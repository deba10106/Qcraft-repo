import sys
import os
import io
import json
import numpy as np
import matplotlib.pyplot as plt
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QProgressBar, QLabel, QMessageBox, QDialog, QComboBox, QTextEdit, QScrollArea, QFileDialog, QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox
from PySide6.QtCore import QThread, Signal, QObject, Qt
from PySide6.QtGui import QPixmap
import math
from circuit_designer.visualization.mapping_visualizer import MappingVisualizer
from circuit_designer.visualization.surface_code_visualizer import SurfaceCodeVisualizer
from circuit_designer.circuit_editor import CircuitEditor
from circuit_designer.workflow_bridge import QuantumWorkflowBridge
from circuit_designer.gate_palette import GatePalette
from circuit_designer.circuit_canvas import CircuitCanvas
from circuit_designer.training_dialog import TrainingDialog
from circuit_designer.config_dialog import ConfigDialog
from hardware_abstraction.device_abstraction import DeviceAbstraction
from .ft_circuit_choice_dialog import FTCircuitChoiceDialog
from circuit_optimization.api import CircuitOptimizationAPI
from scode.api import SurfaceCodeAPI
from code_switcher.code_switcher import CodeSwitcherAPI
from execution_simulation.execution_simulator import ExecutionSimulatorAPI
from logging_results.logging_results_manager import LoggingResultsManager
from fault_tolerant_circuit_builder.ft_circuit_builder import FaultTolerantCircuitBuilder

def load_hardware_json(config_dir):
    try:
        from importlib.resources import files
        hw_path = files('configs').joinpath('hardware.json')
        with hw_path.open('r') as f:
            hw = json.load(f)
    except (FileNotFoundError, ModuleNotFoundError, AttributeError, ImportError):
        hardware_json_path = os.path.join('configs', 'hardware.json')
        with open(hardware_json_path, 'r') as f:
            hw = json.load(f)
    return hw

def get_provider_and_device(config_dir):
    try:
        from importlib.resources import files
        hw_path = files('configs').joinpath('hardware.json')
        with hw_path.open('r') as f:
            hw = json.load(f)
        return hw['provider_name'], hw['device_name']
    except (FileNotFoundError, ModuleNotFoundError, AttributeError, ImportError):
        hardware_json_path = os.path.join('configs', 'hardware.json')
    with open(hardware_json_path, 'r') as f:
        hw = json.load(f)
    return hw['provider_name'], hw['device_name']

class OptimizationMethodDialog(QDialog):
    def __init__(self, parent=None, methods=None):
        super().__init__(parent)
        self.setWindowTitle("Select Optimization Method")
        self.selected_method = None
        layout = QVBoxLayout(self)
        label = QLabel("Choose optimization method:")
        layout.addWidget(label)
        self.combo = QComboBox()
        self.combo.addItems(methods or ["rule_based", "rl", "ml", "hybrid"])
        layout.addWidget(self.combo)
        btns = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(ok_btn)
        btns.addWidget(cancel_btn)
        layout.addLayout(btns)
    def get_selected_method(self):
        return self.combo.currentText()

