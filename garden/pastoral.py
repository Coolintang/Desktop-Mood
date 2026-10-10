"""Hand-painted pond scenery, anchored to the pond in a 1176 × 374 space."""
import math
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainterPath, QPen, QRadialGradient, QLinearGradient
from .wallpaper import _shape, _curve


def _begin(p, rect):
    p.save()
    p.translate(rect.topLeft())
    p.scale(rect.width()/1176, rect.height()/374)


def _color(value, night, weather):
    color = QColor(value)
    if night:
        color = color.darker(175)
    elif weather == 'rain':
        color = color.darker(115)
    elif weather == 'snow':
        color = color.lighter(112)
    return color


def paint_rocks(p, rect, night=False, weather='sunny'):
    """Static shoreline groups; called only when the shore cache is rebuilt."""
    _begin(p, rect)
    for x, y, scale in ((118, 91, 1.05), (158, 67, .65), (90, 120, .58),
                        (991, 81, .78), (1052, 108, 1.15), (1099, 135, .63),
                        (269, 349, 1.18), (320, 362, .68), (914, 344, .9)):
        p.save(); p.translate(x, y); p.scale(scale, scale)
        p.setPen(Qt.NoPen); p.setBrush(QColor(40, 69, 57, 48))
        p.drawEllipse(QRectF(-42, -5, 90, 21))
        outline = QPainterPath(QPointF(-43, 1))
        outline.cubicTo(-47, -12, -30, -38, -10, -40)
        outline.cubicTo(8, -44, 29, -35, 36, -23)
        outline.cubicTo(41, -16, 49, -2, 41, 4)
        outline.cubicTo(23, 15, -28, 14, -43, 1)
        stone = QLinearGradient(-20, -40, 15, 13)
        for at, color in ((0, '#CDD0BB'), (.45, '#AAB9A5'), (1, '#81998A')):
            stone.setColorAt(at, _color(color, night, weather))
        p.setBrush(stone); p.drawPath(outline)
        p.save(); p.setClipPath(outline)
        moss = QRadialGradient(QPointF(-12, -25), 33)
        moss.setColorAt(0, _color('#A3B783', night, weather))
        moss.setColorAt(.55, QColor(149, 170, 121, 115 if not night else 60))
        moss.setColorAt(1, QColor(149, 170, 121, 0))
        p.setBrush(moss); p.drawEllipse(QPointF(-12, -25), 39, 16)
        for i in range(13):
            p.setBrush(QColor(221, 227, 195, 55 if not night else 25))
            p.drawEllipse(QPointF(-29+(i*13)%59, -24+math.sin(i*2.4)*9), 1.2, .7)
        p.restore()
        if weather == 'snow':
            _curve(p, (-32, -28), [(-14, -43, 10, -42, 23, -33)], '#EBF1E4', 5)
        p.restore()
    p.restore()


def paint_watergrass(p, rect, t, night=False):
    """Submerged ribbons are clipped by the caller and painted below fish."""
    _begin(p, rect)
    for group, (x, y) in enumerate(((135, 196), (217, 269), (1010, 238), (854, 317), (402, 337))):
        p.setPen(Qt.NoPen); p.setBrush(QColor(29, 86, 69, 38))
        p.drawEllipse(QPointF(x, y), 29, 7)
        for i in range(11):
            root=x+math.sin(i*2.39+group)*22
            length=22+(i*17+group*11)%43
            sway=math.sin(t*.65+group*.8+i*.35)*7
            tip=root+math.sin(i*1.7+group)*19+sway
            blade=QPainterPath(QPointF(root,y))
            blade.cubicTo(root-4,y-length*.3,tip-11,y-length*.72,tip,y-length)
            blade.cubicTo(tip-5,y-length*.65,root+4,y-length*.2,root,y)
            leaf=QLinearGradient(root,y,tip,y-length)
            leaf.setColorAt(0,QColor(70,128,108,85 if night else 125))
            leaf.setColorAt(.65,QColor(108+i%3*7,162+i%3*5,127,100 if night else 155))
            leaf.setColorAt(1,QColor(164,193,149,60 if night else 105))
            p.setBrush(leaf)
            p.drawPath(blade)
    p.restore()


