"""Render isolated garden fixtures; never read or change the user's saved pond."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import random

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtWidgets import QApplication, QWidget

from garden.constants import Tool
from garden.models import AppState, Fish, Plant
from garden.scene import PondScene
from garden.toolbar import FloatingOrb
from garden.notes import NoteWidget
from garden.chat_widget import ChatWidget
from garden.lan_chat import LanChat
from garden.growth import growth_summary, fish_stage, plant_phase
from garden.fish import paint_fish
from garden.plant import paint_plant


def sample_state():
    return AppState(
        fish=[Fish(.46, .55, 'koi', angle=.25, size=1.14, phase=1.2, id=1),
              Fish(.30, .69, 'goldfish', angle=-.6, size=.9, phase=.4, id=2),
              Fish(.64, .36, 'neon', angle=2.8, size=.75, phase=2.1, id=3),
              Fish(.71, .65, 'koi', angle=-2.5, size=.85, phase=.8, id=4)],
        plants=[Plant(.23, .40, age_hours=38, phase=.5, id=11),
                Plant(.75, .31, age_hours=28, phase=1.5, id=12),
                Plant(.63, .63, age_hours=42, phase=.8, id=13)],
        weather_until=4102444800,
    )


def render_scene(out: Path, name: str, hour: float, weather: str, quality=100,
                 width=1600, height=900, overlay=False, controls=False, feed=False, note=False, chat=False, unread=False):
    state = sample_state()
    state.water_quality = quality
    state.preferences.update(wallpaper_mode='overlay' if overlay else 'scene', time_mode='day', weather_mode=weather)
    scene = PondScene(state)
    scene.t = 12.5
    if feed:
        q = scene.pond_rect(width, height).center()
        random.seed(42)
        scene.apply_tool(Tool.FEED, q.x(), q.y(), width, height)
        scene.ripples[0].age = .65
        scene.tool = Tool.FEED
    image = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    scene.paint(painter, width, height, hour, weather)
    if controls:
        parent = QWidget()
        parent.resize(width, height)
        panel = FloatingOrb()
        panel.setParent(parent, Qt.Widget)
        panel.set_preferences(state.preferences)
        panel.set_context(len(state.fish), len(state.plants), state.water_quality, weather)
        panel.set_growth_context(*growth_summary(state))
        panel.move(width-panel.width()-24, height-panel.height()-24)
        panel.expand()
        if feed:
            panel.set_active_tool(Tool.FEED)
        if unread:
            panel.collapse()
            panel.set_chat_unread(3)
        panel.ensurePolished()
        parent.show()
        panel.show()
        QApplication.processEvents()
        panel.render(painter, QPoint(width-panel.width()-24, max(0, height-panel.height()-24)))
        if note:
            state.note.text = '今天的小庭\n\n□ 给幼鱼投喂\n□ 为荷花浇水\n\n把想记住的，留在这里。'
            state.note.x, state.note.y = .12, .25
            note_widget = NoteWidget(state.note, parent.rect, parent)
            note_widget.set_pinned(True)
            note_widget.show_note(focus=False)
            QApplication.processEvents()
            note_widget.render(painter, note_widget.pos())
            note_widget.close_for_shutdown()
        if chat:
            service = LanChat()  # Fixture only: do not open a network socket.
            chat_widget = ChatWidget(state.chat, parent.rect, service, parent)
            chat_widget.show_note(focus=False)
            chat_widget.set_members(3)
            chat_widget.status.setText('局域网已连接 · 在线庭友自动加入')
            chat_widget.receive_message('小春（示例）', '远处的河流经过水车，流进了小池塘。')
            chat_widget.receive_message('晴空（示例）', '一起在庭院里歇一会儿吧。')
            chat_widget.editor.setPlainText('今天的水草也在轻轻摇动。')
            QApplication.processEvents()
            chat_widget.render(painter, chat_widget.pos())
            chat_widget.close_for_shutdown()
        panel.close()
        parent.close()
    painter.end()
    target = out/name
    if not image.save(str(target)):
        raise OSError(f'Unable to write {target}')
    print(target)
    return target


def render_growth(out):
    image = QImage(1600, 700, QImage.Format_ARGB32_Premultiplied)
    image.fill(QColor('#F6F8EF'))
    p = QPainter(image)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    p.setPen(QColor('#476B57'))
    p.setFont(QFont('Noto Serif CJK SC', 25))
    p.drawText(QRectF(50, 25, 1500, 55), Qt.AlignLeft, '在小庭里，慢慢长大')
    p.setFont(QFont('Noto Sans CJK SC', 11))
    p.drawText(QRectF(52, 86, 1480, 32), Qt.AlignLeft, '阶段示意 · 养护越充分，成长越顺利。在线与离线使用相同的生长规则。')
    for index, hour in enumerate((0, 42, 126, 168)):
        fish = Fish(.5, .5, 'koi', growth_hours=hour, age_hours=hour, phase=0)
        center = QPointF(230+index*375, 230)
        paint_fish(p, fish, center, 1.5, 0)
        p.setPen(QColor('#476B57'))
        p.setFont(QFont('Noto Sans CJK SC', 13))
        p.drawText(QRectF(center.x()-130, 313, 260, 30), Qt.AlignCenter, fish_stage(fish))
        p.setFont(QFont('Noto Sans CJK SC', 10))
        p.drawText(QRectF(center.x()-130, 345, 260, 26), Qt.AlignCenter, f'有效成长 {hour} 小时')
    for index, hour in enumerate((2, 12, 25, 38, 51, 60)):
        plant = Plant(.5, .5, growth_hours=hour, age_hours=hour, phase=0, id=101)
        center = QPointF(142+index*263, 525)
        paint_plant(p, plant, center, 1.0, 0)
        p.setPen(QColor('#476B57'))
        p.setFont(QFont('Noto Sans CJK SC', 13))
        p.drawText(QRectF(center.x()-90, 605, 180, 30), Qt.AlignCenter, plant_phase(plant)[0])
    p.end()
    target = out/'10_growth_cycle.png'
    if not image.save(str(target)):
        raise OSError(f'Unable to write {target}')
    print(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent/'tests_out')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    for name, hour, weather, quality in (
        ('01_day_sunny.png', 13, 'sunny', 100),
        ('02_dusk_feed.png', 18.6, 'sunny', 92),
        ('03_night.png', 23, 'sunny', 88),
        ('04_rain.png', 14, 'rain', 78),
        ('05_snow_murky.png', 9, 'snow', 42),
    ):
        render_scene(args.output, name, hour, weather, quality, feed='feed' in name)
    render_scene(args.output, '06_overlay.png', 13, 'sunny', overlay=True)
    render_scene(args.output, '07_controls.png', 13, 'sunny', controls=True, feed=True)
    render_scene(args.output, '08_small_preview.png', 13, 'sunny', width=960, height=600, controls=True)
    render_scene(args.output, '09_notes.png', 13, 'sunny', controls=True, note=True)
    render_growth(args.output)
    render_scene(args.output, '11_lan_chat.png', 13, 'sunny', controls=True, chat=True)
    render_scene(args.output, '12_chat_unread.png', 13, 'sunny', controls=True, unread=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