class CircuitPreviewDialog(QDialog):
    def __init__(self, parent, circuit_data, show_circuit_button=False):
        super().__init__(parent)
        self.setWindowTitle("Circuit Visualization")
        self.setMinimumSize(800, 600)
        
        # Create main layout
        layout = QVBoxLayout(self)
        
        # Create a scroll area to contain the circuit visualization
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        
        # Create a widget to hold the circuit content
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        
        # Display circuit information
        if circuit_data:
            # Extract circuit data
            qubits = circuit_data.get('qubits', [])
            gates = circuit_data.get('gates', [])
            
            # Add circuit summary
            summary = f"Circuit with {len(qubits)} qubits and {len(gates)} gates"
            summary_label = QLabel(summary)
            summary_label.setStyleSheet("font-weight: bold; font-size: 14px;")
            content_layout.addWidget(summary_label)
            
            # Add gate list in a table format
            if gates:
                table = QTableWidget()
                table.setColumnCount(4)
                table.setRowCount(len(gates))
                table.setHorizontalHeaderLabels(["Gate", "Qubits", "Time", "Parameters"])
                
                for i, gate in enumerate(gates):
                    table.setItem(i, 0, QTableWidgetItem(gate.get('name', '')))
                    table.setItem(i, 1, QTableWidgetItem(str(gate.get('qubits', []))))
                    table.setItem(i, 2, QTableWidgetItem(str(gate.get('time', ''))))
                    table.setItem(i, 3, QTableWidgetItem(str(gate.get('params', []))))
                
                table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
                content_layout.addWidget(table)
        else:
            content_layout.addWidget(QLabel("No circuit data available"))
        
        # Set up the scroll area
        scroll.setWidget(content_widget)
        layout.addWidget(scroll)
        
        # Add buttons at the bottom
        button_layout = QHBoxLayout()
        save_button = QPushButton("Save as Image")
        save_button.clicked.connect(self._save_as_image)
        
        # Add Show Circuit Diagram button if requested
        if show_circuit_button:
            show_circuit_btn = QPushButton("Show Circuit Diagram")
            show_circuit_btn.clicked.connect(self._show_circuit_diagram)
            button_layout.addWidget(show_circuit_btn)
        
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        
        button_layout.addWidget(save_button)
        button_layout.addWidget(close_button)
        layout.addLayout(button_layout)
        
        # Store circuit data for visualization
        self.circuit_data = circuit_data
    
    def _save_as_image(self):
        filename, _ = QFileDialog.getSaveFileName(self, "Save Circuit Image", "", "PNG Files (*.png);;All Files (*)")
        if filename:
            # Capture the widget as an image
            pixmap = self.grab()
            pixmap.save(filename, "PNG")

    def _show_circuit_diagram(self):
        """Display a visual circuit diagram using matplotlib"""
        if not self.circuit_data:
            QMessageBox.warning(self, "No Circuit", "No circuit data available to visualize.")
            return
            
        try:
            # Extract circuit data
            qubits = self.circuit_data.get('qubits', [])
            gates = self.circuit_data.get('gates', [])
            
            if not qubits or not gates:
                QMessageBox.warning(self, "Empty Circuit", "The circuit has no qubits or gates to display.")
                return
                
            # Create a figure with appropriate size
            fig, ax = plt.subplots(figsize=(12, len(qubits) * 0.5 + 2), dpi=100)
            
            # Set title and labels
            ax.set_title("Quantum Circuit Diagram", fontsize=14)
            ax.set_xlabel("Time/Gate Index", fontsize=12)
            ax.set_ylabel("Qubit", fontsize=12)
            
            # Sort qubits to ensure consistent ordering
            sorted_qubits = sorted(qubits)
            
            # Set y-axis to show qubit indices
            ax.set_yticks(range(len(sorted_qubits)))
            ax.set_yticklabels([str(q) for q in sorted_qubits])
            
            # Set x-axis limits with some padding
            max_time = max([gate.get('time', i) for i, gate in enumerate(gates)]) if gates else 0
            ax.set_xlim(-0.5, max_time + 0.5)
            ax.set_ylim(-0.5, len(sorted_qubits) - 0.5)
            
            # Draw horizontal lines for qubits
            for i in range(len(sorted_qubits)):
                ax.plot([0, max_time], [i, i], 'k-', alpha=0.3)
            
            # Define colors for different gate types
            gate_colors = {
                'H': '#3498db',      # Blue
                'X': '#e74c3c',      # Red
                'Y': '#f39c12',      # Orange
                'Z': '#2ecc71',      # Green
                'S': '#9b59b6',      # Purple
                'T': '#1abc9c',      # Turquoise
                'CNOT': '#8e44ad',   # Dark purple
                'CZ': '#27ae60',     # Dark green
                'SWAP': '#d35400',   # Dark orange
                'Toffoli': '#2c3e50',# Dark blue
                'MEASURE': '#7f8c8d', # Gray
                'RESET': '#95a5a6',  # Light gray
                'BARRIER': '#bdc3c7', # Very light gray
                'RZ': '#16a085',     # Green blue
                'RX': '#c0392b',     # Dark red
                'RY': '#f1c40f'      # Yellow
            }
            
            # Draw gates
            for i, gate in enumerate(gates):
                name = gate.get('name', '')
                time = gate.get('time', i)  # Use index if time not specified
                qubits_involved = gate.get('qubits', [])
                
                if not qubits_involved:
                    continue
                
                color = gate_colors.get(name, '#7f8c8d')  # Default to gray
                
                # For single-qubit gates
                if len(qubits_involved) == 1:
                    q_idx = sorted_qubits.index(qubits_involved[0]) if qubits_involved[0] in sorted_qubits else 0
                    rect = plt.Rectangle((time - 0.4, q_idx - 0.4), 0.8, 0.8, 
                                       facecolor=color, alpha=0.8, edgecolor='black')
                    ax.add_patch(rect)
                    ax.text(time, q_idx, name, ha='center', va='center', 
                           color='white', fontweight='bold')
                
                # For two-qubit gates
                elif len(qubits_involved) == 2:
                    q1_idx = sorted_qubits.index(qubits_involved[0]) if qubits_involved[0] in sorted_qubits else 0
                    q2_idx = sorted_qubits.index(qubits_involved[1]) if qubits_involved[1] in sorted_qubits else 0
                    
                    # Draw a vertical line connecting the qubits
                    ax.plot([time, time], [q1_idx, q2_idx], '-', color=color, linewidth=2)
                    
                    # Draw control and target for CNOT
                    if name == 'CNOT':
                        # Control dot
                        ax.plot(time, q1_idx, 'ko', markersize=8)
                        
                        # Target circle with plus
                        circle = plt.Circle((time, q2_idx), 0.3, fill=False, edgecolor='black')
                        ax.add_patch(circle)
                        ax.plot([time-0.3, time+0.3], [q2_idx, q2_idx], 'k-', linewidth=2)
                        ax.plot([time, time], [q2_idx-0.3, q2_idx+0.3], 'k-', linewidth=2)
                    
                    # Draw control and target for CZ
                    elif name == 'CZ':
                        # Control dots
                        ax.plot(time, q1_idx, 'ko', markersize=8)
                        ax.plot(time, q2_idx, 'ko', markersize=8)
                    
                    # Draw SWAP gate
                    elif name == 'SWAP':
                        # X symbols at both ends
                        ax.plot([time-0.2, time+0.2], [q1_idx-0.2, q1_idx+0.2], 'k-', linewidth=2)
                        ax.plot([time-0.2, time+0.2], [q1_idx+0.2, q1_idx-0.2], 'k-', linewidth=2)
                        ax.plot([time-0.2, time+0.2], [q2_idx-0.2, q2_idx+0.2], 'k-', linewidth=2)
                        ax.plot([time-0.2, time+0.2], [q2_idx+0.2, q2_idx-0.2], 'k-', linewidth=2)
                    
                    # Default two-qubit gate representation
                    else:
                        rect1 = plt.Rectangle((time - 0.4, q1_idx - 0.4), 0.8, 0.8, 
                                           facecolor=color, alpha=0.8, edgecolor='black')
                        rect2 = plt.Rectangle((time - 0.4, q2_idx - 0.4), 0.8, 0.8, 
                                           facecolor=color, alpha=0.8, edgecolor='black')
                        ax.add_patch(rect1)
                        ax.add_patch(rect2)
                        ax.text(time, q1_idx, name, ha='center', va='center', 
                               color='white', fontweight='bold')
                        ax.text(time, q2_idx, name, ha='center', va='center', 
                               color='white', fontweight='bold')
                
                # For three or more qubit gates (e.g., Toffoli)
                else:
                    # Draw vertical line connecting all qubits
                    q_indices = [sorted_qubits.index(q) if q in sorted_qubits else 0 for q in qubits_involved]
                    min_idx, max_idx = min(q_indices), max(q_indices)
                    ax.plot([time, time], [min_idx, max_idx], '-', color=color, linewidth=2)
                    
                    # Draw gate representation on each qubit
                    for q_idx in q_indices:
                        rect = plt.Rectangle((time - 0.4, q_idx - 0.4), 0.8, 0.8, 
                                           facecolor=color, alpha=0.8, edgecolor='black')
                        ax.add_patch(rect)
                        ax.text(time, q_idx, name[:1], ha='center', va='center', 
                               color='white', fontweight='bold')
            
            # Add grid
            ax.grid(True, linestyle='--', alpha=0.3)
            
            # Create a new dialog to display the circuit diagram
            circuit_dialog = QDialog(self)
            circuit_dialog.setWindowTitle("Circuit Diagram")
            circuit_dialog.setMinimumSize(800, 400)
            
            # Create layout for the dialog
            layout = QVBoxLayout(circuit_dialog)
            
            # Save figure to buffer and convert to QPixmap
            buf = io.BytesIO()
            plt.tight_layout()
            fig.savefig(buf, format='png', dpi=100)
            plt.close(fig)
            buf.seek(0)
            
            # Create QPixmap and display in QLabel
            pixmap = QPixmap()
            pixmap.loadFromData(buf.getvalue())
            
            # Create a label to display the image
            image_label = QLabel()
            image_label.setPixmap(pixmap)
            image_label.setScaledContents(False)
            
            # Create a scroll area to contain the image
            scroll = QScrollArea()
            scroll.setWidget(image_label)
            scroll.setWidgetResizable(True)
            layout.addWidget(scroll)
            
            # Add a save button
            save_btn = QPushButton("Save Circuit Diagram")
            save_btn.clicked.connect(lambda: self._save_circuit_diagram(pixmap))
            layout.addWidget(save_btn)
            
            # Show the dialog
            circuit_dialog.exec()
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            QMessageBox.warning(self, "Visualization Error", f"Error creating circuit diagram: {str(e)}")
    
    def _save_circuit_diagram(self, pixmap):
        """Save the circuit diagram to a file"""
        filename, _ = QFileDialog.getSaveFileName(self, "Save Circuit Diagram", "", "PNG Files (*.png);;All Files (*)")
        if filename:
            pixmap.save(filename, "PNG")

