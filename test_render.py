"""Render isolated garden fixtures; never read or change the user's saved pond."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import random

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication, QWidget

from garden.constants import Tool
from garden.models import AppState, Fish, Plant
from garden.scene import PondScene
from garden.toolbar import FloatingOrb


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
                 width=1600, height=900, overlay=False, controls=False, feed=False):
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
        panel.move(width-panel.width()-24, height-panel.height()-24)
        panel.expand()
        if feed:
            panel.set_active_tool(Tool.FEED)
        panel.ensurePolished()
        parent.show()
        panel.show()
        QApplication.processEvents()
        panel.render(painter, QPoint(width-panel.width()-24, max(0, height-panel.height()-24)))
        panel.close()
        parent.close()
    painter.end()
    target = out/name
    if not image.save(str(target)):
        raise OSError(f'Unable to write {target}')
    print(target)
    return target


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
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
