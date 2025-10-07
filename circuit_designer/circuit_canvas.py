import os
import importlib.resources
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGraphicsView, QGraphicsScene, QPushButton, QFrame, QGraphicsRectItem, QMenu, QInputDialog, QMessageBox
from PySide6.QtCore import Qt, QPointF, QSize
from PySide6.QtGui import QPainter, QPen, QColor, QFont, QKeyEvent, QIcon, QPixmap
import yaml

class CircuitGraphicsView(QGraphicsView):
    def __init__(self, parent=None, canvas=None):
        super().__init__(parent)
        self.canvas = canvas
        self.setAcceptDrops(True)
    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-gate") or event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()
    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat("application/x-gate") or event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()
    def dropEvent(self, event):
        if self.canvas:
            self.canvas.handle_drop_event(event, self)
    def mousePressEvent(self, event):
        if self.canvas and self.canvas.pending_two_qubit_gate:
            self.canvas.handle_second_qubit_selection(event)
        else:
            super().mousePressEvent(event)

class CircuitCanvas(QWidget):
    def __init__(self, editor, config_path='configs/editor_config.yaml', parent=None):
        super().__init__(parent)
        self.editor = editor
        self.config = self._load_config(config_path)
        self.pending_two_qubit_gate = None  # {'gate_name': str, 'first_q_idx': int, 'first_qubit_label': str, 't': int}
        self.highlighted_wires = set()
        self._setup_ui()
        self._draw_circuit()
        self.setAcceptDrops(True)
        self.dragged_gate = None
        self.gate_items = []  # Track gate graphics for selection/removal
        self.pending_measure_gate = None  # {'qubit': int, 'time': int}
    def _load_config(self, path):
        fname = os.path.basename(path)
        try:
            with importlib.resources.open_text('configs', fname) as f:
                return yaml.safe_load(f)
        except (FileNotFoundError, ModuleNotFoundError):
            with open(path, 'r') as f:
                return yaml.safe_load(f)
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        # Controls (add/remove qubit, add/remove clbit, export, zoom)
        controls = QHBoxLayout()
        self.add_qubit_btn = QPushButton("+")
        self.remove_qubit_btn = QPushButton("-")
        self.add_clbit_btn = QPushButton("+c")
        self.remove_clbit_btn = QPushButton("-c")
        self.export_btn = QPushButton("E")
        self.zoom_in_btn = QPushButton("")
        self.zoom_out_btn = QPushButton("")
        self.reset_view_btn = QPushButton("")
        # Set SVG icons for zoom controls
        self._apply_icon(self.zoom_in_btn, 'zoom_in.svg', 'Zoom In')
        self._apply_icon(self.zoom_out_btn, 'zoom_out.svg', 'Zoom Out')
        self._apply_icon(self.reset_view_btn, 'zoom_reset.svg', 'Reset Zoom')
        # Make zoom buttons more prominent
        for b in (self.zoom_in_btn, self.zoom_out_btn, self.reset_view_btn):
            b.setFixedSize(36, 32)
            b.setStyleSheet(
                "QPushButton { color: #FFFFFF; border: 1px solid rgba(255,255,255,0.30); background-color: rgba(255,255,255,0.05); border-radius: 6px; }"
                "QPushButton:hover { background-color: rgba(255,255,255,0.10); }"
            )
        for btn in [self.add_qubit_btn, self.remove_qubit_btn, self.add_clbit_btn, self.remove_clbit_btn, self.export_btn, self.zoom_in_btn, self.zoom_out_btn, self.reset_view_btn]:
            controls.addWidget(btn)
        controls.addStretch()
        layout.addLayout(controls)
        # Graphics view/scene
        self.scene = QGraphicsScene()
        self.view = CircuitGraphicsView(self, canvas=self)
        self.view.setScene(self.scene)
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setDragMode(QGraphicsView.ScrollHandDrag)
        self.view.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.view.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        # Dark blue background
        self.view.setBackgroundBrush(QColor('#0F2747'))
        layout.addWidget(self.view, 1)
        # Connect controls
        self.add_qubit_btn.clicked.connect(self._add_qubit)
        self.remove_qubit_btn.clicked.connect(self._remove_qubit)
        self.add_clbit_btn.clicked.connect(self._add_clbit)
        self.remove_clbit_btn.clicked.connect(self._remove_clbit)
        self.zoom_in_btn.clicked.connect(self._zoom_in)
        self.zoom_out_btn.clicked.connect(self._zoom_out)
        self.reset_view_btn.clicked.connect(self._reset_view)

    def _apply_icon(self, button: QPushButton, asset_name: str, tooltip: str = ""):
        """Load an icon from assets and apply to a button, with fallback to text if missing."""
        try:
            from importlib.resources import files
            try:
                asset = files('assets').joinpath(asset_name)
                # Prefer path if available
                icon = QIcon(str(asset))
            except Exception:
                # Fallbacks: repo-relative assets and CWD assets
                repo_rel = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'assets', asset_name))
                icon = QIcon(repo_rel)
                if icon.isNull():
                    local_path = os.path.join('assets', asset_name)
                    icon = QIcon(local_path)
        except Exception:
            # Ultimate fallback: try repo-relative then CWD
            repo_rel = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'assets', asset_name))
            icon = QIcon(repo_rel)
            if icon.isNull():
                local_path = os.path.join('assets', asset_name)
                icon = QIcon(local_path)
        if not icon.isNull():
            button.setIcon(icon)
            button.setIconSize(QSize(22, 22))
        if tooltip:
            button.setToolTip(tooltip)
    def _draw_circuit(self):
        self.scene.clear()
        self.gate_items = []  # Track gate graphics for selection/removal
        qubits = self.editor.circuit['qubits']
        clbits = self.editor.circuit.get('clbits', [])
        gates = self.editor.circuit['gates']
        grid_size = self.config.get('grid_size', 40)
        color_scheme = self.config.get('color_scheme', {'wire': '#FFFFFF'})
        # Draw qubit wires
        for i, q in enumerate(qubits):
            y = 50 + i * grid_size
            pen = QPen(QColor(color_scheme.get('wire', '#FFFFFF')), 2)
            if i in self.highlighted_wires:
                pen.setColor(QColor('#2E86FF'))
                pen.setWidth(4)
            self.scene.addLine(50, y, 800, y, pen)
            label = self.scene.addText(f"q{q}", QFont("Arial", 10))
            label.setDefaultTextColor(QColor('#FFFFFF'))
            label.setPos(10, y - 10)
        # Draw classical wires
        for i, c in enumerate(clbits):
            y = 50 + (len(qubits) + i) * grid_size
            pen = QPen(QColor('#FFFFFF'), 2, Qt.DashLine)
            self.scene.addLine(50, y, 800, y, pen)
            label = self.scene.addText(f"c{c}", QFont("Arial", 10))
            label.setDefaultTextColor(QColor('#FFFFFF'))
            label.setPos(10, y - 10)
        # Draw gates
        for g in gates:
            t = g['time']
            qubit_idxs = [qubits.index(q) for q in g['qubits'] if q in qubits]
            x = 100 + t * grid_size
            if g['name'] == 'MEASURE' and 'clbits' in g:
                # Draw measurement box on qubit wire
                if len(qubit_idxs) == 1:
                        yq = 50 + qubit_idxs[0] * grid_size
                        rect = QGraphicsRectItem(x, yq - 15, 30, 30)
                        rect.setBrush(Qt.transparent)
                        rect.setPen(QPen(QColor('#FFFFFF')))
                        rect.setFlag(QGraphicsRectItem.ItemIsSelectable, True)
                        rect.setFlag(QGraphicsRectItem.ItemIsFocusable, True)
                        rect.setData(0, g.get('id', None))
                        self.scene.addItem(rect)
                        self.gate_items.append(rect)
                        label = self.scene.addText('M', QFont("Arial", 10, QFont.Bold))
                        label.setDefaultTextColor(QColor('#FFFFFF'))
                        label.setPos(x + 5, yq - 10)
                        # Draw connection to classical wire
                        clbit_idx = clbits.index(g['clbits'][0]) if g['clbits'][0] in clbits else 0
                        yc = 50 + (len(qubits) + clbit_idx) * grid_size
                        self.scene.addLine(x + 15, yq + 15, x + 15, yc, QPen(QColor('#FFFFFF'), 2, Qt.DashLine))
            elif len(qubit_idxs) == 1:
                # Single-qubit gate
                y = 50 + qubit_idxs[0] * grid_size
                rect = QGraphicsRectItem(x, y - 15, 30, 30)
                rect.setBrush(Qt.transparent)
                rect.setPen(QPen(QColor('#FFFFFF')))
                rect.setFlag(QGraphicsRectItem.ItemIsSelectable, True)
                rect.setFlag(QGraphicsRectItem.ItemIsFocusable, True)
                rect.setData(0, g.get('id', None))
                self.scene.addItem(rect)
                self.gate_items.append(rect)
                label = self.scene.addText(g['name'], QFont("Arial", 10, QFont.Bold))
                label.setDefaultTextColor(QColor('#FFFFFF'))
                label.setPos(x + 5, y - 10)
            elif len(qubit_idxs) == 2:
                # Two-qubit gate: box for control, dot for target, connect with line
                control_idx, target_idx = qubit_idxs[0], qubit_idxs[1]
                y_control = 50 + control_idx * grid_size
                y_target = 50 + target_idx * grid_size
                rect = QGraphicsRectItem(x, y_control - 15, 30, 30)
                rect.setBrush(Qt.transparent)
                rect.setPen(QPen(QColor('#FFFFFF')))
                rect.setFlag(QGraphicsRectItem.ItemIsSelectable, True)
                rect.setFlag(QGraphicsRectItem.ItemIsFocusable, True)
                rect.setData(0, g.get('id', None))
                self.scene.addItem(rect)
                self.gate_items.append(rect)
                label = self.scene.addText(g['name'], QFont("Arial", 10, QFont.Bold))
                label.setDefaultTextColor(QColor('#FFFFFF'))
                label.setPos(x + 5, y_control - 10)
                dot_radius = 7
                dot = self.scene.addEllipse(x + 15 - dot_radius, y_target - dot_radius, 2 * dot_radius, 2 * dot_radius, QPen(QColor('#FFFFFF')), QColor('#FFFFFF'))
                dot.setData(0, g.get('id', None))
                self.gate_items.append(dot)
                self.scene.addLine(x + 15, y_control, x + 15, y_target, QPen(QColor('#FFFFFF'), 2, Qt.SolidLine))
            else:
                continue
        self.scene.contextMenuEvent = self._context_menu_event
    def _add_qubit(self):
        self.editor.add_qubit()
        self._draw_circuit()
    def _remove_qubit(self):
        if self.editor.circuit['qubits']:
            self.editor.remove_qubit(self.editor.circuit['qubits'][-1])
            self._draw_circuit()
    def _add_clbit(self):
        self.editor.add_clbit()
        self._draw_circuit()
    def _remove_clbit(self):
        if self.editor.circuit.get('clbits', []):
            self.editor.remove_clbit(self.editor.circuit['clbits'][-1])
            self._draw_circuit()
    def _zoom_in(self):
        self.view.scale(1.15, 1.15)
    def _zoom_out(self):
        self.view.scale(1/1.15, 1/1.15)
    def _reset_view(self):
        self.view.resetTransform()
    def _prompt_select_clbit(self, default_index: int = 0) -> int:
        """Prompt the user to select a classical bit index. Returns the selected clbit or -1 if cancelled."""
        clbits = self.editor.circuit.get('clbits', [])
        # If there are no classical bits, offer to create one
        if not clbits:
            res = QMessageBox.question(self, "No classical bits", "No classical bits exist. Create one now?", QMessageBox.Yes | QMessageBox.No)
            if res == QMessageBox.Yes:
                self.editor.add_clbit()
                clbits = self.editor.circuit.get('clbits', [])
                self._draw_circuit()
            else:
                return -1
        items = [f"c{c}" for c in clbits]
        # Clamp default index
        if default_index < 0 or default_index >= len(items):
            default_index = 0
        ok, ok_pressed = QInputDialog.getItem(self, "Select classical bit", "Target classical bit:", items, current=default_index, editable=False)
        if not ok_pressed:
            return -1
        try:
            # item is like 'c3' -> 3
            return int(str(ok).lstrip('c'))
        except Exception:
            return -1
    def handle_drop_event(self, event, view):
        mime_data = event.mimeData()
        gate_name = None
        if mime_data.hasFormat("application/x-gate"):
            gate_name = str(mime_data.data("application/x-gate").data(), encoding='utf-8')
        elif mime_data.hasText():
            gate_name = mime_data.text()
        if not gate_name:
            event.ignore()
            return
        if hasattr(event, 'position'):
            widget_pos = event.position().toPoint()
        else:
            widget_pos = event.pos()
        scene_pos = view.mapToScene(view.mapFromGlobal(view.viewport().mapToGlobal(widget_pos)))
        x, y = scene_pos.x(), scene_pos.y()
        qubits = self.editor.circuit['qubits']
        clbits = self.editor.circuit.get('clbits', [])
        grid_size = self.config.get('grid_size', 40)
        qubit_distances = [(i, abs(y - (50 + i * grid_size))) for i in range(len(qubits))]
        qubit_distances.sort(key=lambda t: t[1])
        gate_arity = 1
        for g in self.editor.palette.get_gates():
            if g['name'] == gate_name:
                gate_arity = g.get('arity', 1)
                break
        t = max(0, int(round((x - 100) / grid_size)))
        try:
            if gate_name == 'MEASURE':
                # Determine nearest qubit and propose matching classical bit index if available
                q_idx = qubit_distances[0][0]
                qubit = qubits[q_idx]
                default_cidx = q_idx if q_idx < len(clbits) else 0
                selected_clbit = self._prompt_select_clbit(default_cidx)
                if selected_clbit == -1:
                    event.ignore()
                    return
                self.editor.add_gate(gate_name, qubit, t, clbits=[selected_clbit])
                self._draw_circuit()
                event.acceptProposedAction()
            elif gate_arity == 1:
                q_idx = qubit_distances[0][0]
                qubit = qubits[q_idx]
                self.editor.add_gate(gate_name, qubit, t)
                self._draw_circuit()
                event.acceptProposedAction()
            elif gate_arity == 2:
                if len(qubits) < 2:
                    event.ignore()
                    return
                first_q_idx = qubit_distances[0][0]
                first_qubit_label = qubits[first_q_idx]
                self.pending_two_qubit_gate = {'gate_name': gate_name, 'first_q_idx': first_q_idx, 'first_qubit_label': first_qubit_label, 't': t}
                self.highlighted_wires = set(i for i in range(len(qubits)) if i != first_q_idx)
                self._draw_circuit()
                event.acceptProposedAction()
            else:
                event.ignore()
        except Exception as e:
            print(f"Error adding gate: {e}")
            event.ignore()
    def _context_menu_event(self, event):
        item = self.scene.itemAt(event.scenePos(), self.view.transform())
        if isinstance(item, QGraphicsRectItem) and item.isSelected():
            menu = QMenu()
            remove_action = menu.addAction("Remove Gate")
            action = menu.exec_(event.screenPos())
            if action == remove_action:
                gate_id = item.data(0)
                self.editor.remove_gate(gate_id)
                self._draw_circuit()
    def handle_second_qubit_selection(self, event):
        # User is selecting the second qubit
        pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
        scene_pos = self.view.mapToScene(self.view.mapFromGlobal(self.view.viewport().mapToGlobal(pos)))
        y = scene_pos.y()
        qubits = self.editor.circuit['qubits']
        grid_size = self.config.get('grid_size', 40)
        wire_ys = [50 + i * grid_size for i in range(len(qubits))]
        qubit_distances = [(i, abs(y - wire_y)) for i, wire_y in enumerate(wire_ys)]
        qubit_distances.sort(key=lambda t: t[1])
        second_q_idx, min_dist = qubit_distances[0]
        print(f"[DEBUG] Click y={y}, wire_ys={wire_ys}, selected second_q_idx={second_q_idx}, min_dist={min_dist}")
        for i, wire_y in enumerate(wire_ys):
            print(f"[DEBUG] Qubit {i}: wire_y={wire_y}, |y-wire_y|={abs(y-wire_y)}")
        snap_threshold = grid_size
        first_q_idx = self.pending_two_qubit_gate['first_q_idx']
        first_qubit_label = self.pending_two_qubit_gate['first_qubit_label']
        print(f"[DEBUG] First qubit index: {first_q_idx}, label: {first_qubit_label}")
        if min_dist < snap_threshold and second_q_idx != first_q_idx:
            second_qubit_label = qubits[second_q_idx]
            qubit_pair = [first_qubit_label, second_qubit_label]
            gate_name = self.pending_two_qubit_gate['gate_name']
            t = self.pending_two_qubit_gate['t']
            print(f"[DEBUG] Adding two-qubit gate: {gate_name}, qubits={qubit_pair}, t={t}")
            try:
                self.editor.add_multi_qubit_gate(gate_name, qubit_pair, t)
            except Exception as e:
                print(f"Error adding multi-qubit gate: {e}")
            self.pending_two_qubit_gate = None
            self.highlighted_wires = set()
            self._draw_circuit()
        else:
            print(f"[DEBUG] Click ignored: min_dist={min_dist}, snap_threshold={snap_threshold}, second_q_idx={second_q_idx}, first_q_idx={first_q_idx}")
    def keyPressEvent(self, event: QKeyEvent):
        if self.pending_two_qubit_gate and event.key() == Qt.Key_Escape:
            # Cancel pending two-qubit gate
            self.pending_two_qubit_gate = None
            self.highlighted_wires = set()
            self._draw_circuit()
        elif event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            # Remove selected gate
            for item in self.gate_items:
                if item.isSelected():
                    gate_id = item.data(0)
                    self.editor.remove_gate(gate_id)
                    self._draw_circuit()
                    break
        else:
            super().keyPressEvent(event) 