class LayoutPreviewDialog(QDialog):
    def __init__(self, parent, layout_result):
        # Patch: wrap single-patch layout_result if needed
        if 'multi_patch_layout' not in layout_result and 'qubit_layout' in layout_result:
            layout_result = {
                'multi_patch_layout': {
                    0: {'layout': layout_result['qubit_layout'], **{k: v for k, v in layout_result.items() if k != 'qubit_layout'}}
                }
            }
        super().__init__(parent)
        self.setWindowTitle("Surface Code Layout Preview")
        self.setMinimumSize(900, 700)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.image_label = QLabel()
        self.image_label.setScaledContents(False)
        visualizer = SurfaceCodeVisualizer()
        visualizer.draw_surface_code(layout_result)
        visualizer.canvas.draw()
        import io
        from PySide6.QtGui import QPixmap
        buf = io.BytesIO()
        visualizer.fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        pixmap = QPixmap()
        pixmap.loadFromData(buf.getvalue())
        if pixmap.isNull():
            pixmap = QPixmap(600, 400)
            pixmap.fill()
        self.image_label.setPixmap(pixmap)
        scroll.setWidget(self.image_label)
        layout = QVBoxLayout(self)
        layout.addWidget(scroll)
        button_layout = QHBoxLayout()
        save_button = QPushButton("Save Image")
        save_button.clicked.connect(lambda: self._save_image(pixmap))
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        button_layout.addWidget(save_button)
        button_layout.addWidget(close_button)
        layout.addLayout(button_layout)
    def _save_image(self, pixmap):
        filename, _ = QFileDialog.getSaveFileName(self, "Save Image", "", "PNG Files (*.png);;All Files (*)")
        if filename:
            pixmap.save(filename, "PNG")

class MappingPreviewDialog(QDialog):
    def __init__(self, parent, layout_result, mapping_info, device_name, device_info):
        super().__init__(parent)
        self.setWindowTitle("Mapping Preview")
        self.resize(1200, 800)
        layout = QVBoxLayout(self)
        visualizer = MappingVisualizer()
        self.canvas = visualizer.draw_mapping(layout_result, mapping_info, device_info)
        layout.addWidget(self.canvas)
        # Add Save Image and Close buttons
        button_layout = QHBoxLayout()
        save_button = QPushButton("Save Image")
        save_button.clicked.connect(self._save_image)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        button_layout.addWidget(save_button)
        button_layout.addWidget(close_button)
        layout.addLayout(button_layout)
        self.setLayout(layout)
    def _save_image(self):
        filename, _ = QFileDialog.getSaveFileName(self, "Save Mapping Image", "", "PNG Files (*.png);;All Files (*)")
        if filename:
            self.canvas.figure.savefig(filename, format="png", dpi=150, bbox_inches='tight')

class CustomJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder that can handle tuple keys in dictionaries"""
    def encode(self, obj):
        if isinstance(obj, dict):
            # Convert any tuple keys to strings
            new_obj = {}
            for k, v in obj.items():
                if isinstance(k, tuple):
                    new_obj[str(k)] = v
                else:
                    new_obj[k] = v
            return super().encode(new_obj)
        return super().encode(obj)
    
    def default(self, obj):
        import datetime
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, (datetime.date, datetime.datetime)):
            return obj.isoformat()
        return str(obj)

class StepResultDialog(QDialog):
    proceed_signal = Signal()
    stop_signal = Signal()
    
    def __init__(self, parent, title, result_data=None, circuit=None, mapping_info=None, step_name=None):
        super().__init__(parent)
        self._circuit = circuit
        self._mapping_info = mapping_info
        self._step_name = step_name
        self.result_data = result_data  # Store result_data as an instance attribute
        
        print(f"[DEBUG] StepResultDialog.__init__ called for title: {title}")
        
        self.setWindowTitle(title)
        self.setMinimumSize(800, 600)
        
        # Main layout
        layout = QVBoxLayout(self)
        
        # Create a tab widget to organize different views
        tab_widget = QTabWidget()
        layout.addWidget(tab_widget)
        
        # Tab 1: Table View (for structured data)
        table_tab = QWidget()
        table_layout = QVBoxLayout(table_tab)
        
        if result_data:
            # Convert JSON data to table view
            table_widget = self._create_table_from_json(result_data)
            table_layout.addWidget(table_widget)
        else:
            table_layout.addWidget(QLabel("No result data available"))
        
        tab_widget.addTab(table_tab, "Table View")
        
        # Tab 2: Raw JSON View
        json_tab = QWidget()
        json_layout = QVBoxLayout(json_tab)
        
        if result_data:
            json_text = QTextEdit()
            json_text.setReadOnly(True)
            try:
                # Use custom encoder to handle tuple keys
                json_text.setPlainText(json.dumps(result_data, indent=2, cls=CustomJSONEncoder))
            except Exception as e:
                json_text.setPlainText(f"Error serializing JSON: {str(e)}\n\nRaw data: {str(result_data)}")
            json_layout.addWidget(json_text)
        else:
            json_layout.addWidget(QLabel("No result data available"))
        
        tab_widget.addTab(json_tab, "Raw JSON")
        
        # Action buttons based on step type
        button_layout = QHBoxLayout()
        
        # Add step-specific buttons
        if step_name == "layout":
            view_layout_btn = QPushButton("View Layout")
            view_layout_btn.clicked.connect(self._show_layout)
            # Disable if no visualizable layout
            can_view = False
            try:
                if isinstance(self.result_data, dict):
                    mpl = self.result_data.get('multi_patch_layout')
                    if isinstance(mpl, dict) and any(isinstance(p, dict) and p.get('layout') for p in mpl.values()):
                        can_view = True
                    if 'layout' in self.result_data and self.result_data.get('layout'):
                        can_view = True
            except Exception:
                can_view = False
            view_layout_btn.setEnabled(can_view)
            if not can_view:
                view_layout_btn.setToolTip("No layout data to display")
            button_layout.addWidget(view_layout_btn)
        elif step_name == "mapping":
            view_mapping_btn = QPushButton("View Mapping")
            view_mapping_btn.clicked.connect(self._show_mapping)
            # Disable if mapping failed or empty
            can_view = True
            try:
                if not self._mapping_info or self._mapping_info.get('status') == 'failed' or 'error' in self._mapping_info:
                    can_view = False
            except Exception:
                can_view = False
            view_mapping_btn.setEnabled(can_view)
            if not can_view:
                view_mapping_btn.setToolTip("Mapping failed or unavailable")
            button_layout.addWidget(view_mapping_btn)
        elif step_name == "ft_circuit":
            view_circuit_btn = QPushButton("View Optimized Circuit")
            view_circuit_btn.clicked.connect(self._show_circuit)
            button_layout.addWidget(view_circuit_btn)
            
            view_ft_circuit_btn = QPushButton("Visualize FT Circuit")
            view_ft_circuit_btn.clicked.connect(self._show_circuit)
            button_layout.addWidget(view_ft_circuit_btn)
        
        # Add proceed/stop buttons
        proceed_btn = QPushButton("Proceed to Next Step")
        proceed_btn.clicked.connect(self.proceed)
        button_layout.addWidget(proceed_btn)
        
        stop_btn = QPushButton("Stop Workflow")
        stop_btn.clicked.connect(self.stop)
        button_layout.addWidget(stop_btn)
        
        layout.addLayout(button_layout)

    def _create_table_from_json(self, data):
        """Convert JSON data to a table widget for better visualization"""
        from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem
        
        # Create a tree widget for hierarchical display
        tree = QTreeWidget()
        tree.setHeaderLabels(["Property", "Value"])
        tree.setColumnWidth(0, 300)
        
        def add_items(parent_item, key, value):
            # Convert tuple keys to strings for display
            if isinstance(key, tuple):
                key = str(key)
                
            if isinstance(value, dict):
                # For dictionaries, create a parent item and add children
                if parent_item is None:
                    item = QTreeWidgetItem(tree, [str(key), ""])
                else:
                    item = QTreeWidgetItem(parent_item, [str(key), ""])
                
                for k, v in value.items():
                    add_items(item, k, v)
                
                item.setExpanded(True)
            elif isinstance(value, list):
                # For lists, create a parent item and add children
                if parent_item is None:
                    item = QTreeWidgetItem(tree, [str(key), f"(List with {len(value)} items)"])
                else:
                    item = QTreeWidgetItem(parent_item, [str(key), f"(List with {len(value)} items)"])
                
                # Only show first 10 items for large lists
                display_items = value[:10] if len(value) > 10 else value
                
                for i, v in enumerate(display_items):
                    add_items(item, f"[{i}]", v)
                
                if len(value) > 10:
                    QTreeWidgetItem(item, ["...", f"({len(value)-10} more items)"])
                
                item.setExpanded(len(value) <= 5)  # Only auto-expand small lists
            elif isinstance(value, np.ndarray):
                # Handle numpy arrays
                if parent_item is None:
                    item = QTreeWidgetItem(tree, [str(key), f"(Array with shape {value.shape})"])
                else:
                    item = QTreeWidgetItem(parent_item, [str(key), f"(Array with shape {value.shape})"])
                
                # Convert to list for display
                list_value = value.tolist()
                if len(list_value) <= 10:
                    for i, v in enumerate(list_value):
                        add_items(item, f"[{i}]", v)
                else:
                    for i, v in enumerate(list_value[:10]):
                        add_items(item, f"[{i}]", v)
                    QTreeWidgetItem(item, ["...", f"({len(list_value)-10} more items)"])
            else:
                # For primitive values, just add the item
                if parent_item is None:
                    QTreeWidgetItem(tree, [str(key), str(value)])
                else:
                    QTreeWidgetItem(parent_item, [str(key), str(value)])
        
        # Start building the tree
        if isinstance(data, dict):
            for key, value in data.items():
                add_items(None, key, value)
        elif isinstance(data, list):
            for i, value in enumerate(data):
                add_items(None, f"[{i}]", value)
        else:
            QTreeWidgetItem(tree, ["Value", str(data)])
        
        return tree
    
    def proceed(self):
        print("[DEBUG] StepResultDialog: Proceed clicked for step:", self._step_name)
        self.proceed_signal.emit()
        self.accept()
    
    def stop(self):
        print("[DEBUG] StepResultDialog: Stop clicked for step:", self._step_name)
        self.stop_signal.emit()
        self.reject()
    
    def _show_layout(self):
        if self.result_data:
            # If result_data is a mapping result, extract multi_patch_layout
            if 'multi_patch_layout' in self.result_data:
                layout_to_show = {'multi_patch_layout': self.result_data['multi_patch_layout']}
            elif 'layout' in self.result_data:
                # Already a patch dict, wrap it
                layout_to_show = {'multi_patch_layout': {0: {'layout': self.result_data['layout']}}}
            else:
                layout_to_show = self.result_data
            # Validate visualizable content
            has_any = False
            try:
                mpl = layout_to_show.get('multi_patch_layout', {}) if isinstance(layout_to_show, dict) else {}
                for _, patch in (mpl or {}).items():
                    if isinstance(patch, dict) and patch.get('layout') and len(patch.get('layout')) > 0:
                        has_any = True
                        break
            except Exception:
                has_any = False
            if not has_any:
                QMessageBox.warning(self, "No Layout", "No visualizable layout data in this step output.")
                return
            dlg = LayoutPreviewDialog(self, layout_to_show)
            dlg.exec()
        else:
            QMessageBox.warning(self, "No Layout", "No layout data available to visualize.")
    def _show_mapping(self):
        if not self._mapping_info:
            QMessageBox.warning(self, "No Mapping", "No mapping information available to visualize.")
            return
        # Check for mapping failure before opening dialog
        if self._mapping_info.get('status') == 'failed' or 'error' in self._mapping_info:
            error_msg = self._mapping_info.get('error', 'Unknown mapping error.')
            QMessageBox.critical(self, "Mapping Failed", f"Mapping failed:\n{error_msg}\n\nSuggestions:\n- Try fewer logical qubits\n- Try a smaller code distance\n- Check patch layout and device connectivity")
            return
        device_name = self._mapping_info.get('device')
        provider = self._mapping_info.get('provider')
        # Fallback to hardware.json if missing or 'unknown'
        if not device_name or device_name == 'unknown' or not provider or provider == 'unknown':
            from circuit_designer.gui_main import get_provider_and_device
            import os
            config_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../configs'))
            provider, device_name = get_provider_and_device(config_dir)
        from hardware_abstraction.device_abstraction import DeviceAbstraction
        device_info = DeviceAbstraction.get_device_info(provider, device_name)
        # Patch: ensure device_info has 'qubit_positions' to prevent visualizer crash
        if 'qubit_positions' not in device_info or not device_info['qubit_positions']:
            # Try to reconstruct from mapping_info or set as empty dict
            logical_to_physical = self._mapping_info.get('logical_to_physical', {})
            all_physical = set()
            for patch in logical_to_physical.values():
                all_physical.update(patch.values())
            # Try to get positions from device_info if available
            if 'qubits' in device_info and isinstance(device_info['qubits'], dict):
                device_info['qubit_positions'] = {
                    int(q): (v.get('position', {}).get('x', 0), v.get('position', {}).get('y', 0))
                    for q, v in device_info['qubits'].items() if int(q) in all_physical
                }
            # Fallback: generate a grid layout for all mapped physical qubits
            if not device_info.get('qubit_positions') or not any(device_info['qubit_positions'].values()):
                print(f"[DEBUG][MappingPreviewDialog] Generating fallback grid positions for physical qubits: {sorted(all_physical)}")
                n = len(all_physical)
                if n > 0:
                    side = int(n ** 0.5) + 1
                    positions = {}
                    for idx, q in enumerate(sorted(all_physical)):
                        x = idx % side
                        y = idx // side
                        positions[q] = (x, y)
                    device_info['qubit_positions'] = positions
                    print(f"[DEBUG][MappingPreviewDialog] Fallback positions: {positions}")
                else:
                    device_info['qubit_positions'] = {}
        dlg = MappingPreviewDialog(self, self.result_data, self._mapping_info, device_name, device_info)
        dlg.exec()
    
    def _show_circuit(self):
        if self._circuit is None:
            QMessageBox.warning(self, "No Circuit", "No circuit available to visualize.")
            return
        
        # Determine which button was clicked
        sender = self.sender()
        button_text = sender.text() if sender else ""
        
        # Create a dialog with appropriate title based on button clicked
        if "FT Circuit" in button_text:
            dlg = CircuitPreviewDialog(self, self._circuit, show_circuit_button=True)
            dlg.setWindowTitle("Fault-Tolerant Circuit Visualization")
            
            # For FT circuit, use a specialized visualization
            try:
                # Extract the circuit data
                qubits = self._circuit.get('qubits', [])
                gates = self._circuit.get('gates', [])
                
                # Create a more detailed visualization for FT circuit
                fig, ax = plt.subplots(figsize=(10, 6), dpi=120)
                
                # Set up the plot
                ax.set_title("Fault-Tolerant Circuit Gate Timeline", fontsize=14)
                ax.set_xlabel("Time", fontsize=12)
                ax.set_ylabel("Qubit", fontsize=12)
                
                # Draw grid
                ax.grid(True, linestyle='--', alpha=0.7)
                
                # Set y-axis to show qubit indices
                ax.set_yticks(range(len(qubits)))
                ax.set_yticklabels([str(q) for q in qubits])
                
                # Find the maximum time to set x-axis limits
                max_time = 0
                for gate in gates:
                    time = gate.get('time', 0)
                    if time > max_time:
                        max_time = time
                
                ax.set_xlim(-0.1, max_time + 1)
                ax.set_ylim(-0.5, len(qubits) - 0.5)
                
                # Define colors for different gate types
                gate_colors = {
                    'H': 'blue',
                    'X': 'red',
                    'Z': 'green',
                    'CNOT': 'purple',
                    'SWAP': 'orange',
                    'MEASURE': 'brown',
                    'T': 'cyan',
                    'S': 'magenta',
                    'CZ': 'lime',
                    'Toffoli': 'darkviolet'
                }
                
                # Plot gates
                for gate in gates:
                    name = gate.get('name', '')
                    time = gate.get('time', 0)
                    qubits_involved = gate.get('qubits', [])
                    
                    if not qubits_involved:
                        continue
                    
                    color = gate_colors.get(name, 'gray')
                    
                    # For single-qubit gates
                    if len(qubits_involved) == 1:
                        q_idx = qubits.index(qubits_involved[0]) if qubits_involved[0] in qubits else 0
                        ax.text(time, q_idx, name, color='white', fontweight='bold',
                               ha='center', va='center', bbox=dict(facecolor=color, alpha=0.8))
                    
                    # For two-qubit gates
                    elif len(qubits_involved) == 2:
                        q1_idx = qubits.index(qubits_involved[0]) if qubits_involved[0] in qubits else 0
                        q2_idx = qubits.index(qubits_involved[1]) if qubits_involved[1] in qubits else 0
                        
                        # Draw a line connecting the qubits
                        ax.plot([time, time], [q1_idx, q2_idx], color=color, linewidth=2, alpha=0.7)
                        
                        # Add gate label to both qubits
                        ax.text(time, q1_idx, name, color='white', fontweight='bold',
                               ha='center', va='center', bbox=dict(facecolor=color, alpha=0.8))
                        ax.text(time, q2_idx, name, color='white', fontweight='bold',
                               ha='center', va='center', bbox=dict(facecolor=color, alpha=0.8))
                
                # Save the figure to a buffer
                buf = io.BytesIO()
                plt.tight_layout()
                plt.savefig(buf, format='png', dpi=120)
                plt.close(fig)
                buf.seek(0)
                
                # Create a QPixmap from the buffer and display it
                pixmap = QPixmap()
                pixmap.loadFromData(buf.getvalue())
                
                # Create a label to display the image
                label = QLabel()
                label.setPixmap(pixmap)
                label.setScaledContents(True)
                
                # Create a scroll area to contain the label
                scroll = QScrollArea()
                scroll.setWidget(label)
                scroll.setWidgetResizable(True)
                
                # Set up the dialog layout
                layout = QVBoxLayout()
                layout.addWidget(scroll)
                
                # Add a close button
                close_btn = QPushButton("Close")
                close_btn.clicked.connect(dlg.accept)
                layout.addWidget(close_btn)
                
                # Set the layout
                dlg.setLayout(layout)
                dlg.resize(800, 600)
                
            except Exception as e:
                import traceback
                print(f"[ERROR] Error visualizing FT circuit: {e}")
                traceback.print_exc()
                # Fall back to standard circuit preview
                dlg = CircuitPreviewDialog(self, self._circuit, show_circuit_button=True)
                dlg.setWindowTitle("Fault-Tolerant Circuit (Standard View)")
        else:
            # For regular circuit, use the standard CircuitPreviewDialog
            dlg = CircuitPreviewDialog(self, self._circuit, show_circuit_button=True)
            dlg.setWindowTitle("Optimized Circuit Visualization")
        
        # Show the dialog
        dlg.exec()

class WorkflowWorker(QObject):
    progress = Signal(str)
    finished = Signal(str)
    error = Signal(str)
    step_done = Signal(str, dict)  # step_name, result dict

    # Centralized workflow steps
    STEPS = ["layout", "ft_circuit", "code_switcher", "optimization", "mapping", "execution"]

    def __init__(self, circuit_editor, config_dir=None):
        super().__init__()
        self.circuit_editor = circuit_editor
        self.workflow_bridge = circuit_editor.workflow_bridge
        self.config_dir = config_dir or getattr(circuit_editor, 'config_dir', os.path.abspath(os.path.join(os.path.dirname(__file__), '../configs')))
        self.optimizer = CircuitOptimizationAPI()
        self.surface_code_api = SurfaceCodeAPI()
        self.code_switcher = CodeSwitcherAPI()
        self.executor = ExecutionSimulatorAPI()
        self.logger = LoggingResultsManager()
        self.ft_builder = FaultTolerantCircuitBuilder()
        # Patch: always load full device_info for optimizer
        hardware_json_path = os.path.join(self.config_dir, 'hardware.json')
        try:
            self.full_device_info = DeviceAbstraction.load_selected_device(hardware_json_path)
        except Exception as e:
            print(f"[WARNING] Could not load full device_info: {e}")
            self.full_device_info = None
        self.current_step = 0
        self.cancelled = False
        self.step_results = {}
        
    def set_parameters(self, device_info, layout_type, code_distance, run_config=None, config_overrides=None, optimization_method=None):
        self.device_info = device_info
        self.layout_type = layout_type
        self.code_distance = code_distance
        self.run_config = run_config or {}
        self.config_overrides = config_overrides or {}
        self.optimization_method = optimization_method
        
        # Extract logical qubit count from circuit
        circuit = self.circuit_editor.get_circuit()
        if circuit and 'qubits' in circuit:
            logical_qubits = len(circuit['qubits'])
            print(f"[DEBUG] Extracted {logical_qubits} logical qubits from circuit")
            
            # Add to config overrides
            if 'circuit' not in self.config_overrides:
                self.config_overrides['circuit'] = {}
            self.config_overrides['circuit']['logical_qubits'] = logical_qubits
        # Log parameter snapshot
        try:
            dev_name = self.device_info.get('name') if isinstance(self.device_info, dict) else None
            provider = self.device_info.get('provider') if isinstance(self.device_info, dict) else None
            print(f"[DEBUG] Params: device={dev_name}, provider={provider}, layout={self.layout_type}, code_distance={self.code_distance}, optimization_method={self.optimization_method}")
            print(f"[DEBUG] Params: run_config keys={list(self.run_config.keys())}")
            print(f"[DEBUG] Params: overrides keys={list(self.config_overrides.keys())}")
        except Exception:
            pass

    def cancel(self):
        self.cancelled = True

    def run(self):
        try:
            self.current_step = 0
            self._run_next_step()
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error.emit(str(e))

    def proceed(self):
        """Proceed to the next step in the workflow"""
        self.current_step += 1
        self._run_next_step()

    def jump_to_step(self, step_name: str):
        """Jump directly to a named step in the workflow."""
        if step_name in self.STEPS:
            print(f"[DEBUG] WorkflowWorker: jump_to_step -> {step_name}")
            self.current_step = self.STEPS.index(step_name)
        else:
            raise ValueError(f"Unknown step: {step_name}")

    def _run_next_step(self):
        """Run the next step in the workflow (WorkflowWorker)"""
        print(f"[DEBUG] WorkflowWorker running next step: step {self.current_step}")
        try:
            if self.cancelled:
                self.finished.emit('cancelled')
                return
            # Updated workflow: mapping occurs after optimization (multi-patch mapping after FT circuit)
            steps = self.STEPS
            if self.current_step >= len(steps):
                self.finished.emit('done')
                return
            step_name = steps[self.current_step]
            circuit = self.circuit_editor.get_circuit()
            # Step logic
            if step_name == "optimization":
                self.progress.emit("Optimizing circuit...")
                result = self.workflow_bridge.optimize_circuit(circuit, self.device_info, self.config_overrides)
                try:
                    info = result.get('optimization_info', {}) if isinstance(result, dict) else {}
                    print(f"[DEBUG] Optimization: strategy={info.get('strategy_used')}, fallback_reason={info.get('fallback_reason')}")
                except Exception:
                    pass
                self.step_results[step_name] = result
                self.step_done.emit("optimization", result)
            elif step_name == "layout":
                self.progress.emit("Generating surface code layout...")
                result = self.workflow_bridge.surface_code_api.generate_surface_code_layout(
                    self.layout_type, self.code_distance, self.device_info['name'])
                try:
                    mpl = result.get('multi_patch_layout') if isinstance(result, dict) else None
                    patches = len(mpl) if isinstance(mpl, dict) else 0
                    print(f"[DEBUG] Layout: patches={patches}, keys={list(result.keys()) if isinstance(result, dict) else type(result)}")
                except Exception:
                    pass
                self.step_results[step_name] = result
                self.step_done.emit("layout", result)
            elif step_name == "ft_circuit":
                self.progress.emit("Transforming to fault-tolerant circuit...")
                # Use mapping_info and code_spaces from previous results if available
                mapping_info = self.step_results.get("mapping", {}).get("mapping_info") or self.step_results.get("mapping")
                if mapping_info is None:
                    mapping_info = {}
                layout_result = self.step_results.get("layout")
                code_spaces = []
                if layout_result:
                    if 'code_spaces' in layout_result:
                        code_spaces = layout_result['code_spaces']
                    elif 'multi_patch_layout' in layout_result:
                        code_spaces = list(layout_result['multi_patch_layout'].values())
                try:
                    result = self.workflow_bridge.ft_builder.assemble_fault_tolerant_circuit(
                        circuit, mapping_info, code_spaces, self.device_info
                    )
                except ValueError as e:
                    # Emit error back to main thread; do not show UI here
                    error_msg = f"FT Circuit Builder Error: {str(e)}\n\nMapping Info: {mapping_info}\nCode Spaces: {code_spaces}\nDevice Info: {self.device_info}"
                    self.error.emit(error_msg)
                    return
                self.step_results[step_name] = result
                self.step_done.emit("ft_circuit", result)
            elif step_name == "code_switcher":
                self.progress.emit("Applying code switching...")
                # Use FT circuit from previous step
                ft_circuit = self.step_results.get("ft_circuit")
                # Get code_spaces from layout step
                layout_result = self.step_results.get("layout")
                code_spaces = []
                if layout_result:
                    if 'code_spaces' in layout_result:
                        code_spaces = layout_result['code_spaces']
                    elif 'multi_patch_layout' in layout_result:
                        code_spaces = list(layout_result['multi_patch_layout'].values())
                # Identify switching points
                switching_points = self.workflow_bridge.code_switcher.identify_switching_points(
                    ft_circuit, {'code_spaces': code_spaces}
                )
                # For each switching point, assign the first protocol that supports the gate at that point
                protocol_names = self.workflow_bridge.code_switcher.get_supported_switching_protocols()
                protocols = []
                for sp in switching_points:
                    gate_name = sp.get('name') or (sp.get('gate', {}).get('name') if isinstance(sp.get('gate'), dict) else sp.get('gate'))
                    selected_protocol = None
                    for proto_name in protocol_names:
                        supported_gates = self.workflow_bridge.code_switcher.get_supported_gates_for_protocol(proto_name)
                        # Compare gate_name case-insensitively
                        if gate_name and any(gate_name.lower() == sg.lower() for sg in supported_gates):
                            selected_protocol = self.workflow_bridge.code_switcher.get_switching_protocol_info(proto_name)
                            break
                    protocols.append(selected_protocol if selected_protocol else None)
                # Call with all required arguments
                result = self.workflow_bridge.code_switcher.apply_code_switching(
                    ft_circuit, switching_points, protocols, self.device_info
                )
                try:
                    print(f"[DEBUG] CodeSwitcher: result keys={list(result.keys()) if isinstance(result, dict) else type(result)}")
                except Exception:
                    pass
                self.step_results[step_name] = result
                self.step_done.emit("code_switcher", result)
            elif step_name == "mapping":
                self.progress.emit("Mapping logical to physical qubits...")
                # Prefer mapping the FT/optimized circuit when available
                circuit_to_map = (
                    self.step_results.get("ft_circuit")
                    or self.step_results.get("optimization")
                    or circuit
                )
                source = (
                    "ft_circuit" if self.step_results.get("ft_circuit") is not None
                    else ("optimization" if self.step_results.get("optimization") is not None else "original")
                )
                print(f"[DEBUG] Mapping: using circuit source = {source}")
                result = self.workflow_bridge.map_circuit_to_surface_code(
                    circuit_to_map,
                    self.device_info['name'],
                    self.layout_type,
                    self.code_distance,
                    self.device_info.get('provider'),
                    self.config_overrides
                )
                print('[DEBUG] Mapping step result:', result)
                # --- PATCH: inject qubit_positions into device_info if present ---
                mapping_info = result.get('mapping_info') if result else None
                qubit_positions = None
                try:
                    mi = mapping_info if isinstance(mapping_info, dict) else {}
                    mpl = mi.get('multi_patch_layout') if isinstance(mi, dict) else None
                    patches = len(mpl) if isinstance(mpl, dict) else 0
                    print(f"[DEBUG] Mapping: status={result.get('status') if isinstance(result, dict) else None}, patches={patches}")
                except Exception:
                    pass
                if mapping_info:
                    # 1. Directly as mapping_info['qubit_positions']
                    if 'qubit_positions' in mapping_info:
                        qubit_positions = mapping_info['qubit_positions'
]
                    # 2. Or as a merged dict from all patches in multi_patch_layout
                    elif 'multi_patch_layout' in mapping_info:
                        # Merge all patch layouts into a single dict
                        merged = {}
                        for patch in mapping_info['multi_patch_layout'].values():
                            if 'layout' in patch:
                                merged.update(patch['layout'])
                        if merged:
                            qubit_positions = merged
                if qubit_positions:
                    self.device_info['qubit_positions'] = qubit_positions
                    print(f"[DEBUG][PATCH] Injected qubit_positions into device_info: {list(qubit_positions.keys())}")
                self.step_results[step_name] = result
                self.step_done.emit("mapping", result)
            elif step_name == "execution":
                self.progress.emit("Executing on hardware...")
                # Use best available circuit for execution
                circuit_to_exec = (
                    self.step_results.get("ft_circuit")
                    or self.step_results.get("optimization")
                    or circuit
                )
                source = (
                    "ft_circuit" if self.step_results.get("ft_circuit") is not None
                    else ("optimization" if self.step_results.get("optimization") is not None else "original")
                )
                print(f"[DEBUG] Execution: using circuit source = {source}")
                result = self.workflow_bridge.executor.run_circuit(circuit_to_exec, self.run_config)
                try:
                    print(f"[DEBUG] Execution: result keys={list(result.keys()) if isinstance(result, dict) else type(result)}")
                except Exception:
                    pass
                self.step_done.emit("execution", result)

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error.emit(str(e))

class CircuitDesignerGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.editor = CircuitEditor()
        self.workflow_bridge = QuantumWorkflowBridge()
        self.config_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../configs'))
        self.provider, self.device = get_provider_and_device(self.config_dir)
        self._init_ui()
        self._workflow_thread = None
        self._workflow_worker = None
        self._pending_workflow = None
        self._workflow_results = {}
        # Set window title to Qcraft - <provider> / <device>
        self.setWindowTitle(f"Qcraft - {self.provider} / {self.device}")
        # Remove sweep_checkbox creation and addition from here
        self.status_label = QLabel("Ready")

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        # Apply dark blue theme inspired palette
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background-color: #0F2747; color: #FFFFFF; }
            QLabel, QCheckBox, QGroupBox { color: #FFFFFF; }
            QPushButton { color: #FFFFFF; border: 1px solid rgba(255,255,255,0.30); background-color: rgba(255,255,255,0.05); padding: 6px 10px; border-radius: 6px; }
            QPushButton:hover { background-color: rgba(255,255,255,0.10); }
            QProgressBar { background-color: rgba(255,255,255,0.08); color: #FFFFFF; border: 1px solid rgba(255,255,255,0.20); border-radius: 6px; text-align: center; }
            QProgressBar::chunk { background-color: #2E86FF; border-radius: 6px; }
            QScrollArea, QTabWidget::pane, QTableWidget, QTreeWidget { background-color: #0F2747; color: #FFFFFF; }
            QHeaderView::section { background-color: rgba(255,255,255,0.06); color: #FFFFFF; }
            """
        )
        h_layout = QHBoxLayout()
        # Left: Gate palette (no editor passed)
        self.gate_palette = GatePalette('configs/gates.yaml', parent=self)
        h_layout.addWidget(self.gate_palette, 0)
        # Center: Circuit canvas (editor passed)
        self.circuit_canvas = CircuitCanvas(self.editor)
        h_layout.addWidget(self.circuit_canvas, 1)
        main_layout.addLayout(h_layout, 1)
        # Workflow controls
        controls = QHBoxLayout()
        self.run_workflow_btn = QPushButton("Run Full Workflow")
        self.cancel_workflow_btn = QPushButton("Cancel")
        self.cancel_workflow_btn.setEnabled(False)
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.status_label = QLabel("Ready")
        # Add config and training buttons
        self.config_btn = QPushButton("Edit Configs")
        self.training_btn = QPushButton("Train Module")
        controls.addWidget(self.run_workflow_btn)
        controls.addWidget(self.cancel_workflow_btn)
        controls.addWidget(self.progress_bar)
        controls.addWidget(self.status_label)
        controls.addWidget(self.config_btn)
        controls.addWidget(self.training_btn)
        main_layout.addLayout(controls)
        # Place sweep checkbox below controls, not in controls
        self.sweep_checkbox = QCheckBox("Sweep code distances (try all up to d_max)")
        self.sweep_checkbox.setChecked(False)
        main_layout.addWidget(self.sweep_checkbox)
        # Connect
        self.run_workflow_btn.clicked.connect(self.start_full_workflow)
        self.cancel_workflow_btn.clicked.connect(self.cancel_full_workflow)
        self.config_btn.clicked.connect(self.open_config_dialog)
        self.training_btn.clicked.connect(self.open_training_dialog)

    def _show_config_dialog(self):
        dlg = ConfigDialog(self)
        dlg.exec()

    # removed unused _show_training_dialog

    def start_full_workflow(self):
        # Load optimization strategy from optimizer_config.yaml
        import yaml
        optimizer_config_path = os.path.join(self.config_dir, 'optimizer_config.yaml')
        with open(optimizer_config_path, 'r') as f:
            optimizer_config = yaml.safe_load(f)
        optimization_method = optimizer_config.get('optimization_strategy', 'rule_based')
        # Always load full device info from YAML
        from hardware_abstraction.device_abstraction import DeviceAbstraction
        provider, device_name = get_provider_and_device(self.config_dir)
        device_info = DeviceAbstraction.get_device_info(provider, device_name)
        # Set up other workflow parameters as before
        layout_type = self.editor.config.get('layout_type', 'rotated')
        code_distance = self.editor.config.get('code_distance', 3)
        run_config = {}
        config_overrides = {}
        # Create and start the workflow worker
        self._workflow_worker = WorkflowWorker(self.editor, config_dir=self.config_dir)
        # Do NOT set parent here! (Fix for QObject::moveToThread error)
        self._workflow_worker.set_parameters(
            device_info,
            layout_type,
            code_distance,
            run_config,
            config_overrides,
            optimization_method
        )
        self._workflow_thread = QThread(self)
        self._workflow_worker.moveToThread(self._workflow_thread)
        self._workflow_thread.started.connect(self._workflow_worker.run)
        self._workflow_worker.progress.connect(self.on_workflow_progress)
        self._workflow_worker.finished.connect(self.on_workflow_finished)
        self._workflow_worker.error.connect(self.on_workflow_error)
        self._workflow_worker.step_done.connect(self.on_workflow_step_done)
        self._workflow_thread.start()

    def cancel_full_workflow(self):
        if self._workflow_worker:
            self._workflow_worker.cancel()
        self.status_label.setText("Workflow cancelled.")
        self.run_workflow_btn.setEnabled(True)
        self.cancel_workflow_btn.setEnabled(False)

    def on_workflow_progress(self, message):
        self.status_label.setText(message)
        step_map = {
            "Generating surface code layout...": 10,
            "Transforming to fault-tolerant circuit...": 30,
            "Applying code switching...": 50,
            "Optimizing circuit...": 70,
            "Mapping logical to physical qubits...": 85,
            "Executing on hardware...": 95,
        }
        self.progress_bar.setValue(step_map.get(message, 0))

    def on_workflow_finished(self, job_id):
        self.status_label.setText(f"Workflow complete. Job ID: {job_id}")
        self.progress_bar.setValue(100)
        self.run_workflow_btn.setEnabled(True)
        self.cancel_workflow_btn.setEnabled(False)
        if self._workflow_thread is not None:
            self._workflow_thread.quit()
            self._workflow_thread.wait()
            self._workflow_thread.deleteLater()
            self._workflow_thread = None
        if self._workflow_worker is not None:
            self._workflow_worker.deleteLater()
            self._workflow_worker = None

    def closeEvent(self, event):
        # Clean up workflow thread if running
        if hasattr(self, '_workflow_thread') and self._workflow_thread is not None:
            if self._workflow_thread.isRunning():
                self._workflow_thread.quit()
                self._workflow_thread.wait()
            self._workflow_thread = None
        if hasattr(self, '_workflow_worker') and self._workflow_worker is not None:
            self._workflow_worker.deleteLater()
            self._workflow_worker = None
        event.accept()

    def on_workflow_error(self, error_msg):
        QMessageBox.critical(self, "Workflow Error", error_msg)
        self.status_label.setText("Error occurred.")
        self.run_workflow_btn.setEnabled(True)
        self.cancel_workflow_btn.setEnabled(False)
        if self._workflow_thread is not None:
            self._workflow_thread.quit()
            self._workflow_thread.wait()
            self._workflow_thread.deleteLater()
            self._workflow_thread = None
        if self._workflow_worker is not None:
            self._workflow_worker.deleteLater()
            self._workflow_worker = None


    def on_workflow_step_done(self, step_name, result):
        """Handle completion of a workflow step"""
        print(f"[DEBUG] on_workflow_step_done called with step_name: {step_name}")
        
        # Store the result for the next step
        self._workflow_results[step_name] = result
        
        # Initialize variables
        circuit = None
        mapping_info = None
        layout_result = None
        
        # Update UI based on step
        if step_name == "optimization":
            circuit = result
            # Show optimization strategy/fallback in status label if available
            try:
                info = (result or {}).get('optimization_info', {}) if isinstance(result, dict) else {}
                strat = info.get('strategy_used')
                fb = info.get('fallback_reason')
                if strat and fb:
                    self.status_label.setText(f"Optimization used '{strat}' (fallback: {fb})")
                elif strat:
                    self.status_label.setText(f"Optimization strategy: {strat}")
            except Exception:
                pass
        elif step_name == "layout":
            layout_result = result
        elif step_name == "ft_circuit":
            circuit = result
        elif step_name == "code_switcher":
            # Optionally handle additional code switching logic if needed
            pass
        elif step_name == "mapping":
            # Unwrap mapping_info if wrapped
            if isinstance(result, dict) and 'mapping_info' in result:
                mapping_info = result['mapping_info']
                layout_result = mapping_info  # For multi-patch, layout is in mapping_info
            else:
                mapping_info = result
                layout_result = result
            circuit = result
        # Step result summaries
        try:
            if step_name == "layout" and isinstance(result, dict):
                mpl = result.get('multi_patch_layout')
                patches = len(mpl) if isinstance(mpl, dict) else 0
                print(f"[DEBUG][GUI] Layout step summary: patches={patches}, keys={list(result.keys())}")
            elif step_name == "mapping" and isinstance(result, dict):
                status = result.get('status')
                err = result.get('error')
                mi = mapping_info if isinstance(mapping_info, dict) else {}
                l2p = mi.get('logical_to_physical') if isinstance(mi, dict) else None
                lq = len(l2p) if isinstance(l2p, dict) else 0
                print(f"[DEBUG][GUI] Mapping step summary: status={status}, logical_patches={lq}, error={err}")
            elif step_name == "optimization" and isinstance(result, dict):
                info = result.get('optimization_info', {})
                print(f"[DEBUG][GUI] Optimization summary: strategy={info.get('strategy_used')}, fallback_reason={info.get('fallback_reason')}")
            elif step_name == "execution":
                keys = list(result.keys()) if isinstance(result, dict) else str(type(result))
                print(f"[DEBUG][GUI] Execution step summary: keys={keys}")
        except Exception:
            pass
        
        # If mapping failed, stop workflow immediately
        if step_name == "mapping" and isinstance(result, dict) and (result.get('status') == 'failed' or 'error' in result):
            err = result.get('error') or 'Mapping failed.'
            QMessageBox.critical(self, "Mapping Failed", err)
            self._stop_workflow()
            return

        # Special handling for ft_circuit: present choice dialog after FT circuit step only (before any cleanup)
        if step_name == "ft_circuit":
            # Do not show FT-ready dialog if FT circuit failed
            if isinstance(result, dict) and (result.get('status') == 'failed' or 'error' in result):
                err = result.get('error') or 'Fault-tolerant circuit generation failed.'
                QMessageBox.critical(self, "FT Circuit Error", err)
                self._stop_workflow()
                return
            choice_dialog = FTCircuitChoiceDialog(self)
            user_choice = {'optimize': False, 'execute_direct': False}
            def _choose_optimize():
                user_choice['optimize'] = True
            def _choose_execute():
                user_choice['execute_direct'] = True
            choice_dialog.optimize_and_execute.connect(_choose_optimize)
            choice_dialog.execute_directly.connect(_choose_execute)
            choice_dialog.exec()
            # Branch workflow based on user choice
            if user_choice['optimize']:
                # Jump to optimization step by name
                if self._workflow_worker is not None:
                    self._workflow_worker.jump_to_step("optimization")
                self._run_next_step()
            elif user_choice['execute_direct']:
                # Jump to execution step by name
                if self._workflow_worker is not None:
                    self._workflow_worker.jump_to_step("execution")
                self._run_next_step()
            else:
                # Cancel or close: stop workflow
                self._stop_workflow()
            return

        print(f"[DEBUG] Creating StepResultDialog for step: {step_name}")
        # Store dialog as instance variable to prevent garbage collection
        self._active_dialog = StepResultDialog(
            self, 
            title=f"{step_name.capitalize()} Result", 
            result_data=layout_result if step_name == "mapping" else result, 
            circuit=circuit, 
            mapping_info=mapping_info, 
            step_name=step_name
        )
        self._active_dialog.proceed_signal.connect(self._run_next_step)
        self._active_dialog.stop_signal.connect(self._stop_workflow)
        self._active_dialog.exec()
        # After dialog closes, check if workflow was stopped or finished, cleanup if needed
        if self._workflow_thread is not None and not self._workflow_thread.isRunning():
            self._workflow_thread.deleteLater()
            self._workflow_thread = None
        if self._workflow_worker is not None and not self._workflow_thread:
            self._workflow_worker.deleteLater()
            self._workflow_worker = None


    def _stop_workflow(self):
        self.status_label.setText("Workflow stopped.")
        self.run_workflow_btn.setEnabled(True)
        self.cancel_workflow_btn.setEnabled(False)
        if self._workflow_thread is not None:
            self._workflow_thread.quit()
            self._workflow_thread.wait()
            self._workflow_thread.deleteLater()
            self._workflow_thread = None
        if self._workflow_worker is not None:
            self._workflow_worker.deleteLater()
            self._workflow_worker = None


    def open_config_dialog(self):
        dlg = ConfigDialog(self, bridge=self.workflow_bridge)
        dlg.setWindowTitle("Configuration Editor")
        dlg.exec()

    def open_training_dialog(self):
        dlg = TrainingDialog(self, bridge=self.workflow_bridge, get_circuit_func=self.editor.get_circuit)
        dlg.setWindowTitle("Train Module")
        dlg.exec()

    def _run_next_step(self):
        """Run the next step in the workflow"""
        print("[DEBUG] Running next workflow step")
        if hasattr(self, '_workflow_worker') and self._workflow_worker is not None:
            try:
                self._workflow_worker.proceed()
            except ValueError as e:
                # Show a user-friendly error dialog for mapping errors
                QMessageBox.critical(self, "Mapping Error", str(e))
                self.status_label.setText("Mapping error: " + str(e))
                self.run_workflow_btn.setEnabled(True)
                self.cancel_workflow_btn.setEnabled(False)
                if self._workflow_thread:
                    self._workflow_thread.quit()
                    self._workflow_thread.wait()
            except UnboundLocalError as e:
                # Handle unbound local variable errors (e.g., 'layout')
                QMessageBox.critical(self, "Workflow Error", f"Internal error: {str(e)}. Please check mapping/layout assignment.")
                self.status_label.setText("Error occurred: " + str(e))
                self.run_workflow_btn.setEnabled(True)
                self.cancel_workflow_btn.setEnabled(False)
                if self._workflow_thread:
                    self._workflow_thread.quit()
                    self._workflow_thread.wait()
            except Exception as e:
                # Fallback for any other error
                QMessageBox.critical(self, "Workflow Error", str(e))
                self.status_label.setText("Error occurred: " + str(e))
                self.run_workflow_btn.setEnabled(True)
                self.cancel_workflow_btn.setEnabled(False)
                if self._workflow_thread:
                    self._workflow_thread.quit()
                    self._workflow_thread.wait()
        else:
            print("[WARNING] No workflow worker available to proceed")
            self.status_label.setText("Workflow completed or not running.")
            self.run_workflow_btn.setEnabled(True)
            self.cancel_workflow_btn.setEnabled(False)

def main():
    import sys
    app = QApplication(sys.argv)
    window = CircuitDesignerGUI()
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main() 