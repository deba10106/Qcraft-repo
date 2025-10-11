# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2025 Dr. Debasis Mondal <deba10106@gmail.com>

import os
import importlib.resources
from PySide6.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QLabel, QGroupBox, QFrame
from PySide6.QtCore import Qt, QMimeData
from PySide6.QtGui import QDrag, QPixmap, QPainter, QFont, QColor
from PySide6.QtWidgets import QPushButton
import yaml

class DraggableButton(QPushButton):
    def __init__(self, text, color, text_color, parent=None):
        super().__init__(text, parent)
        self.setFixedSize(70, 38)
        self.setFont(QFont("Arial", 10, QFont.Bold))
        # Let global stylesheet handle colors; provide minimal border to ensure visibility if no global style
        self.setStyleSheet(
            """
            QPushButton { color: #FFFFFF; border: 1px solid rgba(255,255,255,0.30); background-color: rgba(255,255,255,0.05); border-radius: 6px; }
            QPushButton:hover { background-color: rgba(255,255,255,0.10); }
            """
        )
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            drag = QDrag(self)
            mime_data = QMimeData()
            mime_data.setText(self.text())
            drag.setMimeData(mime_data)
            pixmap = QPixmap(self.size())
            pixmap.fill(QColor(200, 200, 255))
            painter = QPainter(pixmap)
            painter.setPen(Qt.black)
            painter.drawText(pixmap.rect(), Qt.AlignCenter, self.text())
            painter.end()
            drag.setPixmap(pixmap)
            drag.setHotSpot(event.pos())
            drag.exec_(Qt.CopyAction | Qt.MoveAction)
        else:
            super().mousePressEvent(event)

class GatePalette(QWidget):
    def __init__(self, gate_config_path='configs/gates.yaml', parent=None):
        super().__init__(parent)
        self.gates = self._load_gates(gate_config_path)
        self._setup_ui()
    def _load_gates(self, path):
        fname = os.path.basename(path)
        try:
            with importlib.resources.open_text('configs', fname) as f:
                return yaml.safe_load(f).get('gates', [])
        except (FileNotFoundError, ModuleNotFoundError):
            with open(path, 'r') as f:
                return yaml.safe_load(f).get('gates', [])
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(15)
        title = QLabel("Quantum Gate Palette")
        title.setFont(QFont("Arial", 11, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #FFFFFF; margin-bottom: 10px;")
        layout.addWidget(title)
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet("background-color: #CCCCCC;")
        layout.addWidget(line)
        # Organize gates by arity
        # Exclude MEASURE/RESET from single-qubit set to avoid duplication; show them only in Measurement & Reset section
        single = [
            g for g in self.gates
            if g.get('arity', 1) == 1 and g.get('name', '').upper() not in ('MEASURE', 'RESET')
        ]
        multi = [g for g in self.gates if g.get('arity', 1) > 1]
        measure = [g for g in self.gates if g['name'].upper() in ('MEASURE', 'RESET')]
        self._add_gate_section(layout, "Single-Qubit Gates", single)
        self._add_gate_section(layout, "Multi-Qubit Gates", multi)
        self._add_gate_section(layout, "Measurement & Reset", measure)
        layout.addStretch()
    def _add_gate_section(self, parent_layout, section_title, gates):
        if not gates:
            return
        container = QWidget()
        container.setStyleSheet(
            """
            QWidget { background-color: rgba(255,255,255,0.04); border-radius: 10px; border: 1px solid rgba(255,255,255,0.15); }
            """
        )
        section_layout = QVBoxLayout(container)
        section_layout.setSpacing(8)
        section_layout.setContentsMargins(8, 10, 8, 10)
        label = QLabel(section_title)
        label.setFont(QFont("Arial", 10, QFont.Bold))
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("color: #FFFFFF; border: none; background: transparent;")
        section_layout.addWidget(label)
        grid = QGridLayout()
        grid.setSpacing(8)
        row, col = 0, 0
        max_cols = 2
        for gate in gates:
            color = gate.get('color', '#CCCCCC')
            text_color = '#FFFFFF' if color.lower() not in ['#ffff00', '#ffd700', '#ff0', '#ffffaa'] else '#000000'
            button = DraggableButton(gate['name'], color, text_color, self)
            grid.addWidget(button, row, col)
            col += 1
            if col >= max_cols:
                col = 0
                row += 1
        section_layout.addLayout(grid)
        parent_layout.addWidget(container) 