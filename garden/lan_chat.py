"""Serverless LAN room with bounded recent-history sharing and best-effort delivery."""
from collections import OrderedDict, deque
import hashlib
import json
import socket
import time
import uuid

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtNetwork import QAbstractSocket, QHostAddress, QNetworkInterface, QUdpSocket
from .chat_history import (ChatArchive, MAX_HISTORY, MAX_TEXT, message_record, record_order,
                           valid_name, valid_record, valid_text, valid_uuid)

GROUP = '239.255.73.41'
PORT = 45873
MAX_PACKET = 8192
SYNC_INTERVAL = 12


def decode_packet(data):
    if len(data) > MAX_PACKET:
        return None
    try:
        value = json.loads(data)
        if not isinstance(value, dict) or value.get('app') != 'haruniwa-chat' or value.get('v') != 1:
            return None
        if not all(valid_uuid(value.get(key)) for key in ('sender', 'id')):
            return None
        if value.get('kind') not in ('hello', 'message', 'bye', 'history_request', 'history_item'):
            return None
        if not valid_name(value.get('name')):
            return None
        if value['kind'] == 'message':
            # v1 live messages without timestamps remain interoperable.
            if not valid_text(value.get('text')):
                return None
            if 'sent_at' in value and not valid_record(value):
                return None
        elif value['kind'] == 'hello' and 'history' in value:
            digest = value['history']
            if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
                return None
        elif value['kind'] == 'history_request':
            known = value.get('known')
            if not isinstance(known, list) or len(known) > MAX_HISTORY or not all(map(valid_uuid, known)):
                return None
        elif value['kind'] == 'history_item':
            if (not valid_uuid(value.get('target')) or not valid_uuid(value.get('request'))
                    or not valid_record(value.get('message'))):
                return None
        return value
    except (ValueError, TypeError, UnicodeError, RecursionError):
        return None


