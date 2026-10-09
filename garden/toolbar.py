"""A quiet, keyboard-accessible control panel for the Haruniwa desktop garden."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QKeySequence, QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QProgressBar, QPushButton, QScrollArea, QSizePolicy,
    QStackedLayout, QVBoxLayout, QWidget, QMenu,
)

from .constants import Tool


_INK = "#3F5D51"
_MUTED = "#839386"
_SAGE = "#70957C"


def _icon(name: str, color: str = _INK) -> QIcon:
    """Draw small, consistent line icons without platform-dependent glyphs."""
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.scale(64 / 24, 64 / 24)
    painter.setPen(QPen(QColor(color), 1.55, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.setBrush(Qt.NoBrush)

    def path(points):
        result = QPainterPath(QPoint(*points[0]))
        for point in points[1:]:
            result.lineTo(*point)
        painter.drawPath(result)

    if name == "flower":
        painter.save()
        painter.translate(12, 12)
        painter.setPen(QPen(QColor(color), 1.1))
        painter.setBrush(QColor("#F7E1E3"))
        for _ in range(5):
            painter.drawEllipse(QRectF(-2.8, -8.5, 5.6, 7.7))
            painter.rotate(72)
        painter.setBrush(QColor("#D5BB80"))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QRectF(-1.7, -1.7, 3.4, 3.4))
        painter.restore()
    elif name == "fish":
        curve = QPainterPath(QPoint(5, 12))
        curve.cubicTo(9, 5, 16, 5, 20, 12)
        curve.cubicTo(16, 19, 9, 19, 5, 12)
        painter.drawPath(curve)
        path([(5, 12), (2, 8), (2, 16), (5, 12)])
        painter.drawPoint(QPoint(16, 11))
        path([(10, 7), (11, 4), (15, 7)])
    elif name in ("water", "clean"):
        curve = QPainterPath(QPoint(11, 3))
        curve.cubicTo(8, 7, 5, 10, 5, 14)
        curve.cubicTo(5, 22, 17, 22, 17, 14)
        curve.cubicTo(17, 10, 14, 7, 11, 3)
        painter.drawPath(curve)
        curve = QPainterPath(QPoint(8, 13))
        curve.quadTo(7, 16, 10, 17)
        painter.drawPath(curve)
        if name == "clean":
            path([(19, 3), (19, 8)])
            path([(16.5, 5.5), (21.5, 5.5)])
    elif name == "feed":
        curve = QPainterPath(QPoint(3, 15))
        curve.cubicTo(5, 22, 19, 22, 21, 15)
        painter.drawPath(curve)
        painter.drawLine(3, 15, 21, 15)
        for x, y in [(8, 9), (14, 6), (16, 11)]:
            painter.drawEllipse(QRectF(x - 1, y - 1, 2, 2))
        path([(10, 3), (11, 1)])
    elif name == "plant":
        path([(12, 21), (12, 9)])
        curve = QPainterPath(QPoint(12, 14))
        curve.cubicTo(4, 15, 3, 10, 3, 6)
        curve.cubicTo(10, 6, 12, 10, 12, 14)
        painter.drawPath(curve)
        curve = QPainterPath(QPoint(12, 10))
        curve.cubicTo(12, 3, 18, 3, 21, 3)
        curve.cubicTo(21, 9, 18, 12, 12, 10)
        painter.drawPath(curve)
        painter.drawLine(7, 21, 17, 21)
    elif name == "erase":
        path([(4, 15), (13, 5), (20, 12), (13, 20), (9, 20), (4, 15)])
        path([(8, 11), (15, 18)])
        painter.drawLine(14, 20, 21, 20)
    elif name == "pause":
        painter.setPen(QPen(QColor(color), 2.7, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(8, 6, 8, 18)
        painter.drawLine(16, 6, 16, 18)
    elif name == "play":
        path([(8, 5), (19, 12), (8, 19), (8, 5)])
    elif name == "chevron":
        path([(6, 9), (12, 15), (18, 9)])
    elif name == "exit":
        path([(10, 4), (4, 4), (4, 20), (10, 20)])
        path([(10, 12), (21, 12)])
        path([(17, 8), (21, 12), (17, 16)])
    elif name == "clock":
        painter.drawEllipse(QRectF(3, 3, 18, 18))
        path([(12, 6), (12, 12), (16, 14)])
    elif name == "pointer":
        path([(5, 3), (7, 20), (11, 15), (15, 20), (18, 18), (14, 13), (20, 12), (5, 3)])
    painter.end()
    return QIcon(pixmap)


class _DragHeader(QFrame):
    """A header that moves the panel, without consuming its buttons' clicks."""
    def __init__(self, owner: "FloatingOrb"):
        super().__init__()
        self.owner = owner
        self._press_global = None
        self._press_panel = None
        self.setCursor(Qt.OpenHandCursor)
        self.setToolTip("按住标题拖动小庭面板")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press_global = event.globalPosition().toPoint()
            self._press_panel = self.owner.pos()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._press_global is not None and event.buttons() & Qt.LeftButton:
            self.owner._move_in_bounds(self._press_panel + event.globalPosition().toPoint() - self._press_global)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._press_global = None
        self.setCursor(Qt.OpenHandCursor)
        super().mouseReleaseEvent(event)


