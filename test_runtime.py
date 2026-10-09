"""State safety and offscreen lifecycle regression tests; use temporary saves."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QPushButton
from PySide6.QtCore import Qt, QTimer, QCoreApplication, QEvent
from PySide6.QtTest import QTest
from garden.models import AppState, DEFAULT_PREFERENCES, normalize_preferences
from garden.state import StateStore


class StateTests(unittest.TestCase):
    def test_legacy_state_and_preferences(self):
        state = AppState.from_dict({'fish': [], 'plants': []})
        self.assertEqual(state.preferences, DEFAULT_PREFERENCES)
        preferences = normalize_preferences({'fps': '60', 'petals': 'false', 'time_mode': 'night',
                                              'weather_mode': ['rain'], 'unknown': True})
        self.assertEqual(preferences['fps'], 30)
        self.assertIs(preferences['petals'], True)
        self.assertEqual(preferences['time_mode'], 'night')
        self.assertNotIn('unknown', preferences)

    def test_atomic_failure_preserves_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state.json'
            store = StateStore(path)
            state = store.load()
            self.assertTrue(store.save(state))
            original = path.read_bytes()
            state.preferences['fps'] = 60
            with patch('garden.state.os.replace', side_effect=OSError('disk unavailable')):
                self.assertFalse(store.save(state))
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(Path(directory).iterdir()), [path])
            self.assertTrue(store.save(state))
            self.assertEqual(StateStore(path).load().preferences['fps'], 60)

    def test_corrupt_file_never_overwritten(self):
        for content in ('{broken', '[]', '{"fish": [{"x": "bad", "y": 0}]}',
                        '{"fish": [null]}', '{"fish": {}}',
                        '{"fish": [{"x": 0, "y": 0, "kind": []}]}'):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'state.json'
                path.write_text(content)
                store = StateStore(path)
                state = store.load()
                self.assertFalse(store.save(state))
                self.assertEqual(path.read_text(), content)


class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_preview_pause_preferences_and_quit_save(self):
        from garden.window import PondWindow
        from garden.constants import Tool
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state.json'
            window = PondWindow(path, preview=True)
            self.assertFalse(bool(window.windowFlags() & Qt.WindowTransparentForInput))
            window.set_tool(Tool.FEED)
            self.assertFalse(window.interaction.isVisible())
            window.set_running(False)
            before = window.scene.t
            window.tick()
            self.assertEqual(window.scene.t, before)
            self.assertFalse(window.timer.isActive())
            window.set_preference('fps', 60)
            window.set_preference('time_mode', 'night')
            window.set_running(True)
            self.assertEqual(window.timer.interval(), 17)
            window.state.water_quality = 73
            self.app.aboutToQuit.emit()
            self.assertEqual(json.loads(path.read_text())['water_quality'], 73)
            self.assertFalse(window.timer.isActive())
            self.assertTrue(window._shutting_down)
            window.shutdown()  # idempotent after app quit
            window.deleteLater()

    def test_preview_close_only_saves_selected_path(self):
        from garden.window import PondWindow
        real_state = Path(__file__).resolve().parent / 'data/state.json'
        original = real_state.read_bytes() if real_state.exists() else None
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'preview.json'
            window = PondWindow(path, preview=True)
            window.state.water_quality = 65
            window.close()
            self.assertEqual(json.loads(path.read_text())['water_quality'], 65)
            self.assertEqual(real_state.read_bytes() if real_state.exists() else None, original)
            window.deleteLater()

    def test_tray_actions_route_to_window(self):
        from garden.window import PondWindow
        with tempfile.TemporaryDirectory() as directory:
            with patch('garden.window.QSystemTrayIcon.isSystemTrayAvailable', return_value=True):
                window = PondWindow(Path(directory) / 'state.json', preview=True)
            self.assertIsNotNone(window.tray)
            window.pause_action.trigger()
            self.assertFalse(window.running)
            window.mode_actions['overlay'].trigger()
            self.assertEqual(window.state.preferences['wallpaper_mode'], 'overlay')
            window._populate_screens()
            self.assertEqual(len(window.screen_menu.actions()), len(self.app.screens()))
            window.screen_menu.actions()[0].trigger()
            window.shutdown()
            window.deleteLater()

    def assert_fully_stopped(self, window):
        self.assertTrue(window._shutting_down)
        self.assertFalse(window.running)
        for layer in (window, window.orb, window.interaction):
            self.assertFalse(layer.isVisible())
        for timer in (window.timer, window.save_timer, window.layer_timer,
                      *window.orb.findChildren(QTimer)):
            self.assertFalse(timer.isActive())

    def test_wallpaper_exit_button_saves_once_and_stops_all_layers(self):
        from garden.window import PondWindow
        from garden.constants import Tool
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state.json'
            with patch('garden.window.QSystemTrayIcon.isSystemTrayAvailable', return_value=False):
                window = PondWindow(path)
            window.show_layers()
            window.orb.expand()
            window.set_tool(Tool.FEED)
            window.orb.show_feedback('testing active feedback')
            window.state.water_quality = 64
            self.app.processEvents()
            self.assertTrue(window.interaction.isVisible())
            self.assertTrue(window.orb._feedback_timer.isActive())
            with patch.object(window.store, 'save', wraps=window.store.save) as save:
                QTest.mouseClick(window.orb.findChild(QPushButton, 'exitButton'), Qt.LeftButton)
                self.assert_fully_stopped(window)
                window.request_exit()
                window.set_running(True)
                window.show_layers()
                window.set_tool(Tool.FEED)
                self.assert_fully_stopped(window)
                save.assert_called_once()
            self.assertEqual(json.loads(path.read_text())['water_quality'], 64)
            window.deleteLater()

    def test_closing_standalone_panel_exits_wallpaper_without_tray(self):
        from garden.window import PondWindow
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state.json'
            with patch('garden.window.QSystemTrayIcon.isSystemTrayAvailable', return_value=False):
                window = PondWindow(path)
            window.show_layers()
            self.app.processEvents()
            self.assertTrue(window.isVisible())
            window.orb.close()  # The close event also used by the window manager.
            self.assert_fully_stopped(window)
            self.assertTrue(path.exists())
            window.deleteLater()

    def test_capsule_exit_menu_and_ctrl_q(self):
        from garden.window import PondWindow
        for entry in ('menu', 'shortcut'):
            with self.subTest(entry=entry), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'state.json'
                window = PondWindow(path)
                window.show_layers()
                window.orb.activateWindow()
                window.orb._capsule.setFocus()
                self.app.processEvents()
                if entry == 'menu':
                    window.orb._capsule.customContextMenuRequested.emit(window.orb._capsule.rect().center())
                    self.assertTrue(window.orb._exit_menu.isVisible())
                    self.app.processEvents()
                    menu = window.orb._exit_menu
                    QTest.mouseClick(menu, Qt.LeftButton, pos=menu.actionGeometry(window.orb.exit_action).center())
                else:
                    QTest.keyClick(window.orb._capsule, Qt.Key_Q, Qt.ControlModifier)
                try:
                    self.assert_fully_stopped(window)
                    self.assertTrue(path.exists())
                finally:
                    window.shutdown()
                    window.deleteLater()
                    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_unexpected_save_failure_does_not_trap_wallpaper(self):
        from garden.window import PondWindow
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state.json'
            window = PondWindow(path)
            window.store.save(window.state)
            original = path.read_bytes()
            window.show_layers()
            window.orb.show_feedback('active timer')
            with patch.object(window.store, 'save', side_effect=OSError('disk unavailable')):
                with self.assertLogs(level='ERROR'):
                    window.request_exit()
            self.assert_fully_stopped(window)
            self.assertEqual(path.read_bytes(), original)
            window.deleteLater()

    def test_wallpaper_has_native_input_transparency(self):
        from garden.window import PondWindow
        with tempfile.TemporaryDirectory() as directory:
            window = PondWindow(Path(directory) / 'state.json')
            self.assertTrue(bool(window.windowFlags() & Qt.WindowTransparentForInput))
            self.assertFalse(window.interaction.isVisible())
            window.shutdown()
            window.deleteLater()


if __name__ == '__main__':
    unittest.main()
