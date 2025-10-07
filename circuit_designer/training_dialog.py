from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget, QGroupBox, QFormLayout, QComboBox, QDoubleSpinBox, QSpinBox, QPushButton, QLabel, QProgressBar, QTextEdit, QMessageBox, QFileDialog, QLineEdit
from PySide6.QtCore import QTimer, Signal
from .workflow_bridge import QuantumWorkflowBridge
from hardware_abstraction.device_abstraction import DeviceAbstraction
import os
import json
import math
import yaml
from scode.api import SurfaceCodeAPI

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

    def _save_training_profile(self):
        prof = {
            'training_source': self.selected_training_source,
            'dataset_file_paths': self.dataset_file_paths,
            'procedural': self._get_procedural_config() if self.selected_training_source == 'Procedural Generation' else {},
            'rl_config': {
                'vec_strategy': self.vec_strategy_combo.currentText() if hasattr(self, 'vec_strategy_combo') else 'subproc',
                'n_envs': int(self.n_envs_spin.value()) if hasattr(self, 'n_envs_spin') else 4
            }
        }
        os.makedirs('configs', exist_ok=True)
        with open(self._profile_path(), 'w') as f:
            json.dump(prof, f, indent=2)

    def _on_optimizer_provider_changed(self, idx=None):
        self._populate_optimizer_device_list()

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