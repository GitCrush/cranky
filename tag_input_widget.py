from PyQt6.QtWidgets import QWidget, QLineEdit, QHBoxLayout, QLabel, QPushButton, QCompleter
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent

class TagChip(QWidget):
    def __init__(self, tag, parent_layout):
        super().__init__()
        self.tag = tag
        self.parent_layout = parent_layout

        layout = QHBoxLayout()
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        self.label = QLabel(tag)
        self.label.setStyleSheet("font-weight: bold;")
        self.label.mouseDoubleClickEvent = self.edit_tag

        remove_btn = QPushButton("×")
        remove_btn.setFixedSize(20, 20)
        remove_btn.clicked.connect(self.remove_self)

        layout.addWidget(self.label)
        layout.addWidget(remove_btn)
        self.setLayout(layout)
        self.setStyleSheet("background-color: lightblue; border-radius: 8px;")

    def remove_self(self):
        self.setParent(None)
        self.parent_layout.tags.remove(self.tag)
        self.parent_layout.tagChanged.emit()

    def edit_tag(self, event):
        self.parent_layout.input.setText(self.tag)
        self.remove_self()
        self.parent_layout.input.setFocus()

class TagInputWidget(QWidget):
    tagChanged = pyqtSignal()

    def __init__(self, tag_list):
        super().__init__()
        self.tags = []
        self.tag_list = tag_list

        self.layout = QHBoxLayout(self)
        self.layout.setSpacing(4)
        self.layout.setContentsMargins(4, 4, 4, 4)

        self.input = QLineEdit()
        self.input.setPlaceholderText("Type and press Enter to confirm tag")
        self.input.returnPressed.connect(self.add_tag_from_input)

        self.completer = QCompleter(tag_list)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.activated.connect(self.insert_completion_only)
        self.input.setCompleter(self.completer)

        self.layout.addWidget(self.input)

    def insert_completion_only(self, tag):
        self.input.setText(tag)
        self.input.setFocus()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.input.hasFocus():
                self.add_tag_from_input()
                event.accept()
                return
        super().keyPressEvent(event)

    def add_tag_from_input(self):
        tag = self.input.text().strip()
        if tag and tag not in self.tags:
            chip = TagChip(tag, self)
            self.layout.insertWidget(self.layout.count() - 1, chip)
            self.tags.append(tag)
            self.tagChanged.emit()
        self.input.clear()
        self.input.setFocus()

    def get_tags(self):
        return self.tags

    def clear_tags(self):
        for i in reversed(range(self.layout.count() - 1)):
            widget = self.layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)
        self.tags.clear()
        self.tagChanged.emit()