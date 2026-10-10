import json
import os
from pathlib import Path
import socket
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QRect
from PySide6.QtNetwork import QNetworkInterface
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from garden.chat_history import ChatArchive, MAX_HISTORY
from garden.chat_widget import ChatWidget
from garden.lan_chat import LanChat, MAX_PACKET, decode_packet
from garden.models import NoteState


def record(index=0, **extra):
    return dict(sender=str(uuid.uuid4()), id=str(uuid.uuid4()), name='庭友',
                text=f'消息 {index}', sent_at=1700000000000+index, **extra)


class HistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_archive_restart_and_chronological_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'state.chat.json'
            first = LanChat(history_path=path)
            items = [record(i) for i in range(MAX_HISTORY+3)]
            for item in reversed(items):
                first._remember(item)
            self.assertEqual(first.history, items[3:])
            self.assertFalse(first._remember(items[-1]))
            first.close()
            restored = LanChat(history_path=path)
            self.assertEqual(restored.identity, first.identity)
            self.assertEqual(restored.history, items[3:])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            restored.close()

    def test_damaged_cache_and_failed_save_preserve_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'chat.json'
            path.write_text('{broken', encoding='utf-8')
            archive = ChatArchive(path)
            self.assertFalse(archive.save([record()]))
            self.assertEqual(path.read_text(), '{broken')
            path.unlink()
            archive = ChatArchive(path)
            self.assertTrue(archive.save([record()]))
            original = path.read_bytes()
            with patch.object(Path, 'replace', side_effect=OSError('disk full')):
                self.assertFalse(archive.save([record(1)]))
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_targeted_history_is_deduplicated_and_not_unread(self):
        service = LanChat()
        chat = ChatWidget(NoteState(), lambda: QRect(0, 0, 960, 600), service)
        relay = LanChat(name='转发庭友')
        request = str(uuid.uuid4())
        service._requests[request] = time.monotonic()
        item = record()
        try:
            wrong = relay._packet('history_item', target=relay.identity, request=request, message=item)
            service._receive(wrong)
            self.assertFalse(service.history)
            unsolicited = relay._packet('history_item', target=service.identity,
                                         request=str(uuid.uuid4()), message=item)
            service._receive(unsolicited)
            self.assertFalse(service.history)
            shared = relay._packet('history_item', target=service.identity, request=request, message=item)
            service._receive(shared)
            service._receive(shared)
            live = dict(app='haruniwa-chat', v=1, kind='message', **item)
            service._receive(json.dumps(live).encode())
            self.assertEqual(service.history, [item])
            self.assertEqual(chat.history.toPlainText().count(item['text']), 1)
            self.assertEqual(chat.unread, 0)
            # A relay alone must not mark the original author as online.
            other = record(1)
            service._receive(relay._packet('history_item', target=service.identity,
                                          request=request, message=other))
            self.assertNotIn(other['sender'], service.peers)
            self.assertEqual(chat.unread, 0)
        finally:
            chat.close_for_shutdown()
            service.close()
            relay.close()
            chat.deleteLater()

    def test_self_send_is_cached_once_and_failed_send_keeps_draft(self):
        service = LanChat(name='我家')
        chat = ChatWidget(NoteState(), lambda: QRect(0, 0, 960, 600), service)
        service.active = True
        try:
            chat.editor.setPlainText('自己的消息')
            with patch.object(service, '_write', return_value=False):
                chat.send_message()
            self.assertEqual(chat.editor.toPlainText(), '自己的消息')
            self.assertFalse(service.history)
            with patch.object(service, '_write', return_value=True):
                chat.send_message()
            self.assertEqual(chat.editor.toPlainText(), '')
            self.assertEqual(len(service.history), 1)
            self.assertEqual(chat.history.toPlainText().count('自己的消息'), 1)
            self.assertIn('我 · 我家', chat.history.toPlainText())
        finally:
            service.active = False
            service.close()
            chat.close_for_shutdown()
            chat.deleteLater()

    def test_packet_validation_and_maximum_inventory_size(self):
        service = LanChat(name='庭'*48)
        try:
            data = service._packet('history_request', known=[str(uuid.uuid4()) for _ in range(MAX_HISTORY)])
            self.assertLessEqual(len(data), MAX_PACKET)
            self.assertIsNotNone(decode_packet(data))
            base = json.loads(service._packet('history_item', target=str(uuid.uuid4()),
                                             request=str(uuid.uuid4()), message=record()))
            for invalid in (None, [], {}, {**record(), 'sent_at': True},
                            {**record(), 'sent_at': float('nan')}, {**record(), 'text': 'x'*1001}):
                self.assertIsNone(decode_packet(json.dumps({**base, 'message': invalid}).encode()))
            self.assertIsNone(decode_packet(service._packet('history_request', known=['x'])))
            self.assertIsNone(decode_packet(service._packet('hello', history=[])))
        finally:
            service.close()

    def test_sharing_is_paced_bounded_and_omits_known_messages(self):
        service = LanChat()
        peer = LanChat()
        items = [record(i) for i in range(5)]
        for item in items:
            service._remember(item)
        service.active = True
        request = json.loads(peer._packet('history_request', known=[items[0]['id']]))
        try:
            now = time.monotonic()
            service._queue_history(request, now)
            self.assertEqual(len(service._share_queue), 4)
            service._queue_history(request, now)
            self.assertEqual(len(service._share_queue), 4)
            with patch.object(service, '_write', return_value=True) as write:
                service._share_pending()
            self.assertEqual(write.call_count, 2)
            self.assertEqual(len(service._share_queue), 2)
        finally:
            service.active = False
            service.close()
            peer.close()
        self.assertFalse(service.share_timer.isActive())
        self.assertFalse(service.cache_timer.isActive())
        self.assertFalse(service._share_queue)

    def test_late_join_from_restarted_peer_with_author_offline_on_loopback(self):
        loopbacks = [i for i in QNetworkInterface.allInterfaces() if i.flags() & QNetworkInterface.IsLoopBack]
        if not loopbacks:
            self.skipTest('no loopback interface')
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'relay.chat.json'
            author = LanChat(name='原作者', port=port, interfaces=loopbacks)
            relay = LanChat(name='共享者', port=port, interfaces=loopbacks, history_path=path)
            newcomer = LanChat(name='新庭友', port=port, interfaces=loopbacks)
            clients = [author, relay, newcomer]
            live = []
            newcomer.messageReceived.connect(lambda *args: live.append(args))
            try:
                self.assertTrue(author.start(), author.status)
                self.assertTrue(relay.start(), relay.status)
                QTest.qWait(150)
                self.assertTrue(author.send_message('离线作者留下的近期消息'))
                QTest.qWait(200)
                original = author.history[0]
                self.assertEqual(relay.history, [original])
                author.close()
                relay.close()
                relay = LanChat(name='重启共享者', port=port, interfaces=loopbacks, history_path=path)
                clients.append(relay)
                self.assertTrue(relay.start(), relay.status)
                self.assertTrue(newcomer.start(), newcomer.status)
                QTest.qWait(500)
                self.assertEqual(newcomer.history, [original])
                self.assertEqual(live, [])
                self.assertNotIn(author.identity, newcomer.peers)
                newcomer.close()
                self.assertTrue(relay.send_message('重连期间的新消息'))
                QTest.qWait(100)
                self.assertTrue(newcomer.start(), newcomer.status)
                QTest.qWait(500)
                self.assertEqual(len(newcomer.history), 2)
                self.assertEqual(live, [])
            finally:
                for client in clients:
                    client.close()
