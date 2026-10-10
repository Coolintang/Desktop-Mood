"""The note survives hiding, pinning, repositioning and application shutdown."""
import json
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import unittest

from PySide6.QtCore import Qt, QCoreApplication, QEvent, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton
from garden.models import AppState, NoteState
from garden.window import PondWindow


class NoteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name)/'note.json'
        self.window = PondWindow(self.path, preview=True)
        self.window.show_layers()
        self.app.processEvents()

    def tearDown(self):
        self.window.shutdown()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.directory.cleanup()

    def test_toolbar_opens_note_text_autosaves_and_hide_keeps_garden_running(self):
        self.window.orb.expand()
        self.app.processEvents()
        self.window.orb.findChild(QPushButton, 'notesButton').click()
        self.assertTrue(self.window.note.isVisible())
        self.window.note.editor.setPlainText('明天记得浇花\n买咖啡 ☕')
        QTest.qWait(750)
        self.assertEqual(json.loads(self.path.read_text())['note']['text'], '明天记得浇花\n买咖啡 ☕')
        QTest.mouseClick(self.window.note.hide_button, Qt.LeftButton)
        self.assertFalse(self.window.note.isVisible())
        self.assertTrue(self.window.timer.isActive())
        self.assertFalse(self.window._shutting_down)
        self.window.show_note()
        self.assertIn('买咖啡', self.window.note.editor.toPlainText())
        self.window.note.close()
        self.assertFalse(self.window.state.note.visible)
        self.window.save_state()
        self.assertFalse(json.loads(self.path.read_text())['note']['visible'])
        self.assertFalse(self.window._shutting_down)

    def test_shutdown_flushes_latest_edit_and_restores_visibility_and_pin(self):
        self.window.show_note()
        self.window.note.editor.setPlainText('尚未等到自动保存的内容')
        QTest.mouseClick(self.window.note.pin_button, Qt.LeftButton)
        self.assertTrue(self.window.state.note.pinned)
        self.window.shutdown()
        self.assertFalse(self.window.note.isVisible())
        self.assertFalse(self.window.note_save_timer.isActive())
        saved = json.loads(self.path.read_text())['note']
        self.assertTrue(saved['visible'])
        self.assertTrue(saved['pinned'])
        other = PondWindow(self.path, preview=True)
        try:
            other.show_layers()
            self.assertTrue(other.note.isVisible())
            self.assertTrue(other.note.pin_button.isChecked())
            self.assertEqual(other.note.editor.toPlainText(), '尚未等到自动保存的内容')
        finally:
            other.shutdown()
            other.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_position_is_bounded_pinned_drag_is_locked_and_resize_stays_visible(self):
        self.window.show_note()
        note = self.window.note
        note.move_within_bounds(QPoint(99999, 99999))
        note.remember_position()
        self.assertTrue(self.window.rect().contains(note.geometry()))
        note.set_pinned(True)
        before = note.pos()
        QTest.mousePress(note.header, Qt.LeftButton, pos=QPoint(20, 15))
        QTest.mouseMove(note.header, QPoint(-500, -500))
        QTest.mouseRelease(note.header, Qt.LeftButton, pos=QPoint(-500, -500))
        self.assertEqual(note.pos(), before)
        self.window.resize(640, 420)
        self.app.processEvents()
        self.assertTrue(self.window.rect().contains(note.geometry()))

    def test_standalone_pin_uses_topmost_only_when_requested(self):
        standalone = PondWindow(Path(self.directory.name)/'desktop.json')
        try:
            standalone.show_note()
            self.assertFalse(standalone.note.windowFlags() & Qt.WindowStaysOnTopHint)
            standalone.note.set_pinned(True)
            self.assertTrue(standalone.note.windowFlags() & Qt.WindowStaysOnTopHint)
            standalone.note.set_pinned(False)
            self.assertFalse(standalone.note.windowFlags() & Qt.WindowStaysOnTopHint)
            standalone.note.hide_note()
            self.assertFalse(standalone.note.isVisible())
        finally:
            standalone.shutdown()
            standalone.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_legacy_note_defaults_and_invalid_positions(self):
        self.assertEqual(AppState.from_dict({}).note, NoteState())
        note = NoteState.from_dict({'text': '便签', 'x': float('nan'), 'y': 999, 'pinned': 'false'})
        self.assertEqual(note.x, .78)
        self.assertEqual(note.y, 1)
        self.assertFalse(note.pinned)
