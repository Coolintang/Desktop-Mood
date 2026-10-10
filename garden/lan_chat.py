"""Small serverless IPv4 LAN room. No history or external service is used.

Multicast is limited to one router hop. Messages are repeated with the same ID
and deduplicated; this is best-effort delivery, not an offline message queue.
"""
from collections import OrderedDict
import json
import socket
import time
import uuid

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtNetwork import QAbstractSocket, QHostAddress, QNetworkInterface, QUdpSocket

GROUP = '239.255.73.41'
PORT = 45873
MAX_TEXT = 1000
MAX_PACKET = 8192


def decode_packet(data):
    if len(data) > MAX_PACKET:
        return None
    try:
        value = json.loads(data)
        if not isinstance(value, dict) or value.get('app') != 'haruniwa-chat' or value.get('v') != 1:
            return None
        for key in ('sender', 'id'):
            if not isinstance(value.get(key), str) or str(uuid.UUID(value[key])) != value[key]:
                return None
        if value.get('kind') not in ('hello', 'message', 'bye'):
            return None
        name = value.get('name')
        if not isinstance(name, str) or not name.strip() or len(name) > 48:
            return None
        if any(ord(c) < 32 for c in name):
            return None
        if value['kind'] == 'message':
            text = value.get('text')
            if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT:
                return None
        return value
    except (ValueError, TypeError, UnicodeError, RecursionError):
        return None


class LanChat(QObject):
    messageReceived = Signal(str, str)
    peersChanged = Signal(int)
    statusChanged = Signal(str)

    def __init__(self, parent=None, *, name=None, port=PORT, interfaces=None):
        super().__init__(parent)
        self.name = (name or socket.gethostname())[:48].strip() or '庭友'
        self.identity = str(uuid.uuid4())
        self.port = port
        self._requested_interfaces = interfaces
        self._interfaces = []
        self.socket = QUdpSocket(self)
        self.socket.readyRead.connect(self._drain)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)
        self.drain_timer = QTimer(self)
        self.drain_timer.setSingleShot(True)
        self.drain_timer.timeout.connect(self._drain)
        self.peers = {}
        self.seen = OrderedDict()
        self.pending = []
        self.active = False
        self.status = '局域网聊天尚未连接'
        self._last_hello = 0
        self._last_send = -10
        self._rate_start = 0
        self._rate_count = 0

    def _status(self, message):
        self.status = message
        self.statusChanged.emit(message)

    def start(self):
        if self.active:
            return True
        flags = QAbstractSocket.ShareAddress | QAbstractSocket.ReuseAddressHint
        if not self.socket.bind(QHostAddress.AnyIPv4, self.port, flags):
            self._status('聊天连接失败：'+self.socket.errorString())
            return False
        self.socket.setSocketOption(QAbstractSocket.MulticastTtlOption, 1)
        self.socket.setSocketOption(QAbstractSocket.MulticastLoopbackOption, 1)
        interfaces = self._requested_interfaces
        if interfaces is None:
            interfaces = [i for i in QNetworkInterface.allInterfaces()
                          if i.flags() & QNetworkInterface.IsUp
                          and i.flags() & QNetworkInterface.CanMulticast
                          and not i.flags() & QNetworkInterface.IsLoopBack
                          and any(e.ip().protocol() == QAbstractSocket.IPv4Protocol for e in i.addressEntries())]
        self._interfaces = [i for i in interfaces if self.socket.joinMulticastGroup(QHostAddress(GROUP), i)]
        if not self._interfaces:
            self.socket.close()
            self._status('未找到可用局域网，请联网后点击重连')
            return False
        self.active = True
        self.timer.start()
        self._hello()
        return True

    def _packet(self, kind, **extra):
        return json.dumps(dict(app='haruniwa-chat', v=1, sender=self.identity,
                               id=str(uuid.uuid4()), name=self.name, kind=kind, **extra),
                          ensure_ascii=False).encode('utf-8')

    def _write(self, data):
        successes = 0
        for interface in self._interfaces:
            self.socket.setMulticastInterface(interface)
            if self.socket.writeDatagram(data, QHostAddress(GROUP), self.port) == len(data):
                successes += 1
        return successes > 0

    def _hello(self):
        self._last_hello = time.monotonic()
        if self._write(self._packet('hello')):
            self._status(f'局域网已连接 · 在线 {len(self.peers)+1} 人（含自己）')
        else:
            self._status('局域网发送失败，请检查网络并重连')

    def send_message(self, text):
        text = text.strip()
        if not text or len(text) > MAX_TEXT:
            self._status(f'请输入 1–{MAX_TEXT} 字的消息')
            return False
        if not self.active:
            self._status('尚未连接，请点击重连')
            return False
        now = time.monotonic()
        if now-self._last_send < .5:
            self._status('发送太快，请稍候再试')
            return False
        data = self._packet('message', text=text)
        if not self._write(data):
            self._status('消息发送失败，请重连后重试')
            return False
        self._last_send = now
        self.pending.append([data, now+1, 2])
        self._status('消息已发出 · 局域网尽力送达，无离线补发')
        return True

    def _drain(self):
        # Yield to the UI even under a busy or malformed multicast stream.
        for _ in range(64):
            if not self.socket.hasPendingDatagrams():
                break
            size = self.socket.pendingDatagramSize()
            data, _, _ = self.socket.readDatagram(min(MAX_PACKET+1, max(1, size)))
            if size <= MAX_PACKET:
                self._receive(bytes(data))
        if self.socket.hasPendingDatagrams():
            self.drain_timer.start(10)

    def _receive(self, data):
        now = time.monotonic()
        if now-self._rate_start >= 1:
            self._rate_start, self._rate_count = now, 0
        self._rate_count += 1
        if self._rate_count > 240:
            return
        packet = decode_packet(data)
        if packet is None or packet['sender'] == self.identity:
            return
        sender = packet['sender']
        old_count = len(self.peers)
        if packet['kind'] == 'bye':
            self.peers.pop(sender, None)
        else:
            if sender not in self.peers and len(self.peers) >= 256:
                return
            self.peers[sender] = now
        if len(self.peers) != old_count:
            self.peersChanged.emit(len(self.peers)+1)
        key = (sender, packet['id'])
        if key in self.seen:
            return
        self.seen[key] = now
        while len(self.seen) > 2048:
            self.seen.popitem(last=False)
        if packet['kind'] == 'message':
            self.messageReceived.emit(packet['name'], packet['text'])

    def _tick(self):
        now = time.monotonic()
        old_count = len(self.peers)
        self.peers = {key: seen for key, seen in self.peers.items() if now-seen < 18}
        if len(self.peers) != old_count:
            self.peersChanged.emit(len(self.peers)+1)
        for item in self.pending:
            if now >= item[1]:
                self._write(item[0]); item[1] = now+1; item[2] -= 1
        self.pending = [item for item in self.pending if item[2] > 0]
        if now-self._last_hello >= 5:
            self._hello()

    def close(self):
        if self.active:
            self._write(self._packet('bye'))
        self.active = False
        self.timer.stop()
        self.drain_timer.stop()
        self.pending.clear()
        self.peers.clear()
        self.seen.clear()
        for interface in self._interfaces:
            self.socket.leaveMulticastGroup(QHostAddress(GROUP), interface)
        self._interfaces.clear()
        self.socket.close()
