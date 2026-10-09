"""Resolution-independent, locally drawn spring garden artwork.

The expensive garden illustration is cached. Only petals, light and the clock
are drawn on each frame, so a wallpaper doesn't need to redraw every blossom.
"""
from __future__ import annotations

from datetime import datetime
import math
import random
from zoneinfo import ZoneInfo

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient

from .constants import TIMEZONE


def _shape(p, points, color):
    path = QPainterPath(QPointF(*points[0]))
    for point in points[1:]:
        path.lineTo(*point)
    path.closeSubpath()
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawPath(path)


def _curve(p, start, segments, color, width):
    path = QPainterPath(QPointF(*start))
    for segment in segments:
        path.cubicTo(*segment)
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor(color), width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawPath(path)


def _bloom(p, x, y, size, color, angle=0):
    p.save()
    p.translate(x, y)
    p.rotate(angle)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    for i in range(5):
        p.rotate(72)
        petal = QPainterPath(QPointF(0, 0))
        petal.cubicTo(-size*.8, -size*.5, -size*.65, -size*1.1, -size*.16, -size)
        petal.lineTo(0, -size*.79)
        petal.lineTo(size*.16, -size)
        petal.cubicTo(size*.65, -size*1.1, size*.8, -size*.5, 0, 0)
        p.drawPath(petal)
    p.setBrush(QColor('#DFA2AA'))
    p.drawEllipse(QPointF(0, 0), size*.13, size*.13)
    p.restore()