class _CapsuleButton(QPushButton):
    def __init__(self, owner: "FloatingOrb"):
        super().__init__("春庭", owner)
        self.owner = owner
        self._press_global = None
        self._press_panel = None
        self._dragged = False
        self.setAccessibleName("展开春庭控制面板")
        self.setToolTip("点击展开春庭；右键保存退出；按住可拖动")
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.clicked.connect(owner.expand)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(lambda point: owner.open_exit_menu(self.mapToGlobal(point)))

    def mousePressEvent(self, event):
        self._press_global = event.globalPosition().toPoint()
        self._press_panel = self.owner.pos()
        self._dragged = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._press_global is not None and event.buttons() & Qt.LeftButton:
            delta = event.globalPosition().toPoint() - self._press_global
            if delta.manhattanLength() >= QApplication.startDragDistance():
                self._dragged = True
            if self._dragged:
                self.setDown(False)
                self.owner._move_in_bounds(self._press_panel + delta)
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._press_global = None
        if self._dragged:
            self.setDown(False)
            self._dragged = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.8, 0.8, -0.8, -0.8)
        painter.setBrush(QColor("#FFFFF9" if self.underMouse() else "#FCFCF4"))
        painter.setPen(QPen(QColor(_SAGE if self.hasFocus() else "#D8E3D5"), 1.3))
        painter.drawRoundedRect(rect, 27, 27)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#F6E8E6"))
        painter.drawEllipse(QRectF(10, 10, 34, 34))
        _icon("flower", "#B58891").paint(painter, QRect(14, 14, 26, 26))
        font = QFont("Noto Serif CJK SC", 14)
        font.setWeight(QFont.DemiBold)
        painter.setFont(font)
        painter.setPen(QColor(_INK))
        painter.drawText(QRect(54, 5, 90, 29), Qt.AlignVCenter, "春庭")
        painter.setFont(QFont("Noto Sans CJK SC", 8))
        painter.setPen(QColor(_MUTED))
        painter.drawText(QRect(54, 31, 105, 16), Qt.AlignVCenter, "让日常慢下来" if self.owner._running else "小庭休憩中")
        _icon("chevron", _SAGE).paint(painter, QRect(self.width() - 28, 19, 16, 16))
        painter.end()


class _SettingCombo(QComboBox):
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(_MUTED), 1.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        center = self.height() / 2
        arrow = QPainterPath()
        arrow.moveTo(self.width() - 19, center - 2)
        arrow.lineTo(self.width() - 15, center + 2)
        arrow.lineTo(self.width() - 11, center - 2)
        painter.drawPath(arrow)
        painter.end()


