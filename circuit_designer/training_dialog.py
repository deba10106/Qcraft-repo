from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget, QGroupBox, QFormLayout, QComboBox, QDoubleSpinBox, QSpinBox, QPushButton, QLabel, QProgressBar, QTextEdit, QMessageBox
from PySide6.QtCore import QTimer, Signal
from .workflow_bridge import QuantumWorkflowBridge
from hardware_abstraction.device_abstraction import DeviceAbstraction
import os
import json
import math
from scode.api import SurfaceCodeAPI

class TrainingDialog(QDialog):
    log_signal = Signal(str, object)  # message, progress
    error_signal = Signal(str)
    process_exit_signal = Signal(int)

    def __init__(self, parent=None, bridge=None):
        super().__init__(parent)
        self.bridge = bridge or QuantumWorkflowBridge()
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
            "Surface Code Generator",
            "Circuit Optimizer"
        ])
        self.module_combo.currentIndexChanged.connect(self._on_module_changed)
        module_layout.addWidget(self.module_combo)
        config_layout.addWidget(module_group)
        # Remove provider/device selection from UI
        # Instead, load from hardware.json
        with open('configs/hardware.json', 'r') as f:
            hw = json.load(f)
        self.provider_name = hw.get('provider_name', 'ibm')
        self.device_name = hw.get('device_name', 'ibm_hummingbird')
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
            self.setWindowTitle("Surface Code Generator Training")
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
            # Dummy circuit for optimizer training (should be replaced with actual circuit if available)
            dummy_circuit = {'gates': [], 'qubits': []}
            self.bridge.train_optimizer_agent(
                circuit=dummy_circuit,
                device_info=device_info,
                config_overrides=self.agent_config,
                log_callback=gui_log_callback
            )
        else:
            self.bridge.train_multi_patch_rl_agent(config_path=config_path, log_callback=gui_log_callback)
        # Do not set training_in_progress to False here; wait for process exit


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