class GardenWallpaper:
    def __init__(self):
        self._cache_key = None
        self._cache = None

    def paint_background(self, p: QPainter, w: int, h: int, daylight: dict, weather: str):
        dpr = p.device().devicePixelRatioF()
        key = (w, h, dpr, daylight['name'], weather)
        if key != self._cache_key:
            self._cache = QImage(round(w*dpr), round(h*dpr), QImage.Format_ARGB32_Premultiplied)
            self._cache.setDevicePixelRatio(dpr)
            self._cache.fill(Qt.transparent)
            q = QPainter(self._cache)
            q.setRenderHint(QPainter.Antialiasing)
            q.scale(w / 1600, h / 900)
            self._illustration(q, daylight, weather)
            q.end()
            self._cache_key = key
        p.drawImage(0, 0, self._cache)

    def _illustration(self, p, dl, weather):
        night = dl['name'] == 'night'
        dusk = dl['name'] in ('dusk', 'golden', 'sunrise', 'dawn')
        sky = QLinearGradient(0, 0, 0, 540)
        colors = ('#283E68', '#7387A6', '#BAC5CB') if night else (
            ('#A9BED3', '#F6D4C0', '#FFF0D9') if dusk else ('#A9D8E6', '#D9EFEC', '#F9F5DC'))
        for at, color in zip((0, .66, 1), colors):
            sky.setColorAt(at, QColor(color))
        p.fillRect(QRectF(0, 0, 1600, 900), sky)

        # Sunlight is a soft wash, leaving quiet sky for desktop icons and a clock.
        glow = QRadialGradient(QPointF(1050, 135), 330)
        glow.setColorAt(0, QColor(255, 248, 215, 115 if not night else 25))
        glow.setColorAt(1, QColor(255, 251, 231, 0))
        p.fillRect(QRectF(0, 0, 1600, 540), glow)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor('#FFF8DF' if not night else '#FFF7DB'))
        p.drawEllipse(QPointF(1050, 135), 28 if not night else 24, 28 if not night else 24)
        rng = random.Random(21)
        if night:
            for _ in range(65):
                x, y = rng.uniform(140, 1520), rng.uniform(25, 320)
                p.setBrush(QColor(255, 251, 225, rng.randint(80, 220)))
                r = rng.uniform(.7, 1.7)
                p.drawEllipse(QPointF(x, y), r, r)

        for x, y, scale in ((340, 88, .8), (720, 196, 1.05), (1280, 75, 1.0), (115, 287, .75)):
            self._cloud(p, x, y, scale, night)

        # Layered distant hills, with curved silhouettes rather than polygons.
        hills = [
            ((0, 338), [(120, 319, 203, 294, 318, 327), (435, 349, 459, 269, 608, 281),
                         (727, 292, 802, 354, 954, 319), (1113, 282, 1200, 277, 1328, 318), (1440, 335, 1530, 286, 1600, 297)], '#9FC9C1'),
            ((0, 390), [(155, 356, 240, 347, 359, 387), (494, 420, 547, 347, 707, 364),
                         (839, 387, 875, 409, 1030, 370), (1217, 324, 1406, 350, 1600, 393)], '#80B6AA'),
            ((0, 426), [(218, 389, 342, 418, 492, 421), (707, 439, 896, 392, 1127, 410), (1323, 431, 1418, 392, 1600, 427)], '#6AA293'),
        ]
        for start, segments, color in hills:
            path = QPainterPath(QPointF(*start))
            for segment in segments:
                path.cubicTo(*segment)
            path.lineTo(1600, 900)
            path.lineTo(0, 900)
            path.closeSubpath()
            p.fillPath(path, QColor(color))
        mist = QLinearGradient(0, 335, 0, 463)
        mist.setColorAt(0, QColor(243, 245, 218, 0))
        mist.setColorAt(.52, QColor(243, 245, 218, 100))
        mist.setColorAt(1, QColor(243, 245, 218, 0))
        p.fillRect(QRectF(0, 330, 1600, 150), mist)

        field = QPainterPath(QPointF(0, 466))
        field.cubicTo(260, 409, 513, 459, 768, 434)
        field.cubicTo(1071, 409, 1325, 433, 1600, 465)
        field.lineTo(1600, 900)
        field.lineTo(0, 900)
        field.closeSubpath()
        grass = QLinearGradient(0, 425, 0, 900)
        grass.setColorAt(0, QColor('#B8CEA0'))
        grass.setColorAt(.35, QColor('#D1DDB2'))
        grass.setColorAt(1, QColor('#94B78E'))
        p.fillPath(field, grass)

        # Meandering sand path and stepping stones towards the water.
        path = QPainterPath(QPointF(-30, 792))
        path.cubicTo(142, 789, 143, 504, 462, 461)
        path.cubicTo(540, 443, 606, 446, 663, 440)
        p.setPen(QPen(QColor('#E5DFC0'), 42, Qt.SolidLine, Qt.RoundCap))
        p.drawPath(path)
        p.setPen(QPen(QColor('#F1E8CD'), 31, Qt.SolidLine, Qt.RoundCap))
        p.drawPath(path)

        # A small tea house set back behind the shore.
        self._tea_house(p, 1248, 345)
        for i in range(20):
            x = i*84 + rng.uniform(-15, 15)
            y = 431 + math.sin(i*.62)*13
            for j in range(3):
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(('#78A685', '#8DB591', '#ABC399')[j]))
                p.drawEllipse(QPointF(x+j*15, y-j*5), 20+j*2, 12+j)

        # Very fine meadow marks and flowers. Seeded and cached, never flickering.
        for _ in range(750):
            x, y = rng.uniform(0, 1600), rng.uniform(459, 900)
            p.setPen(QPen(QColor(rng.choice(('#8FAD81', '#B4C999', '#DBE1AE', '#729C7D'))), .8))
            length = 2+(y-420)/100
            p.drawLine(QPointF(x, y), QPointF(x+rng.uniform(-3, 3), y-length))
            if rng.random() < .14:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(rng.choice(('#FAF1CE', '#F5DBDF', '#F8F6E0'))))
                p.drawEllipse(QPointF(x, y-length), 1.7, 1.2)
        for i, (x, y, size) in enumerate(((98, 819, 28), (139, 766, 24), (163, 717, 23), (192, 674, 20), (216, 633, 18), (252, 595, 15))):
            p.setPen(QPen(QColor('#A7AA8F'), 1))
            p.setBrush(QColor('#D6D8BD'))
            p.drawEllipse(QPointF(x, y+3), size, size*.4)
            p.setBrush(QColor('#EEEDD6'))
            p.drawEllipse(QPointF(x, y), size*.96, size*.36)
            _curve(p, (x-size*.55, y-2), [(x-5, y-8, x+7, y-6, x+size*.6, y-4)], '#FFF6DC', 1)

        # A little garden lantern, anchored on the far bank.
        self._lantern(p, 367, 422, .68, night)
        self._cherry_tree(p, rng, mirrored=False)
        self._cherry_tree(p, random.Random(31), mirrored=True)

        # Near grasses frame the picture without occupying the middle of the pond.
        for side in (0, 1):
            for i in range(100):
                x = rng.uniform(0, 265) if side == 0 else rng.uniform(1410, 1600)
                y = rng.uniform(825, 933)
                length = rng.uniform(12, 65)
                _curve(p, (x, y), [(x-5, y-length*.4, x-13, y-length*.9, x-22, y-length)], rng.choice(('#719677', '#87A580', '#A6BE91')), rng.uniform(1, 3))

        # Paint one coherent color grade on all static illustration layers.
        if night:
            p.fillRect(QRectF(0, 0, 1600, 900), QColor(19, 40, 79, 112))
        elif dusk:
            p.fillRect(QRectF(0, 0, 1600, 900), QColor(208, 129, 128, 32))
        if night:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor('#F6EBD0'))
            p.drawEllipse(QPointF(1050, 135), 24, 24)
            lamp_glow = QRadialGradient(QPointF(367, 385), 44)
            lamp_glow.setColorAt(0, QColor(255, 227, 161, 90))
            lamp_glow.setColorAt(1, QColor(255, 227, 161, 0))
            p.setBrush(lamp_glow)
            p.drawEllipse(QPointF(367, 385), 44, 44)
        if weather in ('cloudy', 'rain', 'snow'):
            tint = {'cloudy': QColor(130, 154, 164, 30), 'rain': QColor(86, 122, 145, 58), 'snow': QColor(233, 243, 239, 83)}[weather]
            p.fillRect(QRectF(0, 0, 1600, 900), tint)

    def _cloud(self, p, x, y, scale, night):
        p.save()
        p.translate(x, y)
        p.scale(scale, scale)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(224, 239, 239, 30 if night else 135))
        p.drawEllipse(QRectF(-127, -5, 294, 31))
        for xx, yy, rx, ry in ((-80, 0, 53, 17), (-39, -17, 45, 32), (6, -37, 49, 45), (54, -22, 44, 30), (100, -1, 62, 19)):
            g = QLinearGradient(0, yy-ry, 0, yy+ry)
            g.setColorAt(0, QColor(255, 254, 242, 38 if night else 233))
            g.setColorAt(1, QColor(235, 244, 235, 22 if night else 168))
            p.setBrush(g)
            p.drawEllipse(QPointF(xx, yy), rx, ry)
        p.restore()

    def _tea_house(self, p, x, y):
        p.save()
        p.translate(x, y)
        _shape(p, [(-2, 48), (161, 48), (161, 123), (-2, 123)], '#E5DBBC')
        _shape(p, [(79, 52), (158, 47), (158, 124), (79, 124)], '#B1AE91')
        p.setPen(QPen(QColor('#826F60'), 4))
        for xx in (3, 41, 78, 118, 155):
            p.drawLine(xx, 56, xx, 125)
        for xx in (14, 88):
            p.fillRect(QRectF(xx, 70, 50, 45), QColor('#DEDCC3'))
            p.setPen(QPen(QColor('#A59E85'), 1.4))
            for j in range(1, 4):
                p.drawLine(xx+j*12, 70, xx+j*12, 114)
            p.drawLine(xx, 93, xx+50, 93)
        roof = QPainterPath(QPointF(-28, 63))
        roof.cubicTo(-6, 62, 37, 18, 67, 0)
        roof.cubicTo(102, 16, 140, 58, 186, 59)
        roof.lineTo(188, 67)
        roof.cubicTo(129, 74, 79, 57, -28, 70)
        roof.closeSubpath()
        p.fillPath(roof, QColor('#657E78'))
        _curve(p, (-28, 63), [(21, 60, 34, 16, 67, 0), (104, 15, 137, 59, 186, 59)], '#8D9A86', 3)
        _curve(p, (-26, 69), [(47, 63, 133, 72, 188, 66)], '#455F59', 4)
        p.fillRect(QRectF(-14, 124, 182, 7), QColor('#9F8A6C'))
        p.fillRect(QRectF(-22, 131, 196, 6), QColor('#C6B996'))
        p.restore()

    def _lantern(self, p, x, y, scale, night):
        p.save()
        p.translate(x, y)
        p.scale(scale, scale)
        _shape(p, [(-18, 4), (18, 4), (26, 13), (-26, 13)], '#89978B')
        p.fillRect(QRectF(-8, -48, 16, 53), QColor('#A3AC98'))
        p.fillRect(QRectF(-19, -66, 38, 25), QColor('#B7BEA6'))
        p.fillRect(QRectF(-10, -62, 20, 16), QColor('#FFE9AD' if night else '#7C8C7B'))
        _shape(p, [(-31, -67), (0, -89), (31, -67)], '#89988C')
        p.setPen(Qt.NoPen)
        p.setBrush(QColor('#B9C1AA'))
        p.drawEllipse(QPointF(0, -90), 6, 7)
        p.restore()

    def _cherry_tree(self, p, rng, mirrored=False):
        p.save()
        if mirrored:
            p.translate(1600, 0)
            p.scale(-.74, .74)
            p.translate(-100, -63)
        # Trunk and twisting branch silhouettes reach in from the edges.
        trunk = QPainterPath(QPointF(-55, 756))
        trunk.cubicTo(95, 671, 90, 417, 135, 290)
        trunk.cubicTo(152, 225, 213, 192, 253, 167)
        trunk.lineTo(244, 153)
        trunk.cubicTo(159, 197, 124, 235, 101, 299)
        trunk.cubicTo(87, 218, 39, 158, -30, 95)
        trunk.lineTo(-57, 113)
        trunk.cubicTo(30, 219, 41, 387, 30, 492)
        trunk.cubicTo(22, 574, 12, 659, -62, 698)
        trunk.closeSubpath()
        g = QLinearGradient(0, 380, 116, 410)
        g.setColorAt(0, QColor('#73675F'))
        g.setColorAt(.62, QColor('#8F7C6C'))
        g.setColorAt(1, QColor('#A09078'))
        p.fillPath(trunk, g)
        for start, segments, width in [
            ((108, 325), [(168, 258, 286, 275, 375, 192), (418, 158, 460, 164, 505, 137)], 13),
            ((154, 250), [(183, 180, 301, 141, 338, 57)], 11),
            ((70, 255), [(31, 151, 114, 116, 159, 47)], 15),
            ((290, 250), [(292, 192, 320, 172, 362, 146)], 6),
            ((73, 434), [(4, 330, -28, 272, -46, 216)], 11),
        ]:
            _curve(p, start, segments, '#847065', width)
        _curve(p, (11, 673), [(68, 559, 57, 415, 111, 284)], '#B09B7E', 3)
        # Uneven clusters have colored shade, tiny individual flowers and open sky.
        clusters = [(-40, 77, 140, 90), (105, 80, 131, 74), (245, 72, 104, 63),
                    (381, 53, 133, 70), (444, 143, 89, 45), (320, 179, 118, 57),
                    (140, 200, 103, 58), (-31, 273, 105, 95), (47, 167, 85, 72)]
        for cx, cy, rx, ry in clusters:
            for _ in range(48):
                a, radius = rng.uniform(0, math.tau), math.sqrt(rng.random())
                x, y = cx+math.cos(a)*rx*radius, cy+math.sin(a)*ry*radius
                s = rng.uniform(11, 28)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(rng.choice(('#E5ABB9', '#EEC0C8', '#F3CAD0', '#F5D6D7'))))
                p.drawEllipse(QPointF(x, y), s, s*.72)
            for _ in range(52):
                a, radius = rng.uniform(0, math.tau), math.sqrt(rng.random())
                x, y = cx+math.cos(a)*rx*radius, cy+math.sin(a)*ry*radius-7
                _bloom(p, x, y, rng.uniform(3, 7.5), rng.choice(('#FCEAE5', '#FFF0E9', '#F9E0DE', '#F4CCD1')), rng.uniform(0, 360))
        p.restore()

    def paint_petals(self, p, w, h, t, night=False):
        p.save()
        p.scale(w/1600, h/900)
        for i in range(28):
            x = (i*127.31 + t*(10+i%4*2.8)) % 1780 - 90
            y = (i*87.43 + t*(10+i%3*2.1) + math.sin(t*.55+i)*23) % 1050 - 90
            p.save()
            p.translate(x, y)
            p.rotate(math.sin(t*.8+i)*48+i*41)
            p.scale(.55+abs(math.sin(t*.6+i))*.45, 1)
            size = 3.3+i%4
            path = QPainterPath(QPointF(0, -size))
            path.cubicTo(size*1.3, -size*.5, size*.8, size*.6, 0, size)
            path.cubicTo(-size, size*.2, -size*.7, -size*.7, 0, -size)
            p.setPen(QPen(QColor(255, 239, 235, 170), .6))
            p.setBrush(QColor(244, 184, 202, 155 if night else 215))
            p.drawPath(path)
            p.restore()
        p.restore()

    def paint_fireflies(self, p, w, h, t):
        p.save()
        p.scale(w/1600, h/900)
        p.setPen(Qt.NoPen)
        for i in range(16):
            x = 145+i*83+math.sin(t*.31+i*1.7)*24
            y = 455+(i*71)%395+math.cos(t*.46+i)*14
            alpha = int(75+65*math.sin(t*1.3+i*2.1))
            glow = QRadialGradient(QPointF(x, y), 13)
            glow.setColorAt(0, QColor(245, 249, 178, alpha))
            glow.setColorAt(.25, QColor(220, 244, 173, alpha//3))
            glow.setColorAt(1, QColor(220, 244, 173, 0))
            p.setBrush(glow)
            p.drawEllipse(QPointF(x, y), 13, 13)
        p.restore()

    def paint_clock(self, p, w, h, dl, override_hour=None):
        now = datetime.now(ZoneInfo(TIMEZONE))
        hour = now.hour if override_hour is None else int(override_hour)
        minute = now.minute if override_hour is None else int((override_hour % 1)*60)
        scale = min(w/1600, h/900)
        p.save()
        p.translate(w*.36, h*.125)
        p.scale(scale, scale)
        night = dl['name'] == 'night'
        ink = QColor('#EEF2E7' if night else '#547C7B')
        p.setPen(ink)
        f = QFont('Noto Sans CJK SC', 10)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 4)
        p.setFont(f)
        p.drawText(QRectF(-100, 0, 340, 25), Qt.AlignCenter, '春 庭  /  H A R U N I W A')
        f = QFont('Noto Sans', 57, QFont.Light)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 1)
        p.setFont(f)
        p.drawText(QRectF(-100, 26, 340, 90), Qt.AlignCenter, f'{hour:02d}:{minute:02d}')
        f = QFont('Noto Sans CJK SC', 10)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 2)
        p.setFont(f)
        weekday = '一二三四五六日'[now.weekday()]
        p.drawText(QRectF(-100, 114, 340, 28), Qt.AlignCenter, f'{now.month:02d} 月 {now.day:02d} 日   /   星期{weekday}')
        ink.setAlpha(170)
        p.setPen(ink)
        f.setPointSize(9)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 3)
        p.setFont(f)
        p.drawText(QRectF(-100, 160, 340, 28), Qt.AlignCenter, '风过春庭，且听水音。')
        p.restore()
