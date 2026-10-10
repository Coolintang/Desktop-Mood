"""A note-like LAN room with plain-text history and hidden-window unread count."""
from datetime import datetime
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QPushButton
from .notes import NoteWidget


class ChatWidget(NoteWidget):
    unreadChanged = Signal(int)

    def __init__(self, state, bounds_provider, service, parent=None):
        self.unread = 0
        self.service = service
        super().__init__(state, bounds_provider, parent)
        self.setWindowTitle('春庭 · 庭友群聊')
        self.setObjectName('gardenChat')
        self.findChild(QLabel, 'noteTitle').setText('庭友群聊')
        self.header.setToolTip('拖动聊天窗口；固定后锁定位置')
        self.hide_button.setToolTip('隐藏后继续接收消息，春庭入口显示未读数量')
        self.editor.setObjectName('chatInput')
        self.editor.setAccessibleName('群聊消息输入')
        self.editor.setPlaceholderText('和同一局域网的庭友说句话……（最多 1000 字）')
        self.editor.setMaximumHeight(75)
        self.editor.setStyleSheet('QPlainTextEdit { background: #FFFBEA; border: 1px solid #E1DABD; border-radius: 8px; padding: 6px; }')
        layout = self.editor.parentWidget().layout()
        self.members = QLabel('正在寻找局域网庭友…')
        layout.insertWidget(1, self.members)
        self.history = QPlainTextEdit()
        self.history.setReadOnly(True)
        self.history.setAccessibleName('局域网群聊记录')
        self.history.setPlaceholderText('同一局域网打开春庭即可加入。\n自动保存并向在线庭友同步最近 200 条消息。')
        layout.insertWidget(2, self.history, 2)
        row = QHBoxLayout()
        self.reconnect_button = QPushButton('重连')
        self.reconnect_button.clicked.connect(self.reconnect)
        row.addWidget(self.reconnect_button)
        row.addStretch()
        self.send_button = QPushButton('发送')
        self.send_button.setStyleSheet('QPushButton { background: #DBE4C4; color: #56724C; border: 1px solid #B6C49A; border-radius: 8px; padding: 5px 14px; }')
        self.send_button.clicked.connect(self.send_message)
        row.addWidget(self.send_button)
        layout.insertLayout(layout.count()-1, row)
        self.status.setWordWrap(True)
        self.status.setText(service.status)
        self.status.setToolTip('同网段公开群聊，无账号或加密；最近 200 条消息会保存在本机并共享给上线庭友。需要至少一位在线庭友保留记录才能补齐。')
        service.messageReceived.connect(self._live_received)
        service.historyChanged.connect(self.refresh_history)
        service.statusChanged.connect(self.status.setText)
        service.peersChanged.connect(self.set_members)
        self.refresh_history()
        self.hide()  # Child widgets otherwise become visible when the preview opens.

    def reposition(self):
        bounds = self._bounds_provider()
        if bounds is None:
            return
        self.setFixedSize(min(410, bounds.width()), min(445, bounds.height()))
        self.move(bounds.left()+round(max(0,bounds.width()-self.width())*self.state.x),
                  bounds.top()+round(max(0,bounds.height()-self.height())*self.state.y))

    def _text_changed(self):
        self.state.text = self.editor.toPlainText()
        self.changed.emit()

    def set_members(self, count):
        self.members.setText(f'局域网在线 {count} 人（含自己）')

    def reconnect(self):
        self.service.close()
        if self.service.start():
            self.set_members(1)
        else:
            self.members.setText('尚未连接局域网')

    def send_message(self):
        text = self.editor.toPlainText().strip()
        if self.service.send_message(text):
            self.editor.clear()

    def refresh_history(self):
        scroll = self.history.verticalScrollBar()
        at_bottom = scroll.value() >= scroll.maximum()
        position = scroll.value()
        lines = []
        for record in self.service.history:
            name = ('我 · ' if record['sender'] == self.service.identity else '') + record['name']
            stamp = datetime.fromtimestamp(record['sent_at']/1000).strftime('%m-%d %H:%M')
            lines.append(f'{name}  {stamp}\n{record["text"]}\n')
        self.history.setPlainText('\n'.join(lines))
        scroll.setValue(scroll.maximum() if at_bottom else position)

    def _append(self, name, text):
        self.history.appendPlainText(f'{name}  {datetime.now():%H:%M}\n{text}\n')

    def receive_message(self, name, text):
        # Also used by the isolated rendering/demo tools.
        if self._closing:
            return
        self._append(name, text)
        self._live_received(name, text)

    def _live_received(self, name, text):
        if self._closing:
            return
        if not self.isVisible() or self.isMinimized():
            self.unread += 1
            self.unreadChanged.emit(self.unread)

    def showEvent(self, event):
        super().showEvent(event)
        self.unread = 0
        self.unreadChanged.emit(0)
