from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
from PySide6.QtCore import Signal

class FTCircuitChoiceDialog(QDialog):
    optimize_and_execute = Signal()
    execute_directly = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Fault-Tolerant Circuit Ready")
        self.setMinimumSize(400, 180)
        layout = QVBoxLayout(self)
        label = QLabel("The fault-tolerant circuit has been generated.\n\nWhat would you like to do next?")
        label.setWordWrap(True)
        layout.addWidget(label)

        button_layout = QHBoxLayout()
        self.optimize_btn = QPushButton("Optimize and Execute")
        self.execute_btn = QPushButton("Execute Directly")
        self.cancel_btn = QPushButton("Cancel Workflow")

        self.optimize_btn.clicked.connect(self._optimize_and_execute)
        self.execute_btn.clicked.connect(self._execute_directly)
        self.cancel_btn.clicked.connect(self.reject)

        button_layout.addWidget(self.optimize_btn)
        button_layout.addWidget(self.execute_btn)
        button_layout.addWidget(self.cancel_btn)
        layout.addLayout(button_layout)

    def _optimize_and_execute(self):
        self.optimize_and_execute.emit()
        self.accept()

    def _execute_directly(self):
        self.execute_directly.emit()
        self.accept()
