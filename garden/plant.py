from __future__ import annotations

import math
import random
from functools import lru_cache

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import (
    QColor, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient,
)

from .constants import PLANT_STAGE_HOURS


def stage(age):
    return sum(age >= h for h in PLANT_STAGE_HOURS)


@lru_cache(maxsize=256)
def _leaf_path(r, seed=1):
    """A round water-lily pad with a single open cleft and a soft, organic rim."""
    rnd = random.Random(seed)
    phase = rnd.random()*math.tau
    points = []
    count = 28
    for i in range(count+1):
        angle = .22+(math.tau-.44)*i/count
        radius = r*(1+.026*math.sin(3*angle+phase)
                    +.012*math.sin(5*angle-phase))
        points.append(QPointF(math.cos(angle)*radius,
                              math.sin(angle)*radius*.91))
    path = QPainterPath(QPointF(r*.08, 0))
    path.cubicTo(r*.20, r*.02, r*.70, r*.18,
                 points[0].x(), points[0].y())
    # Smooth cubic interpolation avoids the old repeated sharp line segments.
    for i in range(count):
        previous = points[max(0, i-1)]
        start, end = points[i], points[i+1]
        following = points[min(count, i+2)]
        c1 = start+(end-previous)/6
        c2 = end-(following-start)/6
        path.cubicTo(c1, c2, end)
    path.cubicTo(r*.70, -r*.18, r*.20, -r*.02, r*.08, 0)
    path.closeSubpath()
    return path


def paint_leaf(p: QPainter, center: QPointF, r: float, seed: int, alpha=255):
    p.save()
    p.translate(center)
    p.setOpacity(p.opacity()*max(0, min(255, alpha))/255)
    path = _leaf_path(r, seed)
    shadow = QRadialGradient(QPointF(r*.06, r*.14), r*1.1)
    shadow.setColorAt(0, QColor(22, 95, 85, 38))
    shadow.setColorAt(1, QColor(22, 95, 85, 0))
    p.setPen(Qt.NoPen)
    p.setBrush(shadow)
    p.drawEllipse(QPointF(r*.06, r*.14), r*1.1, r*.94)
    gradient = QRadialGradient(QPointF(-r*.30, -r*.34), r*1.5)
    for pos, color in ((0, '#B8D991'), (.30, '#85BD83'),
                       (.66, '#559F82'), (1, '#327F74')):
        gradient.setColorAt(pos, QColor(color))
    p.setBrush(gradient)
    p.setPen(QPen(QColor(44, 117, 91, 115), .85))
    p.drawPath(path)
    # Thin, curved veins belong to the leaf surface without overpowering it.
    p.setPen(QPen(QColor(221, 239, 179, 110), .65))
    for k in range(7):
        angle = .48+k*(math.tau-.96)/6
        end = QPointF(math.cos(angle)*r*.84, math.sin(angle)*r*.76)
        vein = QPainterPath(QPointF(r*.03, 0))
        vein.quadTo(end.x()*.54-r*.025, end.y()*.38, end.x(), end.y())
        p.drawPath(vein)
        for fraction in (.49, .70):
            x, y = end.x()*fraction, end.y()*fraction
            branch = QPainterPath(QPointF(x, y))
            side = angle+(.40 if k % 2 else -.40)
            branch.quadTo(x+math.cos(side)*r*.08, y+math.sin(side)*r*.06,
                          x+math.cos(side)*r*.16, y+math.sin(side)*r*.13)
            p.drawPath(branch)
    p.restore()


def paint_lotus(p: QPainter, center: QPointF, r: float):
    p.save()
    p.translate(center)
    shade = QRadialGradient(QPointF(0, r*.12), r*1.1)
    shade.setColorAt(0, QColor(60, 115, 103, 52))
    shade.setColorAt(1, QColor(60, 115, 103, 0))
    p.setBrush(shade)
    p.setPen(Qt.NoPen)
    p.drawEllipse(QPointF(0, r*.12), r*1.05, r*.86)
    # Petals share one soft central fold and open out symmetrically. Alternating
    # layers retain the readable blossom silhouette even at small desktop sizes.
    for layer, (count, length, width) in enumerate(((9, 1.0, .31),
                                                   (8, .76, .28),
                                                   (6, .52, .23))):
        for i in range(count):
            p.save()
            angle = math.tau*i/count+layer*.39
            p.rotate(math.degrees(angle))
            petal_length = r*length*(1+.04*math.sin(i*2.4+layer))
            petal_width = r*width
            petal = QPainterPath(QPointF(0, r*.08))
            petal.cubicTo(-petal_width, -petal_length*.20,
                          -petal_width*.82, -petal_length*.78,
                          0, -petal_length)
            petal.cubicTo(petal_width*.82, -petal_length*.78,
                          petal_width, -petal_length*.20, 0, r*.08)
            petal.closeSubpath()
            gradient = QLinearGradient(0, 0, 0, -petal_length)
            gradient.setColorAt(0, QColor('#F0B9CB'))
            gradient.setColorAt(.48, QColor('#FFF4EF'))
            gradient.setColorAt(.82, QColor('#F9C8D8'))
            gradient.setColorAt(1, QColor('#EC9CB9'))
            p.setBrush(gradient)
            p.setPen(QPen(QColor(209, 135, 164, 90), .55))
            p.drawPath(petal)
            fold = QPainterPath(QPointF(0, -r*.08))
            fold.quadTo(-r*.025, -petal_length*.48, 0, -petal_length*.83)
            p.setPen(QPen(QColor(255, 255, 250, 125), .55))
            p.drawPath(fold)
            p.restore()
    center_gradient = QRadialGradient(QPointF(-r*.045, -r*.045), r*.19)
    center_gradient.setColorAt(0, QColor('#FFF5B2'))
    center_gradient.setColorAt(1, QColor('#E7BD58'))
    p.setPen(Qt.NoPen)
    p.setBrush(center_gradient)
    p.drawEllipse(QPointF(0, 0), r*.16, r*.16)
    p.setBrush(QColor('#FFECA1'))
    for i in range(11):
        angle = i*math.tau/11
        p.drawEllipse(QPointF(math.cos(angle)*r*.205,
                             math.sin(angle)*r*.205), r*.032, r*.032)
    p.restore()


def paint_plant(p, plant, center, scale, t):
    st = stage(plant.age_hours)
    r = (20+st*8)*scale
    phase = plant.phase
    drift = QPointF(math.sin(t*.38+phase)*1.3*scale,
                    math.cos(t*.31+phase)*.8*scale)
    p.save()
    p.translate(center+drift)
    p.rotate(math.sin(t*.24+phase)*2.2)
    origin = QPointF(0, 0)
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor(225, 255, 244, 40), .8))
    p.drawEllipse(origin, r*1.14, r*.98)
    # Small pads sit behind the main leaf, preserving a calm, legible cluster.
    if st >= 1:
        paint_leaf(p, QPointF(-r*.79, r*.46), r*.49, plant.id+1)
    if st >= 2:
        paint_leaf(p, QPointF(r*.73, -r*.41), r*.40, plant.id+2)
    paint_leaf(p, origin, r, plant.id)
    if st >= 3:
        paint_lotus(p, QPointF(r*.03, -r*.10), r*.65)
    p.restore()
