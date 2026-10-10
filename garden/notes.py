"""A persistent paper note; hiding the note never closes the garden."""
from __future__ import annotations
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget


class _NoteHeader(QFrame):
    def __init__(self, note):
        super().__init__(note)
        self.note = note
        self._press = None
        self._origin = None
        self.setCursor(Qt.OpenHandCursor)
        self.setToolTip('拖动便签；取消固定后可调整位置')

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self.note.state.pinned:
            self._press = event.globalPosition().toPoint()
            self._origin = self.note.pos()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._press is not None and event.buttons() & Qt.LeftButton and not self.note.state.pinned:
            target = self._origin+event.globalPosition().toPoint()-self._press
            self.note.move_within_bounds(target)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._press is not None:
            self.note.remember_position()
        self._press = None
        super().mouseReleaseEvent(event)


class NoteWidget(QWidget):
    changed = Signal()

    def __init__(self, state, bounds_provider, parent=None):
        super().__init__(parent)
        self.state = state
        self._bounds_provider = bounds_provider
        self._closing = False
        self.setObjectName('gardenNote')
        self.setWindowTitle('春庭 · 便签')
        if parent is None:
            self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFont(QFont('Noto Sans CJK SC', 10))
        self.setFixedSize(330, 285)
        self.setStyleSheet('''
            QFrame#notePaper { background: #FCF6DE; border: 1px solid #E1D6AF; border-radius: 16px; }
            QFrame { background: transparent; border: none; }
            QLabel { color: #796D4C; background: transparent; border: none; }
            QLabel#noteTitle { font-family: 'Noto Serif CJK SC'; font-size: 18px; }
            QLabel#noteStatus { font-size: 10px; color: #A49977; }
            QPlainTextEdit { background: transparent; color: #5F604B; border: none; padding: 4px; selection-background-color: #DDE4BE; }
            QPushButton { color: #807454; background: transparent; border: 1px solid #DED4B0; border-radius: 8px; padding: 5px 8px; font-size: 11px; }
            QPushButton:hover { background: #EEE7C8; }
            QPushButton:checked { background: #DBE4C4; border-color: #B6C49A; color: #56724C; }
            QPushButton:focus { border-color: #8C9F75; }
        ''')
        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        paper = QFrame()
        paper.setObjectName('notePaper')
        outer.addWidget(paper)
        layout = QVBoxLayout(paper)
        layout.setContentsMargins(15, 13, 15, 10)
        layout.setSpacing(8)
        self.header = _NoteHeader(self)
        row = QHBoxLayout(self.header)
        row.setContentsMargins(0, 0, 0, 0)
        title = QLabel('庭间便签')
        title.setObjectName('noteTitle')
        title.setAttribute(Qt.WA_TransparentForMouseEvents)
        row.addWidget(title, 1)
        self.pin_button = QPushButton('固定')
        self.pin_button.setObjectName('pinNoteButton')
        self.pin_button.setCheckable(True)
        self.pin_button.setToolTip('固定后保持显示在上层，并锁定拖动位置；再次点击解除')
        self.pin_button.toggled.connect(self.set_pinned)
        row.addWidget(self.pin_button)
        self.hide_button = QPushButton('隐藏')
        self.hide_button.setObjectName('hideNoteButton')
        self.hide_button.setToolTip('隐藏便签并保留内容，可从春庭面板重新打开')
        self.hide_button.clicked.connect(self.hide_note)
        row.addWidget(self.hide_button)
        layout.addWidget(self.header)
        self.editor = QPlainTextEdit()
        self.editor.setObjectName('noteEditor')
        self.editor.setAccessibleName('便签内容')
        self.editor.setPlaceholderText('写下今天想做的事，\n或留给明天的一句话……')
        self.editor.setTabChangesFocus(True)
        self.editor.setPlainText(state.text)
        self.editor.textChanged.connect(self._text_changed)
        layout.addWidget(self.editor, 1)
        self.status = QLabel('内容自动保存 · 隐藏后仍会保留')
        self.status.setObjectName('noteStatus')
        layout.addWidget(self.status)
        self.pin_button.setChecked(state.pinned)
        self.reposition()

    def _text_changed(self):
        self.state.text = self.editor.toPlainText()
        self.status.setText('正在保存…')
        self.changed.emit()

    def reposition(self):
        bounds = self._bounds_provider()
        if bounds is None:
            return
        self.setFixedSize(min(330, bounds.width()), min(285, bounds.height()))
        self.move(bounds.left()+round(max(0, bounds.width()-self.width())*self.state.x),
                  bounds.top()+round(max(0, bounds.height()-self.height())*self.state.y))

    def move_within_bounds(self, position):
        bounds = self._bounds_provider()
        self.move(max(bounds.left(), min(position.x(), bounds.right()-self.width()+1)),
                  max(bounds.top(), min(position.y(), bounds.bottom()-self.height()+1)))

    def remember_position(self):
        bounds = self._bounds_provider()
        self.state.x = max(0, min(1, (self.x()-bounds.left())/max(1, bounds.width()-self.width())))
        self.state.y = max(0, min(1, (self.y()-bounds.top())/max(1, bounds.height()-self.height())))
        self.changed.emit()

    def show_note(self, focus=True):
        if self._closing:
            return
        self.state.visible = True
        self.reposition()
        self.show()
        self.raise_()
        if focus:
            self.activateWindow()
            self.editor.setFocus()
        self.changed.emit()

    def hide_note(self):
        self.state.visible = False
        self.hide()
        self.changed.emit()

    def set_pinned(self, pinned):
        self.state.pinned = bool(pinned)
        self.pin_button.blockSignals(True)
        self.pin_button.setChecked(pinned)
        self.pin_button.setText('已固定' if pinned else '固定')
        self.pin_button.blockSignals(False)
        if self.parentWidget() is None:
            self.setWindowFlag(Qt.WindowStaysOnTopHint, pinned)
            if self.state.visible:
                self.show()
        if pinned:
            self.raise_()
        self.header.setCursor(Qt.ArrowCursor if pinned else Qt.OpenHandCursor)
        self.changed.emit()

    def set_save_status(self, success):
        self.status.setText('已保存 · 隐藏后仍会保留' if success else '保存失败，请检查存档路径或磁盘空间')

    def close_for_shutdown(self):
        self._closing = True
        self.close()

    def closeEvent(self, event):
        # Preserve visibility on application quit, but hide on the note's own X.
        if not self._closing:
            self.state.visible = False
            self.changed.emit()
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide_note()
            event.accept()
        else:
            super().keyPressEvent(event)
