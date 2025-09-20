from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QTextEdit, QPushButton, QLabel, QSplitter, QGroupBox, QFormLayout, QLineEdit, QMessageBox, QTabWidget, QWidget, QSpinBox, QDoubleSpinBox, QComboBox, QColorDialog, QScrollArea
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
import yaml
from .workflow_bridge import QuantumWorkflowBridge
from configuration_management.config_manager import ConfigManager

class ColorButton(QPushButton):
    def __init__(self, color, parent=None):
        super().__init__(parent)
        self.setColor(color)
        self.clicked.connect(self.chooseColor)
    
    def setColor(self, color):
        self.color = color
        self.setStyleSheet(f'background-color: {color}')
    
    def chooseColor(self):
        color = QColorDialog.getColor(QColor(self.color))
        if color.isValid():
            self.setColor(color.name())

class ConfigDialog(QDialog):
    def __init__(self, parent=None, bridge=None):
        super().__init__(parent)
        self.setWindowTitle("Configuration Editor")
        self.resize(900, 700)
        self.bridge = bridge or QuantumWorkflowBridge()
        self._current_config_module = None
        self.config_manager = ConfigManager()
        self._setup_ui()
        self._populate_config_list()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal)
        # Config list
        left_panel = QVBoxLayout()
        self.file_list = QListWidget()
        self.file_list.currentItemChanged.connect(self._on_file_selected)
        left_panel.addWidget(QLabel("Configuration Files"))
        left_panel.addWidget(self.file_list)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._populate_config_list)
        left_panel.addWidget(refresh_btn)
        left_widget = QGroupBox()
        left_widget.setLayout(left_panel)
        splitter.addWidget(left_widget)
        # Editor and schema
        right_panel = QVBoxLayout()
        right_panel.addWidget(QLabel("Editor"))
        self.editor = QTextEdit()
        right_panel.addWidget(self.editor)
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self._save_current_file)
        self.save_button.setEnabled(False)
        right_panel.addWidget(self.save_button)
        right_panel.addWidget(QLabel("Schema"))
        self.schema_viewer = QTextEdit()
        self.schema_viewer.setReadOnly(True)
        right_panel.addWidget(self.schema_viewer)
        # API key management
        api_group = QGroupBox("Provider API Keys")
        api_layout = QFormLayout(api_group)
        self.api_key_fields = {}
        providers = set()
        for module in self.bridge.list_configs():
            if 'devices' in module or module in ['ibm_devices', 'ionq_devices', 'hardware']:
                providers.add(module.split('_')[0])
        for provider in sorted(providers):
            field = QLineEdit()
            field.setText(self.bridge.get_api_key(provider) or "")
            self.api_key_fields[provider] = field
            save_btn = QPushButton("Save")
            save_btn.clicked.connect(lambda _, p=provider, f=field: self._save_api_key(p, f))
            api_layout.addRow(f"{provider} API Key:", field)
            api_layout.addRow("", save_btn)
        right_panel.addWidget(api_group)
        right_widget = QGroupBox()
        right_widget.setLayout(right_panel)
        splitter.addWidget(right_widget)
        layout.addWidget(splitter)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def _populate_config_list(self):
        self.file_list.clear()
        modules = self.bridge.list_configs()
        for module in modules:
            self.file_list.addItem(module)

    def _on_file_selected(self, current, previous):
        if not current:
            return
        module = current.text()
        try:
            config = self.bridge.get_config(module)
            config_text = yaml.safe_dump(config, sort_keys=False, allow_unicode=True)
        except Exception as e:
            config_text = f"Error loading config: {e}"
        try:
            schema = self.bridge.get_schema(module)
            schema_text = yaml.safe_dump(schema, sort_keys=False, allow_unicode=True)
        except Exception as e:
            schema_text = f"Schema not found: {e}"
        self.editor.setPlainText(config_text)
        self.schema_viewer.setPlainText(schema_text)
        self._current_config_module = module
        self.save_button.setEnabled(True)

    def _save_current_file(self):
        if not self._current_config_module:
            return
        try:
            content = self.editor.toPlainText()
            config = yaml.safe_load(content)
            self.bridge.save_config(self._current_config_module, config)
            QMessageBox.information(self, "Success", "Configuration saved successfully.")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Error saving file: {str(e)}")

    def _save_api_key(self, provider, field):
        key = field.text().strip()
        self.bridge.set_api_key(provider, key)
        QMessageBox.information(self, "API Key Saved", f"API key for {provider} saved.")

    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        # Create tab widget
        tab_widget = QTabWidget()
        
        # Add visualization tab
        vis_tab = self._create_visualization_tab()
        tab_widget.addTab(vis_tab, "Visualization")
        
        # Add other tabs as needed...
        
        layout.addWidget(tab_widget)
        
        # Add save/cancel buttons
        button_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.save_config)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        
        button_layout.addWidget(save_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
    
    def _create_visualization_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Create a scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        scroll_layout = QVBoxLayout(content)
        
        # Colors group
        colors_group = QGroupBox("Colors")
        colors_layout = QFormLayout()
        
        self.color_buttons = {}
        for color_name in self.config_manager.get_config('visualization')['colors']:
            color_value = self.config_manager.get_config('visualization')['colors'][color_name]
            btn = ColorButton(color_value)
            self.color_buttons[color_name] = btn
            colors_layout.addRow(color_name.replace('_', ' ').title(), btn)
        
        colors_group.setLayout(colors_layout)
        scroll_layout.addWidget(colors_group)
        
        # Patch colors
        patch_colors_group = QGroupBox("Patch Colors")
        patch_colors_layout = QVBoxLayout()
        
        self.patch_color_buttons = []
        for i, color in enumerate(self.config_manager.get_config('visualization')['patch_colors']):
            btn = ColorButton(color)
            self.patch_color_buttons.append(btn)
            patch_colors_layout.addWidget(btn)
        
        add_patch_color_btn = QPushButton("Add Color")
        add_patch_color_btn.clicked.connect(self._add_patch_color)
        patch_colors_layout.addWidget(add_patch_color_btn)
        
        patch_colors_group.setLayout(patch_colors_layout)
        scroll_layout.addWidget(patch_colors_group)
        
        # Sizes group
        sizes_group = QGroupBox("Sizes")
        sizes_layout = QFormLayout()
        
        self.size_inputs = {}
        for size_name, size_value in self.config_manager.get_config('visualization')['sizes'].items():
            if isinstance(size_value, dict):
                # Handle nested font sizes
                sub_group = QGroupBox(size_name.replace('_', ' ').title())
                sub_layout = QFormLayout()
                self.size_inputs[size_name] = {}
                for sub_name, sub_value in size_value.items():
                    spin = QSpinBox()
                    spin.setRange(1, 100)
                    spin.setValue(sub_value)
                    self.size_inputs[size_name][sub_name] = spin
                    sub_layout.addRow(sub_name.replace('_', ' ').title(), spin)
                sub_group.setLayout(sub_layout)
                sizes_layout.addRow(sub_group)
            else:
                spin = QSpinBox()
                spin.setRange(1, 1000)
                spin.setValue(size_value)
                self.size_inputs[size_name] = spin
                sizes_layout.addRow(size_name.replace('_', ' ').title(), spin)
        
        sizes_group.setLayout(sizes_layout)
        scroll_layout.addWidget(sizes_group)
        
        # Interactive features group
        interactive_group = QGroupBox("Interactive Features")
        interactive_layout = QFormLayout()
        
        self.interactive_inputs = {}
        for name, value in self.config_manager.get_config('visualization')['interactive'].items():
            if isinstance(value, (int, float)):
                spin = QDoubleSpinBox()
                spin.setRange(0.0, 10.0)
                spin.setSingleStep(0.1)
                spin.setValue(value)
                self.interactive_inputs[name] = spin
                interactive_layout.addRow(name.replace('_', ' ').title(), spin)
            elif isinstance(value, str):  # For colors
                btn = ColorButton(value)
                self.interactive_inputs[name] = btn
                interactive_layout.addRow(name.replace('_', ' ').title(), btn)
        
        interactive_group.setLayout(interactive_layout)
        scroll_layout.addWidget(interactive_group)
        
        # Layout parameters group
        layout_group = QGroupBox("Layout Parameters")
        layout_layout = QFormLayout()
        
        self.layout_inputs = {}
        for name, value in self.config_manager.get_config('visualization')['layout'].items():
            spin = QDoubleSpinBox()
            spin.setRange(0.0, 100.0)
            spin.setSingleStep(0.1)
            spin.setValue(value)
            self.layout_inputs[name] = spin
            layout_layout.addRow(name.replace('_', ' ').title(), spin)
        
        layout_group.setLayout(layout_layout)
        scroll_layout.addWidget(layout_group)
        
        # Figure parameters group
        figure_group = QGroupBox("Figure Parameters")
        figure_layout = QFormLayout()
        
        self.figure_inputs = {}
        for name, value in self.config_manager.get_config('visualization')['figure'].items():
            if isinstance(value, int):
                spin = QSpinBox()
                spin.setRange(1, 1000)
            else:
                spin = QDoubleSpinBox()
                spin.setRange(0.0, 1.0)
                spin.setSingleStep(0.1)
            spin.setValue(value)
            self.figure_inputs[name] = spin
            figure_layout.addRow(name.replace('_', ' ').title(), spin)
        
        figure_group.setLayout(figure_layout)
        scroll_layout.addWidget(figure_group)
        
        scroll.setWidget(content)
        layout.addWidget(scroll)
        
        return tab
    
    def _add_patch_color(self):
        """Add a new patch color button."""
        btn = ColorButton("#000000")
        self.patch_color_buttons.append(btn)
        layout = self.findChild(QGroupBox, "Patch Colors").layout()
        layout.insertWidget(layout.count() - 1, btn)
    
    def save_config(self):
        """Save all configuration changes."""
        # Update visualization config
        vis_config = {
            'colors': {name: btn.color for name, btn in self.color_buttons.items()},
            'patch_colors': [btn.color for btn in self.patch_color_buttons],
            'sizes': {},
            'interactive': {},
            'layout': {},
            'figure': {}
        }
        
        # Update sizes
        for name, input_widget in self.size_inputs.items():
            if isinstance(input_widget, dict):
                vis_config['sizes'][name] = {
                    sub_name: spin.value()
                    for sub_name, spin in input_widget.items()
                }
            else:
                vis_config['sizes'][name] = input_widget.value()
        
        # Update interactive features
        for name, input_widget in self.interactive_inputs.items():
            if isinstance(input_widget, ColorButton):
                vis_config['interactive'][name] = input_widget.color
            else:
                vis_config['interactive'][name] = input_widget.value()
        
        # Update layout parameters
        for name, spin in self.layout_inputs.items():
            vis_config['layout'][name] = spin.value()
        
        # Update figure parameters
        for name, spin in self.figure_inputs.items():
            vis_config['figure'][name] = spin.value()
        
        # Save to file
        try:
            self.config_manager.save_config('visualization', vis_config)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save configuration: {str(e)}") 