def paint_stream(p, rect, t, night=False, weather='sunny'):
    """A continuous channel passes the paddles and opens into the pond."""
    _begin(p, rect)
    # A narrow distant river winds through the fields, away from the house.
    # Its banks spread toward the viewer and reach the bottom of the wheel.
    stream=QPainterPath(QPointF(760,-66))
    stream.cubicTo(852,-91,1011,-84,944,-57)
    stream.cubicTo(889,-36,918,-60,982,-39)
    stream.cubicTo(1028,-24,1016,7,980,28)
    stream.cubicTo(936,52,858,55,810,65)
    banks=QPainterPath(QPointF(760,-68))
    banks.cubicTo(853,-94,1023,-88,949,-52)
    banks.cubicTo(909,-33,931,-65,986,-46)
    banks.cubicTo(1045,-25,1034,13,990,40)
    banks.cubicTo(951,65,860,68,810,81)
    banks.lineTo(810,49)
    banks.cubicTo(859,42,923,40,970,16)
    banks.cubicTo(1000,0,1012,-19,978,-32)
    banks.cubicTo(919,-55,866,-34,939,-62)
    banks.cubicTo(997,-82,852,-88,760,-64)
    banks.closeSubpath()
    p.setPen(QPen(_color('#ADBF93',night,weather),5,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin))
    water=QLinearGradient(0,-65,0,80)
    water.setColorAt(0,_color('#BFDAD0',night,weather))
    water.setColorAt(1,_color('#86B8AA',night,weather))
    p.setBrush(water);p.drawPath(banks)
    p.save();p.setClipPath(banks)
    # Foam follows the same curve as the channel, never jumps across banks.
    for i in range(19):
        u=(i/19+t*.16)%1
        point=stream.pointAtPercent(u)
        angle=math.radians(stream.angleAtPercent(u))
        dx,dy=math.cos(angle)*6,-math.sin(angle)*6
        p.setPen(QPen(QColor(228,248,228,95 if night else 185),1.6,Qt.SolidLine,Qt.RoundCap))
        p.drawLine(QPointF(point.x()-dx,point.y()-dy),point)
    p.setBrush(Qt.NoBrush)
    for i in range(4):
        phase=(t*.45+i*.25)%1
        p.setPen(QPen(QColor(228,250,232,int((1-phase)*(65 if night else 145))),1.4))
        p.drawEllipse(QPointF(810-phase*29,65+phase*12),8+phase*42,3+phase*12)
    p.restore()  # river clip
    p.restore()  # pond coordinates


def paint_waterwheel(p, rect, t, night=False, weather='sunny'):
    _begin(p,rect)
    p.translate(930,-12)
    wood=_color('#947650',night,weather)
    edge=_color('#5E5945',night,weather)
    light=_color('#D5B383',night,weather)
    # Fixed rear bearing and feet.
    _shape(p,[(-16,57),(-7,-6),(8,-6),(24,57)],edge)
    p.setPen(Qt.NoPen); p.setBrush(QColor(38,71,61,45));p.drawEllipse(QRectF(-70,47,146,22))
    p.save();p.scale(.85,1);p.rotate(t*13)
    for offset in (8,0):
        p.save();p.translate(offset,0)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(edge if offset else wood,9));p.drawEllipse(QPointF(0,0),55,55)
        p.setPen(QPen(light if not offset else wood,2));p.drawEllipse(QPointF(0,0),59,59)
        p.drawEllipse(QPointF(0,0),49,49)
        if not offset:
            for i in range(12):
                p.save();p.rotate(i*30)
                p.setPen(QPen(wood,5));p.drawLine(QPointF(0,0),QPointF(0,-51))
                p.setPen(QPen(light,1));p.drawLine(QPointF(2,-9),QPointF(2,-49))
                p.setPen(QPen(edge,1));p.setBrush(wood);p.drawRect(QRectF(-13,-61,26,9))
                p.setPen(QPen(light,1));p.drawLine(QPointF(-11,-60),QPointF(12,-60))
                p.restore()
        p.restore()
    p.setPen(QPen(edge,3));p.setBrush(light);p.drawEllipse(QPointF(0,0),10,10)
    p.restore()
    _shape(p,[(-20,62),(-5,-4),(4,-4),(18,62),(6,62),(-1,16),(-9,62)],wood)
    p.setPen(QPen(light,2));p.drawLine(QPointF(-4,8),QPointF(-14,56))
    p.setPen(Qt.NoPen);p.setBrush(edge);p.drawEllipse(QPointF(0,0),5,5)
    # Drops leave the lower paddles then fall back into the channel.
    for i in range(9):
        phase=(t*.8+i/9)%1
        p.setBrush(QColor(224,247,232,int((1-phase)*175)))
        p.drawEllipse(QPointF(30+i%3*7+phase*12,36+phase*26),1.3,2.3)
    p.restore()


def paint_reeds(p, rect, t, night=False, weather='sunny'):
    _begin(p,rect)
    for group,(x,y) in enumerate(((95,139),(1116,184),(947,339))):
        for i in range(7):
            sway=math.sin(t*.7+group+i*.28)*5
            tip=x+(i-3)*7+sway; height=29+(i*13)%31
            _curve(p,(x+(i-3)*3,y),[(x,y-height*.4,tip,y-height*.8,tip,y-height)],_color('#6E9368',night,weather),2)
            if i%2:
                _curve(p,(tip,y-height+8),[(tip+1,y-height+4,tip,y-height,tip,y-height-5)],_color('#927554',night,weather),4)
    p.restore()