class _Switch(QCheckBox):
    """A native, focusable checkbox drawn as a small, legible toggle."""
    def __init__(self, text: str):
        super().__init__(text)
        self.setFixedHeight(30)
        self.setMinimumWidth(130)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def hitButton(self, position):
        return self.rect().contains(position)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setFont(self.font())
        painter.setPen(QColor(_INK))
        painter.drawText(self.rect().adjusted(2, 0, -39, 0), Qt.AlignVCenter, self.text())
        track = QRectF(self.width() - 34, 6, 32, 18)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(_SAGE if self.isChecked() else "#D9DED4"))
        painter.drawRoundedRect(track, 9, 9)
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawEllipse(QRectF(track.x() + (16 if self.isChecked() else 3), 9, 12, 12))
        if self.hasFocus():
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(_SAGE), 1, Qt.DotLine))
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 5, 5)
        painter.end()


class FloatingOrb(QWidget):
    """A folded garden capsule and an explicitly opened desktop control card.

    These are ordinary lowered tool windows so normal applications cover them.
    When embedded in the preview, all geometry uses the parent coordinate space.
    """
    toolChanged = Signal(object)
    runningChanged = Signal(bool)
    exitRequested = Signal()
    settingChanged = Signal(str, object)

    ITEMS = [
        (Tool.FEED, "feed", "投喂"),
        (Tool.WATER_PLANT, "water", "浇水"),
        (Tool.CHANGE_WATER, "clean", "净水"),
        (Tool.ADD_FISH, "fish", "添鱼"),
        (Tool.ADD_PLANT, "plant", "种花"),
        (Tool.ERASE, "erase", "移除"),
    ]
    DESCRIPTIONS = {
        Tool.NONE: "选择一件小事，轻触池塘，照料你的春庭。",
        Tool.FEED: "轻触水面撒下鱼食，小鱼会游来相聚。",
        Tool.WATER_PLANT: "轻触水生植物，为它浇水，陪它慢慢长大。",
        Tool.CHANGE_WATER: "轻触池塘换入清水，让水面恢复澄澈。",
        Tool.ADD_FISH: "轻触水面，邀请一尾小鱼住进春庭。",
        Tool.ADD_PLANT: "轻触池塘种下水生植物，等待下一次花开。",
        Tool.ERASE: "轻触想移走的鱼或植物，将它从小庭中移除。",
    }
    DEFAULTS = {
        "wallpaper_mode": "scene", "time_mode": "live", "weather_mode": "auto",
        "fps": 30, "petals": True, "show_clock": True,
    }

    def __init__(self):
        super().__init__()
        self._expanded = False
        self._closing_for_shutdown = False
        self._active = Tool.NONE
        self._running = True
        self._preferences = dict(self.DEFAULTS)
        self._tool_buttons = {}
        self._combos = {}
        self._setting_buttons = {}
        self._context = None
        self._feedback_timer = QTimer(self)
        self._feedback_timer.setSingleShot(True)
        self._feedback_timer.timeout.connect(self._restore_description)
        self.setObjectName("gardenControl")
        self.setWindowTitle("春庭 · HARUNIWA")
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFont(QFont("Noto Sans CJK SC", 9))
        self.setStyleSheet(self._stylesheet())
        self.exit_action = QAction("保存并退出", self)
        self.exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        self.exit_action.setShortcutContext(Qt.ApplicationShortcut)
        self.exit_action.triggered.connect(self.exitRequested.emit)
        self.addAction(self.exit_action)
        self._exit_menu = QMenu(self)
        self._exit_menu.addAction("展开照料面板", self.expand)
        self._exit_menu.addSeparator()
        self._exit_menu.addAction(self.exit_action)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(lambda point: self.open_exit_menu(self.mapToGlobal(point)))
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(8, 8, 8, 8)
        self._stack = QStackedLayout()
        outer_layout.addLayout(self._stack)
        self._capsule = _CapsuleButton(self)
        self._stack.addWidget(self._capsule)
        self._panel = self._build_panel()
        self._stack.addWidget(self._panel)
        self._stack.setCurrentWidget(self._capsule)
        self.setFixedSize(202, 70)
        self.set_preferences(self.DEFAULTS)
        self.set_context(0, 0, 100, "sunny")

    @staticmethod
    def _stylesheet():
        return """
            QWidget#gardenControl { color: #3F5D51; font-size: 12px; }
            QFrame#controlCard { background: #FCFCF5; border: 1px solid #DCE4D6; border-radius: 22px; }
            QFrame#panelHeader, QFrame#panelFooter, QWidget#scrollContent { background: transparent; border: none; }
            QLabel { color: #3F5D51; background: transparent; border: none; }
            QLabel#brand { font-family: 'Noto Serif CJK SC'; font-size: 23px; font-weight: 600; color: #3F5D51; }
            QLabel#brandRoman { color: #929C88; font-size: 9px; letter-spacing: 2px; }
            QLabel#sectionTitle { color: #536E5D; font-size: 12px; font-weight: 600; }
            QLabel#muted { color: #929E91; font-size: 10px; }
            QLabel#weatherBadge { color: #728772; font-size: 10px; background: #E5EDDE; border-radius: 9px; padding: 3px 9px; }
            QFrame#pondStats { background: #EFF3E7; border-radius: 14px; border: 1px solid #E7ECDE; }
            QLabel#statValue { font-size: 23px; font-weight: 500; color: #50745E; }
            QLabel#statLabel { font-size: 10px; color: #8B9781; }
            QProgressBar { background: #DFE8D8; border: none; border-radius: 2px; min-height: 4px; max-height: 4px; }
            QProgressBar::chunk { background: #9DB89A; border-radius: 2px; }
            QPushButton { background: #F3F5EC; border: 1px solid #E3E8DB; border-radius: 10px; color: #52705C; padding: 6px 10px; font-size: 12px; }
            QPushButton:hover { background: #EAF0E1; border-color: #C3D3BF; }
            QPushButton:pressed { background: #DFE8D6; }
            QPushButton:focus { border: 1px solid #749781; }
            QPushButton:checked { background: #E1EBD9; color: #47674F; border: 1px solid #A8C2A0; }
            QPushButton#toolButton { background: #F9FAF3; border-radius: 11px; padding: 9px 6px; }
            QPushButton#toolButton:hover { background: #EFF3E6; border-color: #BECEB4; }
            QPushButton#toolButton:checked { background: #E4EDDB; border-color: #A2BE9B; color: #42654C; }
            QPushButton#iconButton { border: none; border-radius: 13px; background: transparent; padding: 5px; }
            QPushButton#iconButton:hover { background: #EBF0E3; }
            QPushButton#iconButton:focus { border: 1px solid #749781; }
            QPushButton#pauseButton { background: #E5EDDB; border-color: #D7E3CF; }
            QPushButton#pauseButton:hover { background: #DCE7CF; }
            QPushButton#exitButton { color: #9A8D84; background: transparent; border-color: transparent; }
            QPushButton#exitButton:hover { background: #F4E9E4; color: #A06E69; }
            QPushButton#exitButton:focus { border-color: #B99791; }
            QPushButton#fpsButton { font-size: 11px; padding: 3px 8px; border-radius: 8px; }
            QFrame#toolHelp { background: #F4F0E5; border: none; border-radius: 10px; }
            QLabel#toolDescription { color: #8B8B74; font-size: 10px; }
            QComboBox { color: #5A715F; background: #F8F9F1; border: 1px solid #DEE5D6; border-radius: 9px; padding: 7px 10px; font-size: 11px; min-height: 17px; }
            QComboBox:hover { border-color: #B9CBAF; }
            QComboBox:focus { border-color: #749781; }
            QComboBox::drop-down { border: none; width: 24px; }
            QComboBox::down-arrow { image: none; }
            QComboBox QAbstractItemView { color: #496752; background: #FCFCF5; border: 1px solid #CCD9C2; selection-background-color: #E3EDDA; selection-color: #3F5D51; padding: 5px; outline: 0; }
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { background: transparent; width: 5px; margin: 4px 0; }
            QScrollBar::handle:vertical { background: #CCD9C1; border-radius: 2px; min-height: 28px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
            QToolTip { color: #45604F; background: #FCFCF3; border: 1px solid #CFDAC5; padding: 6px; }
        """

    def _label(self, text, object_name=None):
        label = QLabel(text)
        if object_name:
            label.setObjectName(object_name)
        return label

    def _build_panel(self):
        panel = QFrame()
        panel.setObjectName("controlCard")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(17, 14, 17, 12)
        layout.setSpacing(10)

        header = _DragHeader(self)
        header.setObjectName("panelHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(11)
        flower = QLabel()
        flower.setPixmap(_icon("flower", "#B08A91").pixmap(39, 39))
        flower.setAttribute(Qt.WA_TransparentForMouseEvents)
        header_layout.addWidget(flower)
        branding = QVBoxLayout()
        branding.setSpacing(0)
        title = self._label("春庭", "brand")
        roman = self._label("HARUNIWA  /  庭间一刻", "brandRoman")
        for label in (title, roman):
            label.setAttribute(Qt.WA_TransparentForMouseEvents)
            branding.addWidget(label)
        header_layout.addLayout(branding, 1)
        collapse_button = QPushButton()
        collapse_button.setObjectName("iconButton")
        collapse_button.setIcon(_icon("chevron"))
        collapse_button.setIconSize(QSize(20, 20))
        collapse_button.setFixedSize(30, 30)
        collapse_button.setAccessibleName("收起控制面板")
        collapse_button.setToolTip("收起面板（Esc）")
        collapse_button.clicked.connect(self.collapse)
        header_layout.addWidget(collapse_button)
        layout.addWidget(header)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.viewport().setAutoFillBackground(False)
        body = QWidget()
        body.setObjectName("scrollContent")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 2, 0)
        body_layout.setSpacing(10)

        stats = QFrame()
        stats.setObjectName("pondStats")
        stats_layout = QVBoxLayout(stats)
        stats_layout.setContentsMargins(14, 10, 14, 12)
        stats_layout.setSpacing(7)
        stats_heading = QHBoxLayout()
        stats_heading.addWidget(self._label("今日池塘", "sectionTitle"))
        stats_heading.addStretch()
        self._weather_badge = self._label("晴空", "weatherBadge")
        stats_heading.addWidget(self._weather_badge)
        stats_layout.addLayout(stats_heading)
        values = QHBoxLayout()
        self._stat_values = []
        for title_text in ("尾游鱼", "株水生植物", "水质 · 清澈"):
            column = QVBoxLayout()
            column.setSpacing(0)
            value = self._label("00", "statValue")
            caption = self._label(title_text, "statLabel")
            self._stat_values.append((value, caption))
            column.addWidget(value)
            column.addWidget(caption)
            values.addLayout(column, 1)
        stats_layout.addLayout(values)
        self._water_bar = QProgressBar()
        self._water_bar.setRange(0, 100)
        self._water_bar.setTextVisible(False)
        self._water_bar.setAccessibleName("池塘水质")
        stats_layout.addWidget(self._water_bar)
        body_layout.addWidget(stats)

        tool_section = QVBoxLayout()
        tool_section.setSpacing(8)
        tool_heading = QHBoxLayout()
        tool_heading.addWidget(self._label("照料小庭", "sectionTitle"))
        tool_heading.addStretch()
        tool_heading.addWidget(self._label("一念之间，万物生长", "muted"))
        tool_section.addLayout(tool_heading)
        tools_grid = QGridLayout()
        tools_grid.setSpacing(7)
        for index, (tool, icon_name, label) in enumerate(self.ITEMS):
            button = QPushButton(label)
            button.setObjectName("toolButton")
            button.setCheckable(True)
            button.setIcon(_icon(icon_name))
            button.setIconSize(QSize(21, 21))
            button.setMinimumHeight(44)
            button.setCursor(Qt.PointingHandCursor)
            button.setToolTip(self.DESCRIPTIONS[tool] + "\n选择后点击池塘使用；再次点击工具或按 Esc 取消。")
            button.clicked.connect(lambda checked=False, selected=tool: self._choose_tool(selected))
            tools_grid.addWidget(button, index // 3, index % 3)
            self._tool_buttons[tool] = button
        tool_section.addLayout(tools_grid)
        help_card = QFrame()
        help_card.setObjectName("toolHelp")
        help_layout = QHBoxLayout(help_card)
        help_layout.setContentsMargins(10, 7, 10, 7)
        help_layout.setSpacing(8)
        pointer = QLabel()
        pointer.setPixmap(_icon("pointer", "#A29B7E").pixmap(16, 16))
        help_layout.addWidget(pointer, 0, Qt.AlignTop)
        self._description = self._label(self.DESCRIPTIONS[Tool.NONE], "toolDescription")
        self._description.setWordWrap(True)
        self._description.setMinimumHeight(28)
        self._description.setAccessibleName("当前工具提示")
        help_layout.addWidget(self._description, 1)
        tool_section.addWidget(help_card)
        body_layout.addLayout(tool_section)

        settings = QVBoxLayout()
        settings.setSpacing(8)
        settings.addWidget(self._label("把喜欢的天气留在桌面", "sectionTitle"))
        climate_row = QHBoxLayout()
        climate_row.setSpacing(9)
        climate_row.addLayout(self._combo_field("时光", "time_mode", [
            ("跟随此刻", "live"), ("澄净白昼", "day"), ("落日余晖", "dusk"), ("静谧月夜", "night"),
        ]), 1)
        climate_row.addLayout(self._combo_field("天气", "weather_mode", [
            ("自然变化", "auto"), ("晴空", "sunny"), ("薄云", "cloudy"), ("细雨", "rain"), ("初雪", "snow"),
        ]), 1)
        settings.addLayout(climate_row)
        settings.addLayout(self._combo_field("桌面呈现", "wallpaper_mode", [
            ("完整场景 · 动漫壁纸", "scene"), ("透明池塘 · 保留原壁纸", "overlay"),
        ]))
        animation_row = QHBoxLayout()
        animation_row.setSpacing(5)
        animation_row.addWidget(self._label("动画帧率", "muted"))
        animation_row.addStretch()
        self._fps_group = QButtonGroup(self)
        self._fps_group.setExclusive(True)
        for fps in (24, 30, 60):
            button = QPushButton(str(fps))
            button.setObjectName("fpsButton")
            button.setCheckable(True)
            button.setFixedSize(42, 27)
            button.setAccessibleName(f"每秒 {fps} 帧")
            button.setToolTip(f"每秒 {fps} 帧" + (" · 轻省电量" if fps == 24 else " · 日常推荐" if fps == 30 else " · 更顺滑"))
            self._fps_group.addButton(button, fps)
            animation_row.addWidget(button)
        animation_row.addWidget(self._label("fps", "muted"))
        self._fps_group.idClicked.connect(lambda fps: self._change_setting("fps", fps))
        settings.addLayout(animation_row)
        toggles = QHBoxLayout()
        toggles.setSpacing(15)
        for key, label in (("petals", "樱花飘落"), ("show_clock", "桌面时钟")):
            toggle = _Switch(label)
            toggle.setToolTip("在桌面上显示飘落的樱花花瓣" if key == "petals" else "在桌面上显示日期与时间")
            toggle.toggled.connect(lambda checked, name=key: self._change_setting(name, checked))
            self._setting_buttons[key] = toggle
            toggles.addWidget(toggle, 1)
        settings.addLayout(toggles)
        body_layout.addLayout(settings)
        body_layout.addStretch()
        self._scroll.setWidget(body)
        layout.addWidget(self._scroll, 1)

        footer = QFrame()
        footer.setObjectName("panelFooter")
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.setSpacing(7)
        actions = QHBoxLayout()
        actions.setSpacing(7)
        self._pause_button = QPushButton("暂停片刻")
        self._pause_button.setObjectName("pauseButton")
        self._pause_button.setIcon(_icon("pause"))
        self._pause_button.setIconSize(QSize(16, 16))
        self._pause_button.setMinimumHeight(35)
        self._pause_button.setToolTip("暂停或继续小庭的动画与生长")
        self._pause_button.clicked.connect(self._toggle_running)
        actions.addWidget(self._pause_button, 1)
        exit_button = QPushButton("退出")
        exit_button.setObjectName("exitButton")
        exit_button.setIcon(_icon("exit", "#9A8D84"))
        exit_button.setIconSize(QSize(16, 16))
        exit_button.setMinimumHeight(35)
        exit_button.setToolTip("保存小庭并退出应用（Ctrl+Q）")
        exit_button.setAccessibleName("保存并退出春庭")
        exit_button.clicked.connect(self.exit_action.trigger)
        actions.addWidget(exit_button)
        footer_layout.addLayout(actions)
        note = self._label("Esc 取消工具 / 收起面板 · 按住标题可拖动", "muted")
        note.setAlignment(Qt.AlignCenter)
        footer_layout.addWidget(note)
        layout.addWidget(footer)
        return panel

    def _combo_field(self, label, key, choices):
        field = QVBoxLayout()
        field.setSpacing(4)
        caption = self._label(label, "muted")
        field.addWidget(caption)
        combo = _SettingCombo()
        combo.setAccessibleName(label)
        for title, value in choices:
            combo.addItem(title, value)
        combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(5)
        combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        combo.setCursor(Qt.PointingHandCursor)
        combo.setToolTip({
            "time_mode": "跟随北京时间（Asia/Shanghai），或让小庭停留在喜欢的时光",
            "weather_mode": "选择自然变化，或固定一种天气",
            "wallpaper_mode": "完整场景铺满桌面；透明池塘叠加在原有壁纸上",
        }[key])
        combo.currentIndexChanged.connect(lambda index, name=key, control=combo: self._change_setting(name, control.itemData(index)))
        caption.setBuddy(combo)
        self._combos[key] = combo
        field.addWidget(combo)
        return field

    def _bounds(self):
        parent = self.parentWidget()
        if parent is not None:
            return parent.rect()
        screen = QApplication.screenAt(self.frameGeometry().center()) or self.screen() or QApplication.primaryScreen()
        return screen.availableGeometry() if screen is not None else QRect(0, 0, 1280, 720)

    def _move_in_bounds(self, position):
        bounds = self._bounds()
        max_x = max(bounds.left(), bounds.right() - self.width() + 1)
        max_y = max(bounds.top(), bounds.bottom() - self.height() + 1)
        self.move(max(bounds.left(), min(position.x(), max_x)), max(bounds.top(), min(position.y(), max_y)))

    def _resize_anchored(self, width, height):
        bottom_right = self.geometry().bottomRight()
        bounds = self._bounds()
        width = min(width, bounds.width())
        height = min(height, bounds.height())
        self.setFixedSize(width, height)
        self._move_in_bounds(QPoint(bottom_right.x() - width + 1, bottom_right.y() - height + 1))

    def show_wallpaper_level(self):
        self._move_in_bounds(self.pos())
        self.show()
        if self.parentWidget() is None:
            self.lower()

    def expand(self):
        if self._expanded:
            return
        self._expanded = True
        self._stack.setCurrentWidget(self._panel)
        self._resize_anchored(382, 695)
        self._tool_buttons[Tool.FEED].setFocus(Qt.OtherFocusReason)
        self.update()

    def collapse(self):
        if not self._expanded:
            return
        self._expanded = False
        self._stack.setCurrentWidget(self._capsule)
        self._resize_anchored(202, 70)
        self._capsule.setFocus(Qt.OtherFocusReason)
        self.update()

    def _choose_tool(self, tool):
        active = Tool.NONE if self._active == tool else tool
        self.set_active_tool(active)
        self.toolChanged.emit(active)

    def set_active_tool(self, tool: Tool):
        self._active = tool
        self._feedback_timer.stop()
        for key, button in self._tool_buttons.items():
            button.setChecked(key == tool)
        self._restore_description()

    def _restore_description(self):
        self._description.setText(self.DESCRIPTIONS.get(self._active, self.DESCRIPTIONS[Tool.NONE]))

    def _toggle_running(self):
        self.set_running(not self._running)
        self.runningChanged.emit(self._running)

    def set_running(self, running: bool):
        self._running = bool(running)
        self._pause_button.setText("暂停片刻" if running else "继续生长")
        self._pause_button.setIcon(_icon("pause" if running else "play"))
        self._capsule.update()

    def _change_setting(self, name, value):
        if value is None or self._preferences.get(name) == value:
            return
        self._preferences[name] = value
        self.settingChanged.emit(name, value)

    def set_preferences(self, preferences: dict):
        """Synchronize persisted settings without emitting user-change signals."""
        for name, value in preferences.items():
            if name in self.DEFAULTS:
                self._preferences[name] = value
        for name, combo in self._combos.items():
            index = combo.findData(self._preferences[name])
            if index >= 0:
                combo.blockSignals(True)
                combo.setCurrentIndex(index)
                combo.blockSignals(False)
        fps_button = self._fps_group.button(int(self._preferences["fps"]))
        if fps_button is not None:
            fps_button.setChecked(True)
        for name, toggle in self._setting_buttons.items():
            toggle.blockSignals(True)
            toggle.setChecked(bool(self._preferences[name]))
            toggle.blockSignals(False)

    def set_context(self, fish_count, plant_count, quality, weather):
        quality = max(0, min(100, round(float(quality))))
        weather = str(getattr(weather, "value", weather))
        context = (int(fish_count), int(plant_count), quality, weather)
        if context == self._context:
            return
        self._context = context
        self._stat_values[0][0].setText(f"{context[0]:02d}")
        self._stat_values[1][0].setText(f"{context[1]:02d}")
        self._stat_values[2][0].setText(f"{quality}%")
        self._stat_values[2][1].setText("水质 · " + ("清澈" if quality >= 75 else "尚好" if quality >= 45 else "待净水"))
        self._water_bar.setValue(quality)
        self._water_bar.setAccessibleDescription(f"水质百分之 {quality}")
        self._weather_badge.setText({"sunny": "晴空", "cloudy": "薄云", "rain": "细雨", "snow": "初雪", "auto": "自然变化"}.get(weather, weather))

    def show_feedback(self, message: str):
        if self._closing_for_shutdown:
            return
        self._description.setText(str(message))
        self._feedback_timer.start(4500)

    def open_exit_menu(self, global_position):
        if not self._closing_for_shutdown:
            self._exit_menu.popup(global_position)

    def close_for_shutdown(self):
        """Close the UI without sending another application-exit request."""
        already_closing = self._closing_for_shutdown
        self._closing_for_shutdown = True
        self._feedback_timer.stop()
        self._exit_menu.close()
        if already_closing:
            self.hide()
        else:
            self.close()

    def closeEvent(self, event):
        # Closing a standalone tool window doesn't trigger Qt's last-window
        # policy. Forward the desktop/window-manager close to the application.
        requested_by_user = not self._closing_for_shutdown
        self._closing_for_shutdown = True
        self._feedback_timer.stop()
        self._exit_menu.close()
        event.accept()
        if requested_by_user:
            self.exitRequested.emit()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            if self._active != Tool.NONE:
                self.set_active_tool(Tool.NONE)
                self.toolChanged.emit(Tool.NONE)
            else:
                self.collapse()
            event.accept()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        radius = 25 if self._expanded else 31
        for spread, alpha in ((6, 4), (4, 5), (2, 7)):
            painter.setBrush(QColor(47, 70, 48, alpha))
            shadow = QRectF(self.rect()).adjusted(8 - spread, 10 - spread, -8 + spread, -5 + spread)
            painter.drawRoundedRect(shadow, radius + spread, radius + spread)
        painter.end()
