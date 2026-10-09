from __future__ import annotations
import logging
import math
from PySide6.QtCore import Qt, QTimer, QElapsedTimer
from PySide6.QtGui import QPainter, QRegion, QIcon, QPixmap, QColor, QActionGroup
from PySide6.QtWidgets import QWidget, QApplication, QSystemTrayIcon, QMenu
from .constants import Tool
from .models import normalize_preferences
from .state import StateStore
from .scene import PondScene
from .toolbar import FloatingOrb


class InteractionWindow(QWidget):
    """Input exists only over the pond, while a tool is selected."""
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.setMouseTracking(True)
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

    def activate_for_tool(self):
        self.setGeometry(self.owner.geometry())
        r = self.owner.scene.pond_rect(self.width(), self.height()).adjusted(-16, -16, 16, 16)
        self.setMask(QRegion(r.toAlignedRect(), QRegion.Ellipse))
        self.show()
        self.lower()
        self.setCursor(Qt.CrossCursor)

    def deactivate(self):
        self.hide()

    def mouseMoveEvent(self, event):
        self.owner.scene.hover = (event.position().x(), event.position().y())
        self.owner.update()

    def leaveEvent(self, event):
        self.owner.scene.hover = None
        self.owner.update()

    def mousePressEvent(self, event):
        self.owner.handle_pond_click(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.owner.cancel_tool()
        else:
            super().keyPressEvent(event)


class PondWindow(QWidget):
    """Wallpaper visuals and independent input; preview uses a normal window.

    Native layering/input hints depend on the Linux compositor. Preview works
    without desktop-layer support, including restrictive Wayland compositors.
    """
    def __init__(self, state_path="data/state.json", preview=False, screen_name=None):
        super().__init__()
        self.preview = preview
        self.setMouseTracking(True)
        self._shutting_down = False
        self._screen = None
        self.store = StateStore(state_path)
        self.state = self.store.load()
        self.scene = PondScene(self.state)
        self.tool = Tool.NONE
        self.running = True
        self.setWindowTitle("春庭 · Haruniwa")
        self.setMinimumSize(640, 420)
        if not preview:
            self.setAttribute(Qt.WA_TranslucentBackground)
            self.setAttribute(Qt.WA_TransparentForMouseEvents)
            self.setAttribute(Qt.WA_ShowWithoutActivating)
            self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnBottomHint |
                                Qt.WindowDoesNotAcceptFocus | Qt.WindowTransparentForInput)
        self.interaction = InteractionWindow(self)
        self.orb = FloatingOrb()
        if preview:
            self.orb.setParent(self, Qt.Widget)
        self.orb.toolChanged.connect(self.set_tool)
        self.orb.runningChanged.connect(self.set_running)
        self.orb.exitRequested.connect(self.request_exit)
        self.orb.settingChanged.connect(self.set_preference)
        self.orb.set_preferences(self.state.preferences)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.elapsed = QElapsedTimer()
        self.elapsed.start()
        self.timer.start(self.frame_interval())
        self.save_timer = QTimer(self)
        self.save_timer.timeout.connect(self.save_state)
        self.save_timer.start(30000)
        self.layer_timer = QTimer(self)
        self.layer_timer.timeout.connect(self._maintain_wallpaper_layer)
        if not preview:
            self.layer_timer.start(1500)
        self.tray = None
        self._create_tray()
        app = QApplication.instance()
        app.aboutToQuit.connect(self.shutdown)
        app.screenAdded.connect(self._screens_changed)
        app.screenRemoved.connect(self._screens_changed)
        screens = app.screens()
        self.select_screen(next((s for s in screens if s.name() == screen_name), app.primaryScreen()))
        if preview:
            self.resize(1200, 760)
        self.refresh_context()
        if self.store.last_error:
            self.orb.show_feedback("存档读取失败：保留原文件，本次不会覆盖保存")

    @property
    def toolbar(self):
        return self.orb

    def frame_interval(self):
        return round(1000 / self.state.preferences['fps'])

    def _create_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor('#7bbcb4'))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(2, 2, 28, 28)
        painter.setBrush(QColor('#fff1ed'))
        for index in range(5):
            angle = index * math.tau / 5 - math.pi / 2
            painter.drawEllipse(round(12 + math.cos(angle) * 6), round(12 + math.sin(angle) * 6), 8, 8)
        painter.setBrush(QColor('#e5ba65'))
        painter.drawEllipse(13, 13, 6, 6)
        painter.end()
        self.tray = QSystemTrayIcon(QIcon(pixmap), self)
        self.tray.setToolTip("春庭 · Haruniwa")
        menu = QMenu(self)
        menu.addAction("显示控制面板", self.show_controls)
        self.pause_action = menu.addAction("暂停动画")
        self.pause_action.setCheckable(True)
        self.pause_action.triggered.connect(lambda paused: self.set_running(not paused))
        modes = menu.addMenu("壁纸模式")
        self.mode_group = QActionGroup(self)
        self.mode_actions = {}
        for label, value in (("完整庭院", "scene"), ("透明池塘", "overlay")):
            action = modes.addAction(label)
            action.setCheckable(True)
            self.mode_group.addAction(action)
            action.setChecked(self.state.preferences['wallpaper_mode'] == value)
            action.triggered.connect(lambda checked, mode=value: self.set_preference('wallpaper_mode', mode))
            self.mode_actions[value] = action
        self.screen_menu = menu.addMenu("显示器")
        self.screen_menu.aboutToShow.connect(self._populate_screens)
        menu.addSeparator()
        menu.addAction("保存并退出", self.request_exit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.show_controls()
                                    if reason == QSystemTrayIcon.Trigger else None)
        self.tray.show()

    def _populate_screens(self):
        self.screen_menu.clear()
        for screen in QApplication.screens():
            action = self.screen_menu.addAction(screen.name())
            action.setCheckable(True)
            action.setChecked(screen is self._screen)
            action.triggered.connect(lambda checked, selected=screen: self.select_screen(selected))

    def select_screen(self, screen):
        if screen is None:
            return
        if self._screen is not None:
            try:
                self._screen.geometryChanged.disconnect(self._screen_geometry_changed)
            except (RuntimeError, TypeError):
                pass
        self._screen = screen
        screen.geometryChanged.connect(self._screen_geometry_changed)
        if self.preview:
            self.move(screen.availableGeometry().topLeft())
        else:
            self.setGeometry(screen.geometry())
        self.position_controls()
        if self.tool != Tool.NONE and not self.preview:
            self.interaction.activate_for_tool()

    def _screen_geometry_changed(self, *_):
        if not self.preview:
            self.setGeometry(self._screen.geometry())
        self.position_controls()
        if self.tool != Tool.NONE and not self.preview:
            self.interaction.activate_for_tool()

    def _screens_changed(self, *_):
        screens = QApplication.screens()
        if self._screen not in screens:
            self._screen = None
            self.select_screen(QApplication.primaryScreen())
        else:
            self._screen_geometry_changed()

    def position_controls(self):
        if not hasattr(self, 'orb'):
            return
        bounds = self.rect() if self.preview else self._screen.availableGeometry()
        self.orb.move(max(bounds.left(), bounds.right() - self.orb.width() - 24),
                      max(bounds.top(), bounds.bottom() - self.orb.height() - 24))

    def show_controls(self):
        if self._shutting_down:
            return
        self.position_controls()
        self.orb.show()
        self.orb.expand()
        self.orb.raise_()
        if self.preview:
            self.show()
            self.raise_()

    def show_layers(self):
        if self._shutting_down:
            return
        self.show()
        if not self.preview:
            self.lower()
        self.orb.show_wallpaper_level()

    def _maintain_wallpaper_layer(self):
        if self._shutting_down:
            return
        self.lower()
        if self.interaction.isVisible():
            self.interaction.lower()

    def set_tool(self, tool):
        if self._shutting_down:
            return
        self.tool = Tool(tool)
        self.scene.tool = self.tool
        if self.tool == Tool.NONE:
            self.scene.hover = None
        self.orb.set_active_tool(self.tool)
        if self.preview or self.tool == Tool.NONE:
            self.interaction.deactivate()
        else:
            self.interaction.activate_for_tool()
        self.update()

    def cancel_tool(self):
        self.set_tool(Tool.NONE)

    def set_preference(self, key, value):
        if self._shutting_down:
            return
        self.state.preferences = normalize_preferences({**self.state.preferences, key: value})
        self.orb.set_preferences(self.state.preferences)
        if self.tray:
            self.mode_actions[self.state.preferences['wallpaper_mode']].setChecked(True)
        if self.running:
            self.timer.setInterval(self.frame_interval())
        self.save_state()
        self.refresh_context()
        if self.tool != Tool.NONE and not self.preview:
            self.interaction.activate_for_tool()
        self.update()

    def set_running(self, running):
        if self._shutting_down:
            return
        self.running = bool(running)
        self.orb.set_running(self.running)
        if self.tray:
            self.pause_action.setChecked(not self.running)
        if self.running:
            self.elapsed.restart()
            self.timer.start(self.frame_interval())
        else:
            self.timer.stop()
            self.cancel_tool()
        self.update()

    def refresh_context(self):
        weather = self.state.preferences['weather_mode']
        self.orb.set_context(len(self.state.fish), len(self.state.plants), self.state.water_quality,
                             self.state.weather if weather == 'auto' else weather)

    def tick(self):
        if not self.running:
            return
        dt = min(self.elapsed.restart() / 1000.0, 0.25)
        self.scene.update(dt)
        self.refresh_context()
        self.update()

    def handle_pond_click(self, event):
        if event.button() == Qt.RightButton:
            self.cancel_tool()
        elif event.button() == Qt.LeftButton and self.tool != Tool.NONE:
            point = event.position()
            message = self.scene.apply_tool(self.tool, point.x(), point.y(), self.width(), self.height())
            if message:
                self.orb.show_feedback(message)
            self.refresh_context()
            self.update()
        event.accept()

    def mouseMoveEvent(self, event):
        if self.preview:
            self.scene.hover = (event.position().x(), event.position().y())
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.scene.hover = None
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if self.preview:
            self.handle_pond_click(event)
        else:
            super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            if self.tool != Tool.NONE:
                self.cancel_tool()
            else:
                self.orb.collapse()
            event.accept()
        else:
            super().keyPressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.preview:
            self.position_controls()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        self.scene.paint(painter, self.width(), self.height())

    def save_state(self):
        ok = self.store.save(self.state)
        if not ok:
            logging.warning("Could not save pond state: %s", self.store.last_error)
            self.orb.show_feedback("保存失败，原存档已保留；请检查文件权限或磁盘空间")
        return ok

    def shutdown(self):
        if self._shutting_down:
            return
        self._shutting_down = True
        self.running = False
        self.tool = self.scene.tool = Tool.NONE
        self.scene.hover = None
        self.timer.stop()
        self.save_timer.stop()
        self.layer_timer.stop()
        try:
            self.save_state()
        except Exception:
            # A disk or unexpected serialization error must never trap the user
            # in a borderless wallpaper. StateStore normally reports failures.
            logging.exception("Could not save pond state during shutdown")
        finally:
            self.interaction.close()
            self.orb.close_for_shutdown()
            self.hide()
            if self.tray:
                self.tray.hide()

    def request_exit(self):
        try:
            self.shutdown()
        finally:
            QApplication.instance().quit()

    def closeEvent(self, event):
        self.request_exit()
        event.accept()
