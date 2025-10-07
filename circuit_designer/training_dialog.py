from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget, QGroupBox, QFormLayout, QComboBox, QDoubleSpinBox, QSpinBox, QPushButton, QLabel, QProgressBar, QTextEdit, QMessageBox, QFileDialog, QLineEdit
from PySide6.QtCore import QTimer, Signal
from .workflow_bridge import QuantumWorkflowBridge
from hardware_abstraction.device_abstraction import DeviceAbstraction
import os
import json
import math
import time
import yaml
from scode.api import SurfaceCodeAPI
from utils.credential_manager import ensure_google_adc_from_stored
from cloud.remote_trainer import JobConfig
from cloud.vertex_trainer import VertexAITrainer

class TrainingDialog(QDialog):
    log_signal = Signal(str, object)  # message, progress
    error_signal = Signal(str)
    process_exit_signal = Signal(int)

    def __init__(self, parent=None, bridge=None, get_circuit_func=None):
        super().__init__(parent)
        self.bridge = bridge or QuantumWorkflowBridge()
        self.get_circuit_func = get_circuit_func
        self.selected_module = 'surface_code'
        self.training_in_progress = False
        self.current_episode = 0
        self.total_episodes = 1000
        self.current_reward = None
        self.current_ler = None
        self.reward_history = []
        self.episode_history = []
        self.ler_history = []
        self.agent_config = {}
        self._setup_ui()
        self._initialize_agent_config()
        self._update_ui_for_agent_type()
        self.log_signal.connect(self._handle_log_update)
        self.error_signal.connect(self._handle_error)
        self.process_exit_signal.connect(self._handle_process_exit)
        # Load persisted training profile
        try:
            self._load_training_profile()
        except Exception:
            pass
        # Cloud state
        self.cloud_trainer = None
        self.cloud_job_id = None
        self.cloud_poll_timer = None
        self._cloud_project = None
        self._cloud_region = None
        self._cloud_logs_last_ts = None  # RFC3339 timestamp string
        self._cloud_start_time = None
        self._cloud_timeout_seconds = 0
        self._cloud_auto_shutdown = False

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)
        self._setup_configuration_tab()
        self._setup_training_tab()
        self._setup_results_tab()
        button_layout = QHBoxLayout()
        self.start_button = QPushButton("Start Training")
        self.start_button.clicked.connect(self._on_start_training)
        button_layout.addWidget(self.start_button)
        self.stop_button = QPushButton("Stop Training")
        self.stop_button.clicked.connect(self._on_stop_training)
        self.stop_button.setEnabled(False)
        button_layout.addWidget(self.stop_button)
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.accept)
        button_layout.addWidget(self.close_button)
        main_layout.addLayout(button_layout)
        self._populate_device_list()

    def _setup_configuration_tab(self):
        config_tab = QWidget()
        config_layout = QVBoxLayout(config_tab)
        module_group = QGroupBox("Module to Train")
        module_layout = QVBoxLayout(module_group)
        self.module_combo = QComboBox()
        self.module_combo.addItems([
            "Code Patch Optimizer",
            "Circuit Optimizer"
        ])
        self.module_combo.setToolTip(
            "Select 'Code Patch Optimizer' to train the RL mapping agent.\n"
            "Surface vs qLDPC is chosen in configs/multi_patch_rl_agent.yaml ->\n"
            "multi_patch_rl_agent.environment.code_family."
        )
        self.module_combo.currentIndexChanged.connect(self._on_module_changed)
        module_layout.addWidget(self.module_combo)
        config_layout.addWidget(module_group)
        # Remove provider/device selection from UI
        # Instead, load from hardware.json
        with open('configs/hardware.json', 'r') as f:
            hw = json.load(f)
        self.provider_name = hw.get('provider_name', 'ibm')
        self.device_name = hw.get('device_name', 'ibm_hummingbird')
        # Training source configuration
        self._setup_training_source_ui(config_layout)
        # Cloud training configuration
        self._setup_cloud_ui(config_layout)
        # Module-specific dynamic config
        self.dynamic_config_area = QVBoxLayout()
        config_layout.addLayout(self.dynamic_config_area)
        self._populate_dynamic_config_fields('surface_code')
        config_layout.addStretch()
        self.tab_widget.addTab(config_tab, "Configuration")

    def _on_module_changed(self, idx):
        modules = ['surface_code', 'optimizer']
        self.selected_module = modules[idx]
        for i in reversed(range(self.dynamic_config_area.count())):
            widget = self.dynamic_config_area.itemAt(i).widget()
            if widget:
                widget.setParent(None)
        self._populate_dynamic_config_fields(self.selected_module)
        self._update_ui_for_agent_type()

    def _populate_dynamic_config_fields(self, module):
        if module == 'surface_code':
            self._add_surface_code_fields()
        elif module == 'optimizer':
            self._add_optimizer_fields()

    # --- Training source UI ---
    def _setup_training_source_ui(self, parent_layout: QVBoxLayout):
        self.training_source_group = QGroupBox("Training Source")
        grp_layout = QVBoxLayout(self.training_source_group)
        self.training_source_combo = QComboBox()
        self.training_source_combo.addItems(["Current Circuit", "Dataset Files", "Procedural Generation"])
        self.training_source_combo.currentIndexChanged.connect(self._on_training_source_changed)
        grp_layout.addWidget(self.training_source_combo)
        # Dynamic area for source-specific controls
        self.training_source_area = QVBoxLayout()
        grp_layout.addLayout(self.training_source_area)
        parent_layout.addWidget(self.training_source_group)
        # Initialize state
        self.selected_training_source = 'Current Circuit'
        self.dataset_file_paths = []
        self.dataset_circuits = []
        self._refresh_training_source_fields()

    def _on_training_source_changed(self, idx):
        options = ["Current Circuit", "Dataset Files", "Procedural Generation"]
        self.selected_training_source = options[idx]
        self._refresh_training_source_fields()

    def _refresh_training_source_fields(self):
        # Clear existing widgets
        for i in reversed(range(self.training_source_area.count())):
            w = self.training_source_area.itemAt(i).widget()
            if w:
                w.setParent(None)
        if self.selected_training_source == 'Dataset Files':
            btn = QPushButton("Select circuit file(s)...")
            btn.clicked.connect(self._select_dataset_files)
            self.training_source_area.addWidget(btn)
            self.dataset_summary_label = QLabel("No files selected")
            self.training_source_area.addWidget(self.dataset_summary_label)
        elif self.selected_training_source == 'Procedural Generation':
            form = QFormLayout()
            self.proc_qubits_min = QSpinBox(); self.proc_qubits_min.setRange(1, 1000); self.proc_qubits_min.setValue(2)
            self.proc_qubits_max = QSpinBox(); self.proc_qubits_max.setRange(1, 1000); self.proc_qubits_max.setValue(6)
            self.proc_gates_min = QSpinBox(); self.proc_gates_min.setRange(1, 100000); self.proc_gates_min.setValue(10)
            self.proc_gates_max = QSpinBox(); self.proc_gates_max.setRange(1, 100000); self.proc_gates_max.setValue(50)
            self.proc_gate_set = QLineEdit(); self.proc_gate_set.setPlaceholderText("Comma-separated gate names (optional)")
            form.addRow("Qubits min", self.proc_qubits_min)
            form.addRow("Qubits max", self.proc_qubits_max)
            form.addRow("Gates min", self.proc_gates_min)
            form.addRow("Gates max", self.proc_gates_max)
            form.addRow("Gate set", self.proc_gate_set)
            grp = QGroupBox("Procedural Config"); grp.setLayout(form)
            self.training_source_area.addWidget(grp)
            # Preview button
            preview_btn = QPushButton("Preview generated circuits")
            preview_btn.clicked.connect(self._preview_procedural_samples)
            self.training_source_area.addWidget(preview_btn)

    # --- Cloud UI ---
    def _setup_cloud_ui(self, parent_layout: QVBoxLayout):
        self.cloud_group = QGroupBox("Cloud Training (GCP Vertex AI)")
        form = QFormLayout(self.cloud_group)
        self.cloud_enable_checkbox = QCheckBox("Run on Cloud (GCP)") if 'QCheckBox' in globals() else None
        # Lazy import to avoid missing symbol in context; construct explicitly
        from PySide6.QtWidgets import QCheckBox
        self.cloud_enable_checkbox = QCheckBox("Run on Cloud (GCP)")
        form.addRow(self.cloud_enable_checkbox)
        self.gcp_project_edit = QLineEdit(); self.gcp_project_edit.setPlaceholderText("GCP Project ID")
        self.gcp_region_edit = QLineEdit(); self.gcp_region_edit.setText("us-central1")
        self.gcs_bucket_edit = QLineEdit(); self.gcs_bucket_edit.setPlaceholderText("gs://bucket-name or bucket-name")
        self.image_uri_edit = QLineEdit(); self.image_uri_edit.setPlaceholderText("us-docker.pkg.dev/<project>/<repo>/qcraft-gpu:latest")
        self.machine_type_edit = QLineEdit(); self.machine_type_edit.setText("n1-standard-8")
        self.accel_type_edit = QLineEdit(); self.accel_type_edit.setText("NVIDIA_TESLA_T4")
        self.accel_count_spin = QSpinBox(); self.accel_count_spin.setRange(0, 8); self.accel_count_spin.setValue(1)
        self.dataset_gcs_edit = QLineEdit(); self.dataset_gcs_edit.setPlaceholderText("gs://bucket/path/to/dataset/ (optional)")
        self.job_name_edit = QLineEdit(); self.job_name_edit.setPlaceholderText("Optional job name")
        form.addRow("Project", self.gcp_project_edit)
        form.addRow("Region", self.gcp_region_edit)
        form.addRow("GCS Bucket", self.gcs_bucket_edit)
        form.addRow("Image URI", self.image_uri_edit)
        form.addRow("Machine Type", self.machine_type_edit)
        form.addRow("Accelerator Type", self.accel_type_edit)
        form.addRow("Accelerator Count", self.accel_count_spin)
        form.addRow("Dataset GCS URI", self.dataset_gcs_edit)
        form.addRow("Job Name", self.job_name_edit)
        # Timeout and auto-cancel controls
        self.timeout_minutes_spin = QSpinBox(); self.timeout_minutes_spin.setRange(0, 14400); self.timeout_minutes_spin.setValue(0)
        form.addRow("Timeout (min)", self.timeout_minutes_spin)
        self.auto_shutdown_checkbox = QCheckBox("Auto-cancel at timeout")
        form.addRow(self.auto_shutdown_checkbox)
        parent_layout.addWidget(self.cloud_group)

    def _select_dataset_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Select circuit file(s)", "", "Circuit files (*.json *.yaml *.yml);;All files (*.*)")
        if not paths:
            return
        self.dataset_file_paths = paths
        # Load circuits now for quick validation
        self.dataset_circuits = self._load_circuits_from_paths(paths)
        count = len(self.dataset_circuits)
        avg_qubits = sum(len(c.get('qubits', [])) for c in self.dataset_circuits) / count if count else 0
        avg_gates = sum(len(c.get('gates', [])) for c in self.dataset_circuits) / count if count else 0
        self.dataset_summary_label.setText(f"Selected {len(paths)} file(s), loaded {count} circuit(s). Avg qubits: {avg_qubits:.1f}, Avg gates: {avg_gates:.1f}")
        # Persist profile
        self._save_training_profile()

    def _load_circuits_from_paths(self, paths: list) -> list:
        circuits = []
        for p in paths:
            try:
                if p.lower().endswith('.json'):
                    with open(p, 'r') as f:
                        data = json.load(f)
                elif p.lower().endswith(('.yaml', '.yml')):
                    with open(p, 'r') as f:
                        data = yaml.safe_load(f)
                else:
                    continue
                if isinstance(data, dict) and 'qubits' in data:
                    circuits.append(data)
                elif isinstance(data, list):
                    circuits.extend([d for d in data if isinstance(d, dict) and 'qubits' in d])
            except Exception as e:
                # Continue on individual file errors
                print(f"[WARN] Failed to load circuit from {p}: {e}")
        return circuits

    def _get_procedural_config(self) -> dict:
        gate_set = [g.strip() for g in self.proc_gate_set.text().split(',')] if hasattr(self, 'proc_gate_set') and self.proc_gate_set.text().strip() else None
        return {
            'qubits': {'min': self.proc_qubits_min.value(), 'max': self.proc_qubits_max.value()},
            'gates': {'min': self.proc_gates_min.value(), 'max': self.proc_gates_max.value()},
            'gate_set': gate_set
        }

    def _preview_procedural_samples(self):
        try:
            cfg = self._get_procedural_config()
            # Use device info for native gate set fallback
            provider, device_name = self._get_active_provider_device()
            device_info = DeviceAbstraction.get_device_info(provider, device_name)
            samples = [self._generate_random_circuit(cfg, device_info) for _ in range(3)]
            msg = []
            for i, c in enumerate(samples):
                msg.append(f"Sample {i+1}: qubits={len(c.get('qubits', []))}, gates={len(c.get('gates', []))}")
            QMessageBox.information(self, "Procedural Preview", "\n".join(msg))
        except Exception as e:
            QMessageBox.warning(self, "Preview Error", f"Failed to generate preview: {e}")

    def _generate_random_circuit(self, cfg: dict, device_info: dict) -> dict:
        import random
        qmin = int((cfg.get('qubits') or {}).get('min', 2))
        qmax = int((cfg.get('qubits') or {}).get('max', max(2, device_info.get('max_qubits', 5))))
        gmin = int((cfg.get('gates') or {}).get('min', 10))
        gmax = int((cfg.get('gates') or {}).get('max', 50))
        n_qubits = max(1, random.randint(min(qmin, qmax), max(qmin, qmax)))
        n_gates = max(1, random.randint(min(gmin, gmax), max(gmin, gmax)))
        gate_set = cfg.get('gate_set') or list(device_info.get('native_gates', ['H','X','Z','CNOT','S','T','CZ']))
        single_gates = [g for g in gate_set if str(g).upper() not in {'CNOT','CX','CZ','SWAP','CCX'}]
        twoq_gates = [g for g in gate_set if str(g).upper() in {'CNOT','CX','CZ','SWAP'}]
        circuit = {'qubits': list(range(n_qubits)), 'clbits': [], 'gates': []}
        t = 0
        for _ in range(n_gates):
            use_twoq = twoq_gates and n_qubits >= 2 and random.random() < 0.35
            if use_twoq:
                gname = random.choice(twoq_gates)
                q1, q2 = random.sample(range(n_qubits), 2)
                circuit['gates'].append({'id': f'g{len(circuit["gates"])}_{gname}_{q1}_{q2}_{t}', 'name': gname, 'qubits': [q1, q2], 'time': t, 'params': []})
            else:
                gname = random.choice(single_gates or ['H'])
                q = random.randrange(n_qubits)
                circuit['gates'].append({'id': f'g{len(circuit["gates"])}_{gname}_{q}_{t}', 'name': gname, 'qubits': [q], 'time': t, 'params': []})
            t += 1
        return circuit

    def _add_surface_code_fields(self):
        # Remove layout type, code distance, learning rate, and episodes fields from the UI
        pass

    def _add_optimizer_fields(self):
        # Learning rate
        self.optimizer_lr_label = QLabel("Learning Rate:")
        self.optimizer_lr_spin = QDoubleSpinBox()
        self.optimizer_lr_spin.setDecimals(6)
        self.optimizer_lr_spin.setRange(1e-6, 1.0)
        self.optimizer_lr_spin.setSingleStep(1e-4)
        self.optimizer_lr_spin.setValue(0.0003)
        self.dynamic_config_area.addWidget(self.optimizer_lr_label)
        self.dynamic_config_area.addWidget(self.optimizer_lr_spin)
        # Number of episodes
        self.optimizer_episodes_label = QLabel("Episodes:")
        self.optimizer_episodes_spin = QSpinBox()
        self.optimizer_episodes_spin.setRange(100, 1000000)
        self.optimizer_episodes_spin.setValue(1000)
        self.dynamic_config_area.addWidget(self.optimizer_episodes_label)
        self.dynamic_config_area.addWidget(self.optimizer_episodes_spin)
        # Vec controls
        self.vec_strategy_label = QLabel("Vectorization:")
        self.vec_strategy_combo = QComboBox(); self.vec_strategy_combo.addItems(["subproc", "dummy", "none"])
        self.n_envs_label = QLabel("Parallel Envs:")
        self.n_envs_spin = QSpinBox(); self.n_envs_spin.setRange(1, 64); self.n_envs_spin.setValue(4)
        vec_form = QFormLayout()
        vec_form.addRow(self.vec_strategy_label, self.vec_strategy_combo)
        vec_form.addRow(self.n_envs_label, self.n_envs_spin)
        vec_group = QGroupBox("Parallelism"); vec_group.setLayout(vec_form)
        self.dynamic_config_area.addWidget(vec_group)

    def _setup_training_tab(self):
        training_tab = QWidget()
        training_layout = QVBoxLayout(training_tab)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        training_layout.addWidget(self.progress_bar)
        self.status_label = QLabel("Ready")
        training_layout.addWidget(self.status_label)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        training_layout.addWidget(self.log_text)
        # Download artifacts button (enabled when cloud job artifacts are available)
        self.download_artifacts_btn = QPushButton("Download Artifacts")
        self.download_artifacts_btn.setEnabled(False)
        self.download_artifacts_btn.clicked.connect(self._on_download_artifacts)
        training_layout.addWidget(self.download_artifacts_btn)
        self.tab_widget.addTab(training_tab, "Training")

    def _setup_results_tab(self):
        results_tab = QWidget()
        results_layout = QVBoxLayout(results_tab)
        self.final_reward_label = QLabel("Final Reward: N/A")
        results_layout.addWidget(self.final_reward_label)
        self.final_avg_reward_label = QLabel("Average Reward: N/A")
        results_layout.addWidget(self.final_avg_reward_label)
        self.training_time_label = QLabel("Training Time: N/A")
        results_layout.addWidget(self.training_time_label)
        self.tab_widget.addTab(results_tab, "Results")

    def _initialize_agent_config(self):
        # Always initialize agent_config as a dict
        self.agent_config = {}
        if self.selected_module == 'surface_code':
            self.module_combo.setCurrentIndex(0)
        elif self.selected_module == 'optimizer':
            self.module_combo.setCurrentIndex(1)

    def _update_ui_for_agent_type(self):
        if self.selected_module == 'surface_code':
            self.setWindowTitle("Code Patch Optimizer Training")
        elif self.selected_module == 'optimizer':
            self.setWindowTitle("Circuit Optimizer Training")
        self._add_log_message(f"Selected agent type: {self.selected_module}")

    def _on_start_training(self):
        print("[DEBUG][GUI] _on_start_training CALLED")
        self.training_in_progress = True
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.tab_widget.setCurrentIndex(1)
        self.progress_bar.setValue(0)
        self.log_text.clear()
        self.reward_history = []
        self.episode_history = []
        self.current_reward = None
        self.current_ler = None
        self._add_log_message("Training started...")

        # Always use device info from hardware.json
        provider, device_name = self._get_active_provider_device()
        device_info = DeviceAbstraction.get_device_info(provider, device_name)
        self.agent_config['device'] = device_info
        # Persist RL vec config
        if not isinstance(self.agent_config, dict):
            self.agent_config = {}
        self.agent_config.setdefault('rl_config', {})
        if hasattr(self, 'vec_strategy_combo'):
            self.agent_config['rl_config']['vec_strategy'] = self.vec_strategy_combo.currentText()
        if hasattr(self, 'n_envs_spin'):
            self.agent_config['rl_config']['n_envs'] = int(self.n_envs_spin.value())
        if hasattr(self, 'optimizer_episodes_spin'):
            self.agent_config['rl_config']['num_episodes'] = int(self.optimizer_episodes_spin.value())
        self.bridge.set_agent_config(self.agent_config)

        # Cloud path: submit Vertex AI job if enabled
        if hasattr(self, 'cloud_enable_checkbox') and self.cloud_enable_checkbox.isChecked():
            self._submit_vertex_job()
            # Do not proceed with local training
            return

        def gui_log_callback(message, progress):
            self.log_signal.emit(message, progress)
            if "[ERROR]" in message or "Exception" in message or "Traceback" in message:
                self.error_signal.emit(message)
            if "Training process exited with code" in message:
                try:
                    code = int(message.split("code")[-1].strip())
                except Exception:
                    code = -1
                self.process_exit_signal.emit(code)

        # Actually start training here
        config_path = None
        if self.selected_module == 'optimizer':
            # Determine training source
            circuits = None
            procedural = None
            if self.selected_training_source == 'Dataset Files':
                if not self.dataset_circuits:
                    QMessageBox.warning(self, "No Circuits", "No circuits loaded from selected files. Please select valid JSON/YAML circuit files.")
                    self.training_in_progress = False
                    self.start_button.setEnabled(True)
                    self.stop_button.setEnabled(False)
                    return
                circuits = self.dataset_circuits
                # Use a minimal single-circuit placeholder to satisfy the API
                circuit = circuits[0]
            elif self.selected_training_source == 'Procedural Generation':
                procedural = self._get_procedural_config()
                # Minimal placeholder circuit; env will procedurally sample on reset
                circuit = {'gates': [], 'qubits': list(range(procedural['qubits']['min']))}
            else:
                # Current circuit
                try:
                    circuit = self.get_circuit_func() if callable(self.get_circuit_func) else None
                except Exception:
                    circuit = None
                if not isinstance(circuit, dict) or 'qubits' not in circuit:
                    QMessageBox.warning(self, "Empty Circuit", "Current circuit is empty. Please add gates or choose a different training source.")
                    self.training_in_progress = False
                    self.start_button.setEnabled(True)
                    self.stop_button.setEnabled(False)
                    return
            self.bridge.train_optimizer_agent(
                circuit=circuit,
                device_info=device_info,
                config_overrides=self.agent_config,
                log_callback=gui_log_callback,
                circuits=circuits,
                procedural=procedural
            )
        else:
            self.bridge.train_multi_patch_rl_agent(config_path=config_path, log_callback=gui_log_callback)
        # Do not set training_in_progress to False here; wait for process exit

        # Persist profile on start
        try:
            self._save_training_profile()
        except Exception:
            pass

    # --- Cloud submission helpers ---
    def _submit_vertex_job(self):
        # Validate minimal fields
        project = self.gcp_project_edit.text().strip()
        region = self.gcp_region_edit.text().strip() or 'us-central1'
        bucket = self.gcs_bucket_edit.text().strip()
        image_uri = self.image_uri_edit.text().strip()
        if not project or not image_uri:
            QMessageBox.warning(self, "Missing GCP settings", "Project and Image URI are required for cloud training.")
            self.training_in_progress = False
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            return
        # Ensure GCP credentials are available
        if not self._ensure_gcp_credentials():
            self.training_in_progress = False
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            return
        # Build job config
        cfg = JobConfig(
            module='optimizer' if self.selected_module == 'optimizer' else 'surface_code',
            config_overrides=self.agent_config or {},
            episodes=int(self.optimizer_episodes_spin.value()) if hasattr(self, 'optimizer_episodes_spin') else None,
            vec_strategy=self.vec_strategy_combo.currentText() if hasattr(self, 'vec_strategy_combo') else None,
            n_envs=int(self.n_envs_spin.value()) if hasattr(self, 'n_envs_spin') else None,
            project=project,
            region=region,
            bucket=bucket if bucket else None,
            image_uri=image_uri,
            machine_type=self.machine_type_edit.text().strip() or None,
            accelerator_type=self.accel_type_edit.text().strip() or None,
            accelerator_count=int(self.accel_count_spin.value()),
            dataset_gcs_uri=self.dataset_gcs_edit.text().strip() or None,
            procedural_cfg=self._get_procedural_config() if getattr(self, 'selected_training_source', '') == 'Procedural Generation' else None,
            job_name=self.job_name_edit.text().strip() or None,
            timeout_seconds=(int(self.timeout_minutes_spin.value()) * 60) if hasattr(self, 'timeout_minutes_spin') else None,
        )
        try:
            self.cloud_trainer = VertexAITrainer(project=project, region=region, staging_bucket=bucket or None)
            job_id = self.cloud_trainer.submit_job(cfg)
            self.cloud_job_id = job_id
            self._cloud_project = project
            self._cloud_region = region
            self._cloud_logs_last_ts = None
            # Track timeout/auto-shutdown
            self._cloud_start_time = time.time()
            self._cloud_timeout_seconds = int(self.timeout_minutes_spin.value()) * 60 if hasattr(self, 'timeout_minutes_spin') else 0
            self._cloud_auto_shutdown = bool(self.auto_shutdown_checkbox.isChecked()) if hasattr(self, 'auto_shutdown_checkbox') else False
            self._add_log_message(f"[INFO] Submitted Vertex AI job: {job_id}")
            self.status_label.setText("Cloud job submitted")
            # Start polling
            from PySide6.QtCore import QTimer
            self.cloud_poll_timer = QTimer(self)
            self.cloud_poll_timer.timeout.connect(self._poll_vertex_status)
            self.cloud_poll_timer.start(10000)
        except Exception as e:
            QMessageBox.critical(self, "Cloud Submission Failed", str(e))
            self.training_in_progress = False
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)

    def _ensure_gcp_credentials(self) -> bool:
        try:
            import google.auth  # type: ignore
            creds, proj = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
            # Basic sanity: credentials exist and are valid type
            if creds is None:
                raise RuntimeError("No default GCP credentials found.")
            return True
        except Exception as e:
            # Try to set ADC from stored service account JSON
            try:
                path = ensure_google_adc_from_stored()
                if path:
                    import google.auth  # type: ignore
                    creds, proj = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
                    if creds is not None:
                        return True
            except Exception:
                pass
            QMessageBox.critical(
                self,
                "GCP Credentials Required",
                "Google Application Default Credentials were not found.\n\n"
                "Fix one of the following and retry:\n"
                "- Run: gcloud auth application-default login\n"
                "- Or set GOOGLE_APPLICATION_CREDENTIALS to a service account JSON with Vertex AI and GCS permissions.\n\n"
                f"Details: {e}"
            )
            return False

    def _poll_vertex_status(self):
        if not self.cloud_trainer or not self.cloud_job_id:
            return
        try:
            st = self.cloud_trainer.get_status(self.cloud_job_id)
            self.status_label.setText(f"Cloud status: {st.state}")
            if st.message:
                self._add_log_message(st.message)
            # Attempt to stream new logs
            try:
                self._pull_vertex_logs()
            except Exception:
                pass
            # Auto-cancel on timeout if configured
            if (
                self._cloud_auto_shutdown and self._cloud_timeout_seconds and self._cloud_start_time
                and (time.time() - float(self._cloud_start_time)) > float(self._cloud_timeout_seconds)
                and st.state not in ("SUCCEEDED", "FAILED", "CANCELLED")
            ):
                try:
                    self.cloud_trainer.cancel_job(self.cloud_job_id)
                    self._add_log_message("[INFO] Auto-cancelled cloud job due to timeout.")
                except Exception as ce:
                    self._add_log_message(f"[WARN] Auto-cancel failed: {ce}")
            if st.state in ("SUCCEEDED", "FAILED", "CANCELLED", "NOT_FOUND"):
                if self.cloud_poll_timer:
                    self.cloud_poll_timer.stop()
                self._add_log_message(f"[INFO] Job ended with state: {st.state}")
                if st.artifacts_uri:
                    self._add_log_message(f"[INFO] Artifacts: {st.artifacts_uri}")
                    self.download_artifacts_btn.setEnabled(True)
                # Reset buttons
                self.training_in_progress = False
                self.start_button.setEnabled(True)
                self.stop_button.setEnabled(False)
        except Exception as e:
            self._add_log_message(f"[WARN] Status polling error: {e}")

    def _pull_vertex_logs(self):
        # Lazy import to avoid hard dependency
        try:
            from google.cloud import logging_v2  # type: ignore
        except Exception:
            return
        if not (self._cloud_project and self.cloud_job_id):
            return
        client = logging_v2.Client(project=self._cloud_project)
        job_num = self.cloud_job_id.rsplit('/', 1)[-1]
        # Build filter; best-effort match on resource type and job id
        filt = [
            'resource.type="aiplatform.googleapis.com/CustomJob"',
            f'resource.labels.job_id="{job_num}"'
        ]
        if self._cloud_logs_last_ts:
            filt.append(f'timestamp>="{self._cloud_logs_last_ts}"')
        filter_str = " AND ".join(filt)
        entries = list(client.list_entries(filter_=filter_str))
        if not entries:
            return
        entries.sort(key=lambda e: e.timestamp)
        for e in entries:
            try:
                msg = e.payload if isinstance(e.payload, str) else str(e.payload)
                self._add_log_message(msg)
            except Exception:
                pass
        # Update last timestamp
        self._cloud_logs_last_ts = entries[-1].timestamp.isoformat()

    def _on_download_artifacts(self):
        if not (self.cloud_trainer and self.cloud_job_id):
            QMessageBox.information(self, "Artifacts", "No cloud job to download from.")
            return
        dest = QFileDialog.getExistingDirectory(self, "Select download folder")
        if not dest:
            return
        try:
            local = self.cloud_trainer.download_artifacts(self.cloud_job_id, dest)
            if local:
                QMessageBox.information(self, "Artifacts Downloaded", f"Artifacts downloaded to: {local}")
                self._add_log_message(f"[INFO] Artifacts downloaded to: {local}")
            else:
                QMessageBox.warning(self, "Artifacts", "No artifacts URI available to download.")
        except Exception as e:
            QMessageBox.critical(self, "Download Failed", str(e))
            self._add_log_message(f"[ERROR] Artifact download failed: {e}")


    def _handle_log_update(self, message, progress):
        self._add_log_message(message)
        if progress is not None:
            self.progress_bar.setValue(int(progress * 100))
        if "Reward:" in message or "LER=" in message or "Multi-Patch" in message:
            try:
                parts = message.split(",")
                for part in parts:
                    if "Reward:" in part:
                        self.current_reward = float(part.split("Reward:")[1].strip())
                    if "LER=" in part or "Logical Error Rate" in part:
                        ler_str = part.split("=")[-1].replace("e", "E").strip()
                        self.current_ler = float(ler_str)
                if self.current_reward is not None:
                    self.reward_history.append(self.current_reward)
                if self.current_ler is not None:
                    self.ler_history.append(self.current_ler)
            except Exception:
                pass

    def _handle_error(self, message):
        QMessageBox.critical(self, "Training Error", f"An error occurred during training:\n{message}")
        self.training_in_progress = False
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)

    def _handle_process_exit(self, code):
        self.training_in_progress = False
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        if self.reward_history:
            self.final_reward_label.setText(f"Final Reward: {self.reward_history[-1]}")
            avg_reward = sum(self.reward_history) / len(self.reward_history)
            self.final_avg_reward_label.setText(f"Average Reward: {avg_reward:.2f}")
        else:
            self.final_reward_label.setText("Final Reward: N/A")
            self.final_avg_reward_label.setText("Average Reward: N/A")
        self.training_time_label.setText(f"Training Time: {len(self.reward_history)} episodes")
        self.tab_widget.setCurrentIndex(2)
        if code == 0:
            QMessageBox.information(self, "Training Complete", "Training has completed successfully.")
        else:
            QMessageBox.critical(self, "Training Failed", f"The training process exited with code {code}. Please check the logs for details.")

    def _on_stop_training(self):
        if not self.training_in_progress:
            return
        # If cloud job is running, request cancel
        try:
            if getattr(self, 'cloud_trainer', None) and getattr(self, 'cloud_job_id', None):
                self.cloud_trainer.cancel_job(self.cloud_job_id)
                self._add_log_message(f"[INFO] Requested cancel for cloud job: {self.cloud_job_id}")
        except Exception as e:
            self._add_log_message(f"[WARN] Failed to cancel cloud job: {e}")
        self.training_in_progress = False
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self._add_log_message("Training stopped by user.")

    def _add_log_message(self, message):
        self.log_text.append(message)

    def _populate_device_list(self):
        # No-op: provider/device are now loaded from hardware.json
        pass

    def _get_active_provider_device(self):
        # Always return values from hardware.json
        return self.provider_name, self.device_name

    # --- Training profile persistence ---
    def _profile_path(self):
        return os.path.join('configs', 'training_profile.json')

    def _load_training_profile(self):
        path = self._profile_path()
        if not os.path.exists(path):
            return
        with open(path, 'r') as f:
            prof = json.load(f)
        # Restore training source
        source = prof.get('training_source')
        if source in ["Current Circuit", "Dataset Files", "Procedural Generation"]:
            idx = ["Current Circuit", "Dataset Files", "Procedural Generation"].index(source)
            self.training_source_combo.setCurrentIndex(idx)
        # Restore dataset file paths (lazy load; do not auto-open file dialogs)
        paths = prof.get('dataset_file_paths', [])
        if paths:
            self.dataset_file_paths = paths
            self.dataset_circuits = self._load_circuits_from_paths(paths)
        # Restore procedural
        proc = prof.get('procedural', {})
        if proc and hasattr(self, 'proc_qubits_min'):
            self.proc_qubits_min.setValue(int(proc.get('qubits', {}).get('min', self.proc_qubits_min.value())))
            self.proc_qubits_max.setValue(int(proc.get('qubits', {}).get('max', self.proc_qubits_max.value())))
            self.proc_gates_min.setValue(int(proc.get('gates', {}).get('min', self.proc_gates_min.value())))
            self.proc_gates_max.setValue(int(proc.get('gates', {}).get('max', self.proc_gates_max.value())))
            gs = proc.get('gate_set')
            if gs and hasattr(self, 'proc_gate_set'):
                self.proc_gate_set.setText(",".join(gs))
        # Restore vec config
        rl = prof.get('rl_config', {})
        if rl and hasattr(self, 'vec_strategy_combo'):
            if rl.get('vec_strategy') in ["subproc","dummy","none"]:
                self.vec_strategy_combo.setCurrentText(rl.get('vec_strategy'))
        if rl and hasattr(self, 'n_envs_spin'):
            self.n_envs_spin.setValue(int(rl.get('n_envs', self.n_envs_spin.value())))
        # Restore cloud
        cloud = prof.get('cloud', {})
        if cloud:
            if hasattr(self, 'cloud_enable_checkbox'):
                self.cloud_enable_checkbox.setChecked(bool(cloud.get('enabled', False)))
            if cloud.get('project') and hasattr(self, 'gcp_project_edit'):
                self.gcp_project_edit.setText(cloud.get('project'))
            if cloud.get('region') and hasattr(self, 'gcp_region_edit'):
                self.gcp_region_edit.setText(cloud.get('region'))
            if cloud.get('bucket') and hasattr(self, 'gcs_bucket_edit'):
                self.gcs_bucket_edit.setText(cloud.get('bucket'))
            if cloud.get('image_uri') and hasattr(self, 'image_uri_edit'):
                self.image_uri_edit.setText(cloud.get('image_uri'))
            if cloud.get('machine_type') and hasattr(self, 'machine_type_edit'):
                self.machine_type_edit.setText(cloud.get('machine_type'))
            if cloud.get('accelerator_type') and hasattr(self, 'accel_type_edit'):
                self.accel_type_edit.setText(cloud.get('accelerator_type'))
            if cloud.get('accelerator_count') and hasattr(self, 'accel_count_spin'):
                try:
                    self.accel_count_spin.setValue(int(cloud.get('accelerator_count')))
                except Exception:
                    pass
            if cloud.get('dataset_gcs_uri') and hasattr(self, 'dataset_gcs_edit'):
                self.dataset_gcs_edit.setText(cloud.get('dataset_gcs_uri'))
            if cloud.get('job_name') and hasattr(self, 'job_name_edit'):
                self.job_name_edit.setText(cloud.get('job_name'))
            if cloud.get('timeout_minutes') is not None and hasattr(self, 'timeout_minutes_spin'):
                try:
                    self.timeout_minutes_spin.setValue(int(cloud.get('timeout_minutes') or 0))
                except Exception:
                    pass
            if 'auto_shutdown' in cloud and hasattr(self, 'auto_shutdown_checkbox'):
                try:
                    self.auto_shutdown_checkbox.setChecked(bool(cloud.get('auto_shutdown')))
                except Exception:
                    pass

    def _save_training_profile(self):
        prof = {
            'training_source': self.selected_training_source,
            'dataset_file_paths': self.dataset_file_paths,
            'procedural': self._get_procedural_config() if self.selected_training_source == 'Procedural Generation' else {},
            'rl_config': {
                'vec_strategy': self.vec_strategy_combo.currentText() if hasattr(self, 'vec_strategy_combo') else 'subproc',
                'n_envs': int(self.n_envs_spin.value()) if hasattr(self, 'n_envs_spin') else 4,
            },
            'cloud': {
                'enabled': bool(self.cloud_enable_checkbox.isChecked()) if hasattr(self, 'cloud_enable_checkbox') else False,
                'project': self.gcp_project_edit.text().strip() if hasattr(self, 'gcp_project_edit') else '',
                'region': self.gcp_region_edit.text().strip() if hasattr(self, 'gcp_region_edit') else '',
                'bucket': self.gcs_bucket_edit.text().strip() if hasattr(self, 'gcs_bucket_edit') else '',
                'image_uri': self.image_uri_edit.text().strip() if hasattr(self, 'image_uri_edit') else '',
                'machine_type': self.machine_type_edit.text().strip() if hasattr(self, 'machine_type_edit') else '',
                'accelerator_type': self.accel_type_edit.text().strip() if hasattr(self, 'accel_type_edit') else '',
                'accelerator_count': int(self.accel_count_spin.value()) if hasattr(self, 'accel_count_spin') else 0,
                'dataset_gcs_uri': self.dataset_gcs_edit.text().strip() if hasattr(self, 'dataset_gcs_edit') else '',
                'job_name': self.job_name_edit.text().strip() if hasattr(self, 'job_name_edit') else '',
                'timeout_minutes': int(self.timeout_minutes_spin.value()) if hasattr(self, 'timeout_minutes_spin') else 0,
                'auto_shutdown': bool(self.auto_shutdown_checkbox.isChecked()) if hasattr(self, 'auto_shutdown_checkbox') else False,
            },
        }
        os.makedirs('configs', exist_ok=True)
        with open(self._profile_path(), 'w') as f:
            json.dump(prof, f, indent=2)

    def _populate_optimizer_device_list(self):
        provider = self.optimizer_provider_combo.currentText().lower() if hasattr(self, 'optimizer_provider_combo') else 'ibm'
        devices = self.bridge.list_devices(provider)
        print(f"[DEBUG] Optimizer devices for provider '{provider}': {devices}")
        self.optimizer_device_combo.clear()
        if devices:
            self.optimizer_device_combo.addItems(devices)
            self.start_button.setEnabled(True)
            self.optimizer_device_combo.setToolTip("")
        else:
            self.optimizer_device_combo.addItem("No devices found")
            self.start_button.setEnabled(False)
            self.optimizer_device_combo.setToolTip("No devices found for this provider. Check your config files.") 