import json
import os
import socket
import tempfile
import time
import unittest
import uuid
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import Qt
from PySide6.QtNetwork import QNetworkInterface, QAbstractSocket
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from garden.lan_chat import LanChat, decode_packet
from garden.models import AppState
from garden.window import PondWindow


def packet(**extra):
    return json.dumps(dict(app='haruniwa-chat', v=1, sender=str(uuid.uuid4()),
                          id=str(uuid.uuid4()), kind='message', name='庭友', text='你好', **extra)).encode()


class ChatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_rejects_malformed_and_oversized_packets(self):
        valid = json.loads(packet())
        self.assertIsNotNone(decode_packet(packet()))
        for invalid in (b'x', b'[]', b'null', b'['*8190, b'x'*8193):
            self.assertIsNone(decode_packet(invalid))
        for key,value in (('v',2),('sender','x'),('id',[]),('kind','file'),('text','x'*1001),
                          ('text','  '),('name','\n'),('name','x'*49)):
            self.assertIsNone(decode_packet(json.dumps({**valid,key:value}).encode()))

    def test_dedup_self_echo_and_bounded_history(self):
        service = LanChat()
        messages = []
        service.messageReceived.connect(lambda *args: messages.append(args))
        raw = packet()
        service._receive(raw); service._receive(raw)
        service._receive(json.dumps({**json.loads(raw),'sender':service.identity}).encode())
        self.assertEqual(messages,[('庭友','你好')])
        self.assertEqual(len(service.peers),1)
        service.peers['expired'] = time.monotonic()-20
        service._last_hello = time.monotonic()
        service._tick()
        self.assertNotIn('expired',service.peers)
        service.close()

    def test_hidden_badge_pin_restore_and_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'state.json'
            window = PondWindow(path,preview=True)
            window.show_layers()
            window.orb.collapse()
            window.chat_service._receive(packet())
            self.assertEqual(window.chat.unread,1)
            self.assertTrue(window.orb.chat_badge.isVisible())
            QTest.mouseClick(window.orb.chat_badge,Qt.LeftButton)
            self.assertTrue(window.chat.isVisible())
            self.assertEqual(window.chat.unread,0)
            self.assertFalse(window.orb.chat_badge.isVisible())
            self.assertIn('你好',window.chat.history.toPlainText())
            window.chat.receive_message('<b>名字</b>','<script>普通文本</script>')
            self.assertIn('<script>普通文本</script>',window.chat.history.toPlainText())
            self.assertEqual(window.chat.unread,0)
            window.chat.editor.setPlainText('保留草稿')
            window.chat.send_message()  # No connection: keep the unsent draft.
            self.assertEqual(window.chat.editor.toPlainText(),'保留草稿')
            window.chat.set_pinned(True)
            window.chat.hide_note()
            self.assertFalse(window.chat.isVisible())
            self.assertFalse(window._shutting_down)
            window.chat.receive_message('庭友','隐藏后消息')
            self.assertEqual(window.chat.unread,1)
            window.shutdown()
            self.assertFalse(window.chat.isVisible())
            self.assertFalse(window.chat_service.timer.isActive())
            self.assertFalse(window.chat_service.drain_timer.isActive())
            self.assertEqual(window.chat_service.socket.state(),QAbstractSocket.UnconnectedState)
            restored = AppState.from_dict(json.loads(path.read_text()))
            self.assertTrue(restored.chat.pinned)
            self.assertFalse(restored.chat.visible)
            self.assertEqual(restored.chat.text,'保留草稿')
            self.assertNotIn('隐藏后消息',path.read_text())
            window.deleteLater()

    def test_legacy_state_and_standalone_pin(self):
        from garden.chat_widget import ChatWidget
        from PySide6.QtCore import QRect
        state = AppState.from_dict({})
        self.assertFalse(state.chat.visible)
        service=LanChat()
        chat=ChatWidget(state.chat,lambda:QRect(0,0,960,600),service)
        chat.set_pinned(True)
        self.assertTrue(chat.windowFlags() & Qt.WindowStaysOnTopHint)
        chat.set_pinned(False)
        self.assertFalse(chat.windowFlags() & Qt.WindowStaysOnTopHint)
        chat.close_for_shutdown();chat.deleteLater()

    def test_two_clients_multicast_on_loopback_only(self):
        # Select only loopback: synthetic messages cannot leave this computer.
        loopbacks=[i for i in QNetworkInterface.allInterfaces() if i.flags() & QNetworkInterface.IsLoopBack]
        if not loopbacks:
            self.skipTest('no loopback network interface')
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as probe:
            probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
        first=LanChat(name='甲',port=port,interfaces=loopbacks)
        second=LanChat(name='乙',port=port,interfaces=loopbacks)
        received=[]
        second.messageReceived.connect(lambda *args:received.append(args))
        try:
            self.assertTrue(first.start(),first.status)
            self.assertTrue(second.start(),second.status)
            first._hello()
            QTest.qWait(150)
            self.assertEqual(len(first.peers),1)
            self.assertEqual(len(second.peers),1)
            self.assertTrue(first.send_message('仅本机回环测试'))
            QTest.qWait(2400)
            self.assertEqual(received,[('甲','仅本机回环测试')])
            self.assertFalse(first.send_message('x'*1001))
            first.close()
            QTest.qWait(100)
            self.assertEqual(len(second.peers),0)
        finally:
            first.close();second.close()