class LanChat(QObject):
    messageReceived = Signal(str, str)
    peersChanged = Signal(int)
    statusChanged = Signal(str)
    historyChanged = Signal()

    def __init__(self, parent=None, *, name=None, port=PORT, interfaces=None, history_path=None):
        super().__init__(parent)
        self.name = ''.join(c for c in (name or socket.gethostname()) if ord(c) >= 32)[:48].strip() or '庭友'
        self.archive = ChatArchive(history_path)
        self.identity = self.archive.identity
        self._records = OrderedDict((record['id'], record) for record in self.archive.records)
        self.cache_timer = QTimer(self)
        self.cache_timer.setSingleShot(True)
        self.cache_timer.setInterval(600)
        self.cache_timer.timeout.connect(self._save_history)
        self.share_timer = QTimer(self)
        self.share_timer.setInterval(100)
        self.share_timer.timeout.connect(self._share_pending)
        self._share_queue = deque()
        self._last_request = -SYNC_INTERVAL
        self._requests = {}
        self._answered = {}
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
        self.status = message + (' · 聊天缓存读写失败（详见日志）' if self.archive.error else '')
        self.statusChanged.emit(self.status)

    @property
    def history(self):
        return list(self._records.values())

    def _digest(self):
        return hashlib.sha256(''.join(sorted(self._records)).encode('ascii')).hexdigest()

    def _remember(self, record):
        if record['id'] in self._records:
            return False
        record = message_record(record)
        records = sorted([*self.history, record], key=record_order)[-MAX_HISTORY:]
        if record not in records:
            return False
        self._records = OrderedDict((item['id'], item) for item in records)
        if not self.cache_timer.isActive():
            self.cache_timer.start()
        self.historyChanged.emit()
        return True

    def _save_history(self):
        if not self.archive.save(self.history):
            self._status('聊天仍可使用，历史记录暂时无法保存')

    def _request_history(self):
        now = time.monotonic()
        if not self.active or now - self._last_request < SYNC_INTERVAL:
            return
        data = self._packet('history_request', known=list(self._records))
        if self._write(data):
            self._last_request = now
            self._requests[json.loads(data)['id']] = now

    def _queue_history(self, packet, now):
        sender = packet['sender']
        if not self.active or now - self._answered.get(sender, -SYNC_INTERVAL) < SYNC_INTERVAL:
            return
        self._answered[sender] = now
        known = set(packet['known'])
        for record in self.history:
            if record['id'] not in known and len(self._share_queue) < MAX_HISTORY * 2:
                data = self._packet('history_item', target=sender, request=packet['id'], message=record)
                self._share_queue.append((now, data))
        if self._share_queue:
            self.share_timer.start()

    def _share_pending(self):
        # Pace replies so a joining peer cannot stall animation or flood the LAN.
        now = time.monotonic()
        for _ in range(min(2, len(self._share_queue))):
            created, data = self._share_queue.popleft()
            if now-created < 30:
                self._write(data)
        if not self._share_queue:
            self.share_timer.stop()

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
        self._request_history()
        return True

    def _packet(self, kind, **extra):
        return json.dumps(dict(app='haruniwa-chat', v=1, sender=self.identity,
                               id=str(uuid.uuid4()), name=self.name, kind=kind, **extra),
                          ensure_ascii=False, separators=(',', ':')).encode('utf-8')

    def _write(self, data):
        if len(data) > MAX_PACKET:
            return False
        successes = 0
        for interface in self._interfaces:
            self.socket.setMulticastInterface(interface)
            if self.socket.writeDatagram(data, QHostAddress(GROUP), self.port) == len(data):
                successes += 1
        return successes > 0

    def _hello(self):
        self._last_hello = time.monotonic()
        if self._write(self._packet('hello', history=self._digest())):
            self._status(f'局域网已连接 · 在线 {len(self.peers)+1} 人（含自己）')
        else:
            self._status('局域网发送失败，请检查网络并重连')

    def send_message(self, text):
        text = text.strip()
        if not valid_text(text):
            self._status(f'请输入 1–{MAX_TEXT} 字的消息')
            return False
        if not self.active:
            self._status('尚未连接，请点击重连')
            return False
        now = time.monotonic()
        if now-self._last_send < .5:
            self._status('发送太快，请稍候再试')
            return False
        data = self._packet('message', text=text, sent_at=int(time.time()*1000))
        if not self._write(data):
            self._status('消息发送失败，请重连后重试')
            return False
        self._last_send = now
        self._remember(message_record(json.loads(data)))
        self.pending.append([data, now+1, 2])
        self._status('消息已发出 · 在线庭友会共享最近 200 条记录')
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
            self._answered.pop(sender, None)
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
            packet.setdefault('sent_at', int(time.time()*1000))
            if self._remember(message_record(packet)):
                self.messageReceived.emit(packet['name'], packet['text'])
        elif packet['kind'] == 'hello':
            if 'history' in packet and packet['history'] != self._digest():
                self._request_history()
        elif packet['kind'] == 'history_request':
            self._queue_history(packet, now)
        elif packet['kind'] == 'history_item':
            requested = self._requests.get(packet['request'])
            if packet['target'] == self.identity and requested is not None and now-requested < 30:
                # A relayed record never turns its original author into an online peer,
                # and never counts as a new unread/live message.
                self._remember(packet['message'])

    def _tick(self):
        now = time.monotonic()
        old_count = len(self.peers)
        self.peers = {key: seen for key, seen in self.peers.items() if now-seen < 18}
        self._answered = {key: seen for key, seen in self._answered.items() if now-seen < 30}
        self._requests = {key: seen for key, seen in self._requests.items() if now-seen < 30}
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
        self.share_timer.stop()
        self.cache_timer.stop()
        self._save_history()
        self._share_queue.clear()
        self._requests.clear()
        self._answered.clear()
        self._last_request = -SYNC_INTERVAL
        self.pending.clear()
        self.peers.clear()
        self.seen.clear()
        for interface in self._interfaces:
            self.socket.leaveMulticastGroup(QHostAddress(GROUP), interface)
        self._interfaces.clear()
        self.socket.close()
