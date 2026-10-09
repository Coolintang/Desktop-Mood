"""Exercise the real desktop controls without touching the user's garden save."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QFrame, QPushButton, QWidget

from garden.constants import Tool
from garden.toolbar import FloatingOrb


class ControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.preview = QWidget()
        self.preview.resize(1000, 820)
        self.panel = FloatingOrb()
        self.panel.setParent(self.preview, Qt.Widget)
        self.panel.move(self.preview.width() - self.panel.width() - 20,
                        self.preview.height() - self.panel.height() - 20)
        self.preview.show()
        self.panel.show_wallpaper_level()
        self.app.processEvents()

    def tearDown(self):
        self.preview.close()
        self.preview.deleteLater()
        self.app.processEvents()

    def button(self, label):
        return next(button for button in self.panel.findChildren(QPushButton) if button.text() == label)

    def open_panel(self):
        QTest.mouseClick(self.button("春庭"), Qt.LeftButton)
        self.app.processEvents()

    def card_is_visible(self):
        return self.panel.findChild(QFrame, "controlCard").isVisible()

    def test_clicking_a_tool_again_cancels_and_switching_selects_one(self):
        changes = []
        self.panel.toolChanged.connect(changes.append)
        self.open_panel()
        feed, fish = self.button("投喂"), self.button("添鱼")
        QTest.mouseClick(feed, Qt.LeftButton)
        self.assertTrue(feed.isChecked())
        QTest.mouseClick(feed, Qt.LeftButton)
        self.assertFalse(feed.isChecked())
        QTest.mouseClick(feed, Qt.LeftButton)
        QTest.mouseClick(fish, Qt.LeftButton)
        self.assertFalse(feed.isChecked())
        self.assertTrue(fish.isChecked())
        self.assertEqual(changes, [Tool.FEED, Tool.NONE, Tool.FEED, Tool.ADD_FISH])

    def test_user_settings_emit_once_when_owner_synchronizes_them(self):
        changes = []

        def synchronize(name, value):
            changes.append((name, value))
            # The window echoes normalized persisted settings back to the UI.
            self.panel.set_preferences({name: value})

        self.panel.settingChanged.connect(synchronize)
        self.panel.set_preferences({"weather_mode": "rain", "fps": 30, "petals": True})
        self.assertEqual(changes, [])
        self.open_panel()
        QTest.mouseClick(self.button("60"), Qt.LeftButton)
        petals = next(control for control in self.panel.findChildren(QCheckBox) if control.text() == "樱花飘落")
        QTest.mouseClick(petals, Qt.LeftButton)
        time = next(control for control in self.panel.findChildren(QComboBox) if control.accessibleName() == "时光")
        time.setFocus()
        QTest.keyClick(time, Qt.Key_End)
        self.assertEqual(time.currentData(), "night")
        self.assertEqual(changes, [("fps", 60), ("petals", False), ("time_mode", "night")])

    def test_escape_cancels_tool_before_collapsing_panel(self):
        changes = []
        self.panel.toolChanged.connect(changes.append)
        self.open_panel()
        fish = self.button("添鱼")
        QTest.mouseClick(fish, Qt.LeftButton)
        QTest.keyClick(fish, Qt.Key_Escape)
        self.assertEqual(changes, [Tool.ADD_FISH, Tool.NONE])
        self.assertFalse(fish.isChecked())
        self.assertTrue(self.card_is_visible())
        QTest.keyClick(fish, Qt.Key_Escape)
        self.assertFalse(self.card_is_visible())
        self.assertTrue(self.button("春庭").isVisible())

    def test_escape_closes_weather_popup_before_collapsing_panel(self):
        self.open_panel()
        weather = next(control for control in self.panel.findChildren(QComboBox) if control.accessibleName() == "天气")
        QTest.mouseClick(weather, Qt.LeftButton)
        self.app.processEvents()
        self.assertTrue(weather.view().isVisible())
        QTest.keyClick(weather.view(), Qt.Key_Escape)
        self.assertFalse(weather.view().isVisible())
        self.assertTrue(self.card_is_visible())
        QTest.keyClick(weather, Qt.Key_Escape)
        self.assertFalse(self.card_is_visible())

    def test_anchor_small_preview_and_dragging_stay_within_parent(self):
        anchor = self.panel.geometry().bottomRight()
        QTest.mouseMove(self.button("春庭"))
        self.assertFalse(self.card_is_visible())
        self.open_panel()
        self.assertEqual(self.panel.geometry().bottomRight(), anchor)
        self.panel.collapse()
        self.assertEqual(self.panel.geometry().bottomRight(), anchor)

        self.preview.resize(540, 460)
        self.panel.move(300, 370)
        self.open_panel()
        self.assertTrue(self.preview.rect().contains(self.panel.geometry()))
        header = self.panel.findChild(QFrame, "panelHeader")
        QTest.mousePress(header, Qt.LeftButton, pos=QPoint(55, 16))
        QTest.mouseMove(header, QPoint(-2000, -2000), delay=1)
        QTest.mouseRelease(header, Qt.LeftButton, pos=QPoint(-2000, -2000))
        self.assertEqual(self.panel.pos(), QPoint(0, 0))
        QTest.mousePress(header, Qt.LeftButton, pos=QPoint(55, 16))
        QTest.mouseMove(header, QPoint(2000, 2000), delay=1)
        QTest.mouseRelease(header, Qt.LeftButton, pos=QPoint(2000, 2000))
        self.assertTrue(self.preview.rect().contains(self.panel.geometry()))
        self.assertEqual(self.panel.geometry().bottomRight(), self.preview.rect().bottomRight())
        self.panel.collapse()
        self.assertTrue(self.preview.rect().contains(self.panel.geometry()))


if __name__ == "__main__":
    unittest.main()
