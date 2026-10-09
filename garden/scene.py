from __future__ import annotations
import math, random
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor, QPainter, QPainterPath, QPen, QRadialGradient, QLinearGradient, QFont, QImage
)
from .models import *
from .constants import *
from .fish import paint_fish, update_fish
from .plant import paint_plant
from .daylight import daylight
from .weather import update_weather, LIGHT
from .wallpaper import GardenWallpaper


class PondScene:
    def __init__(self, state: AppState):
        self.state = state
        # Older versions allowed square coordinates even though water is oval.
        # Keep existing plants reachable rather than silently clipping them away.
        for plant in self.state.plants:
            dx, dy = plant.x-.5, plant.y-.5
            distance = math.hypot(dx, dy)
            if distance > .40:
                plant.x, plant.y = .5+dx*.40/distance, .5+dy*.40/distance
        self.food = []
        self.drops = []
        self.ripples = []
        self.t = 0.0
        self.tool = Tool.NONE
        self.wallpaper = GardenWallpaper()
        self._shore_cache = None
        self._shore_cache_key = None
        self.hover = None
        self._viewport = (1600, 900)
        self._daylight = daylight(13)

    @property
    def preferences(self):
        return getattr(self.state, 'preferences', {})

    @property
    def illustrated(self):
        return self.preferences.get('wallpaper_mode', 'scene') == 'scene'

    def environment(self, override_hour=None, override_weather=None):
        mode = self.preferences.get('time_mode', 'live')
        hour = override_hour if override_hour is not None else {
            'day': 13, 'dusk': 18.6, 'night': 23,
        }.get(mode)
        weather_mode = self.preferences.get('weather_mode', 'auto')
        weather = override_weather or (self.state.weather if weather_mode == 'auto' else weather_mode)
        return daylight(hour), weather if weather in LIGHT else 'sunny'


    def pond_rect(self, w, h):
        if self.illustrated:
            return QRectF(w*.125, h*.485, w*.735, h*.415)
        pw = min(w * .76, 1120)
        ph = min(h * .78, 720)
        return QRectF((w - pw) / 2, (h - ph) / 2, pw, ph)

    def entity_scale(self, rect):
        return max(.2, min(1.35, rect.width()/900, rect.height()/360))

    def contains(self, x, y, w, h):
        r = self.pond_rect(w, h)
        nx = (x - r.center().x()) / (r.width() / 2)
        ny = (y - r.center().y()) / (r.height() / 2)
        return nx * nx + ny * ny < 1.0

    def norm(self, x, y, w, h):
        r = self.pond_rect(w, h)
        return ((x - r.left()) / r.width(), (y - r.top()) / r.height())

    def point(self, x, y, w, h):
        r = self.pond_rect(w, h)
        return QPointF(r.left() + x * r.width(), r.top() + y * r.height())

    def update(self, dt):
        dt = max(0.0, min(float(dt), .25))
        self.t += dt
        hours = dt / 3600
        self.state.water_quality = max(0, self.state.water_quality - WATER_DECAY_PER_HOUR*hours)
        for fish in self.state.fish:
            fish.hunger = min(100, fish.hunger + FISH_HUNGER_PER_HOUR*hours)
        for plant in self.state.plants:
            plant.age_hours += hours
            plant.moisture = max(0, plant.moisture - 1.4*hours)
        update_weather(self.state)
        rect = self.pond_rect(*self._viewport)
        update_fish(self.state.fish, self.food, dt,
                    pond_size=(rect.width(), rect.height()), render_scale=self.entity_scale(rect)*.85)
        for x in self.food:
            x.life -= dt
        self.food = [x for x in self.food if x.life > 0 and not x.eaten]
        for x in self.ripples:
            x.age += dt
        self.ripples = [x for x in self.ripples if x.age < x.max_age]
        for d in self.drops:
            d.x += d.vx * dt
            d.y += d.vy * dt
            d.vy += 70 * dt
            d.life -= dt
        self.drops = [d for d in self.drops if d.life > 0]

    def apply_tool(self, tool, x, y, w, h):
        if tool == Tool.NONE or not self.contains(x, y, w, h):
            return None
        nx, ny = self.norm(x, y, w, h)
        if tool == Tool.FEED:
            if len(self.food) >= 75:
                return '水面还有许多鱼食，让鱼儿慢慢享用吧'
            for _ in range(min(5, 75-len(self.food))):
                fx = nx + random.uniform(-.02, .02)
                fy = ny + random.uniform(-.02, .02)
                d = math.hypot(fx-.5, fy-.5)
                if d > .46:
                    fx, fy = .5+(fx-.5)*.46/d, .5+(fy-.5)*.46/d
                self.food.append(FoodPellet(fx, fy))
            self.ripples.append(Ripple(nx, ny))
            self.state.water_quality = max(0, self.state.water_quality-FEED_POLLUTION)
            return '撒下一点鱼食，等鱼儿游过来'
        if tool == Tool.WATER_PLANT:
            watered = 0
            for plant in self.state.plants:
                q = self.point(plant.x, plant.y, w, h)
                if math.hypot(q.x()-x, q.y()-y) < max(65, self.pond_rect(w, h).width()*.085):
                    plant.moisture = min(100, plant.moisture+35)
                    watered += 1
            if not watered:
                return '靠近荷叶再轻点一下，就可以浇水了'
            for _ in range(12):
                if len(self.drops) < 120:
                    self.drops.append(WaterDrop(x+random.uniform(-25, 25), y-45,
                                               random.uniform(-18, 18), random.uniform(20, 60)))
            self.ripples.append(Ripple(nx, ny, max_radius=55))
            return '荷叶喝饱了水，静待花开'
        if tool == Tool.CHANGE_WATER:
            self.state.water_quality = 100
            self.food.clear()
            self.ripples.append(Ripple(nx, ny, max_age=2.5, max_radius=250))
            return '换上清水，池塘又清澈了'
        if tool in (Tool.ADD_FISH, Tool.ADD_PLANT):
            if len(self.state.fish)+len(self.state.plants) >= MAX_ENTITIES:
                return '池塘已经很热闹了，先移走一些鱼或荷花吧'
            # Keep new residents fully inside the visible bank.
            d = math.hypot(nx-.5, ny-.5)
            if d > .40:
                nx, ny = .5+(nx-.5)*.40/d, .5+(ny-.5)*.40/d
            if tool == Tool.ADD_FISH:
                self.state.fish.append(Fish(nx, ny, random.choice(FISH_KINDS),
                                           angle=random.random()*math.tau, size=random.uniform(.72, 1.08)))
                message = '一尾新鱼，游进了春庭'
            else:
                self.state.plants.append(Plant(nx, ny, age_hours=6))
                message = '种下一片新绿，让它慢慢长大'
            self.ripples.append(Ripple(nx, ny, max_radius=65))
            return message
        if tool == Tool.ERASE:
            nearest, distance = None, max(35, self.pond_rect(w, h).width()*.052)
            for obj in [*self.state.fish, *self.state.plants]:
                q = self.point(obj.x, obj.y, w, h)
                d = math.hypot(q.x()-x, q.y()-y)
                if d < distance:
                    nearest, distance = obj, d
            if nearest is None:
                return '轻点要移走的鱼或荷花'
            if nearest in self.state.fish:
                self.state.fish.remove(nearest)
            else:
                self.state.plants.remove(nearest)
            return '留一点空白，让庭院自在呼吸'
        return None

    def _pond_path(self, r):
        cx, cy = r.center().x(), r.center().y()
        rx, ry = r.width() / 2, r.height() / 2
        p = QPainterPath()
        pts = []
        for i in range(96):
            a = i * 2 * math.pi / 96
            rr = (1 + .018 * math.sin(5 * a)
                    + .012 * math.sin(11 * a + 1.1)
                    + .008 * math.sin(19 * a + .4))
            pts.append(QPointF(
                cx + math.cos(a) * rx * rr,
                cy + math.sin(a) * ry * rr
            ))
        p.moveTo(pts[0])
        for q in pts[1:]:
            p.lineTo(q)
        p.closeSubpath()
        return p

    def _paint_glass_water_base(self, p: QPainter, path, r, light: float):
        night = self._daylight['name'] == 'night'
        dusk = self._daylight['name'] in ('dusk', 'golden', 'dawn', 'sunrise')
        colors = ('#397886', '#579C9D', '#9CC3AE') if night else (
            ('#76A9A7', '#A9C9B7', '#DFDFC0') if dusk else ('#56AFAE', '#81C7BC', '#C0DFC4'))
        g = QRadialGradient(QPointF(r.center().x(), r.center().y()+r.height()*.1), r.width()*.62)
        for pos, color in zip((0, .60, 1), colors):
            c = QColor(color)
            c.setAlpha(255 if self.illustrated else 180)
            g.setColorAt(pos, c)
        p.fillPath(path, g)
        sheen = QLinearGradient(r.topLeft(), r.bottomRight())
        sheen.setColorAt(0, QColor(251, 254, 232, 50))
        sheen.setColorAt(.35, QColor(222, 248, 231, 8))
        sheen.setColorAt(.76, QColor(252, 248, 222, 27))
        sheen.setColorAt(1, QColor(230, 249, 223, 5))
        p.fillPath(path, sheen)

    def _paint_depth(self, p: QPainter, r):
        # Slowly breathing depth patches. Their centers move by a few pixels so
        # the water never looks like a static background image.
        p.setPen(Qt.NoPen)
        for i in range(14):
            a = i * 2.399
            drift_x = math.sin(self.t * .09 + i * 1.7) * 18
            drift_y = math.cos(self.t * .075 + i * 1.1) * 13
            x = r.center().x() + math.cos(a) * r.width() * .33 + drift_x
            y = r.center().y() + math.sin(a * 1.27) * r.height() * .28 + drift_y
            radius = 92 + 25 * (i % 3) + 7 * math.sin(self.t * .16 + i)
            rg = QRadialGradient(QPointF(x, y), radius)
            rg.setColorAt(0, QColor(4, 67, 91, 22))
            rg.setColorAt(.62, QColor(7, 86, 105, 10))
            rg.setColorAt(1, QColor(6, 79, 101, 0))
            p.setBrush(rg)
            p.drawEllipse(QPointF(x, y), radius * 1.45, radius * .82)

    def _paint_dynamic_water(self, p: QPainter, r, ambient: float, light: float):
        """Continuous organic motion: drifting caustics + wave bands + micro ripples.

        There are deliberately no perpendicular line families, so the animation
        can never resolve into the grid appearance rejected by the art spec.
        """
        p.setBrush(Qt.NoBrush)

        # 1) Irregular caustic arcs drifting at different rates.
        for i in range(34):
            u = (i * .173 + self.t * (.006 + (i % 4) * .0012)) % 1.0
            v = (i * .319 + math.sin(self.t * .20 + i * .77) * .025) % 1.0
            x = r.left() + u * r.width()
            y = r.top() + v * r.height()
            rad = 24 + (i % 6) * 10 + 4 * math.sin(self.t * .45 + i)
            pulse = .55 + .45 * math.sin(self.t * .72 + i * 1.31)
            alpha = int((15 + 22 * pulse) * ambient * light)
            p.setPen(QPen(QColor(225, 255, 249, max(4, alpha)), 1.0 + (i % 3) * .45))
            start = int(((i * 37 + self.t * 8) % 180) * 16)
            span = int((48 + (i % 5) * 17) * 16)
            p.drawArc(QRectF(x - rad, y - rad * .36, rad * 2, rad * .72), start, span)

        # 2) Same-direction curved flow highlights. These visibly translate over
        # time and give the lake a living surface without forming a mesh/grid.
        for i in range(9):
            base_y = r.top() + (i + .55) / 9.8 * r.height()
            travel = ((self.t * (12 + i % 3 * 3) + i * 91) % (r.width() + 300)) - 150
            x0 = r.left() + travel
            width = 170 + (i % 4) * 34
            amp = 8 + (i % 3) * 5
            q = QPainterPath(QPointF(x0, base_y))
            q.cubicTo(
                QPointF(x0 + width * .28, base_y + amp * math.sin(self.t * .34 + i)),
                QPointF(x0 + width * .68, base_y - amp * .8),
                QPointF(x0 + width, base_y + amp * .25)
            )
            alpha = int((13 + 7 * math.sin(self.t * .55 + i)) * ambient * light)
            p.setPen(QPen(QColor(235, 255, 252, max(4, alpha)), 2.0 + (i % 2) * .7, Qt.SolidLine, Qt.RoundCap))
            p.drawPath(q)

        # 3) Tiny ambient ring ripples: slow and sparse, like surface tension.
        for i in range(12):
            cycle = (self.t * (.18 + .012 * (i % 4)) + i * .137) % 1.0
            x = r.left() + ((i * .271 + .17) % 1.0) * r.width()
            y = r.top() + ((i * .413 + .11) % 1.0) * r.height()
            rr = 8 + cycle * (28 + i % 3 * 8)
            alpha = int((1.0 - cycle) ** 1.8 * 24 * ambient * light)
            p.setPen(QPen(QColor(225, 255, 250, alpha), .9))
            p.drawEllipse(QPointF(x, y), rr, rr * .28)

    def _paint_glass_finish(self, p: QPainter, path, r):
        # Broad specular blooms make the whole pond read as translucent glass.
        for i, (ux, uy, rx, ry, a) in enumerate((
            (.23, .18, .23, .12, 24),
            (.72, .30, .18, .09, 16),
            (.58, .78, .27, .10, 13),
        )):
            c = QPointF(r.left() + ux * r.width(), r.top() + uy * r.height())
            rg = QRadialGradient(c, r.width() * rx)
            rg.setColorAt(0, QColor(255, 255, 255, a))
            rg.setColorAt(.55, QColor(240, 255, 255, a // 3))
            rg.setColorAt(1, QColor(255, 255, 255, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(rg)
            p.drawEllipse(c, r.width() * rx, r.height() * ry)

        # Double glass rim: soft dark depth outside + fine white reflection inside.
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(4, 35, 43, 38), 12))
        p.drawPath(path)
        p.setPen(QPen(QColor(225, 255, 252, 52), 2.2))
        p.drawPath(path)
        p.setPen(QPen(QColor(255, 255, 255, 44), .8))
        p.drawPath(path)


    def _paint_cached_shore(self, p, path, rect, w, h):
        dpr = p.device().devicePixelRatioF()
        key = (w, h, dpr, self.illustrated, self._daylight['name'] == 'night')
        if key != self._shore_cache_key:
            self._shore_cache = QImage(round(w*dpr), round(h*dpr), QImage.Format_ARGB32_Premultiplied)
            self._shore_cache.setDevicePixelRatio(dpr)
            self._shore_cache.fill(Qt.transparent)
            painter = QPainter(self._shore_cache)
            painter.setRenderHint(QPainter.Antialiasing)
            self._paint_anime_shore(painter, path, rect)
            painter.end()
            self._shore_cache_key = key
        p.drawImage(0, 0, self._shore_cache)

    def _paint_anime_shore(self, p: QPainter, path, r):
        alpha = 255 if self.illustrated else 100
        scale = r.width()/1176
        p.setBrush(Qt.NoBrush)
        for color, width in ((QColor(75, 111, 81, int(alpha*.38)), 42),
                             (QColor(158, 175, 132, alpha), 31),
                             (QColor(229, 224, 191, alpha), 22),
                             (QColor(198, 205, 170, alpha), 10)):
            p.setPen(QPen(color, width*scale, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.drawPath(path)
        for i in range(52):
            a = i*math.tau/52
            rr = 1+.018*math.sin(5*a)+.012*math.sin(11*a+1.1)+.008*math.sin(19*a+.4)
            x = r.center().x()+math.cos(a)*r.width()*.505*rr
            y = r.center().y()+math.sin(a)*r.height()*.515*rr
            sw, sh = (12+i%5*3)*scale, (5+i%3*2)*scale
            p.save()
            p.translate(x, y)
            p.rotate(math.degrees(math.atan2(math.cos(a)*r.height(), -math.sin(a)*r.width())))
            g = QLinearGradient(0, -sh, 0, sh)
            g.setColorAt(0, QColor(239, 236, 212, alpha))
            g.setColorAt(.6, QColor(201, 207, 176, alpha))
            g.setColorAt(1, QColor(153, 174, 145, alpha))
            p.setBrush(g)
            p.setPen(QPen(QColor(122, 153, 126, alpha//2), .7))
            stone = QPainterPath(QPointF(-sw, 0))
            stone.cubicTo(-sw*.9, -sh, sw*.3, -sh*1.1, sw, -sh*.2)
            stone.cubicTo(sw*1.2, sh*.7, -sw*.4, sh*1.2, -sw, 0)
            p.drawPath(stone)
            if i%3 == 0:
                p.setPen(QPen(QColor(123, 163, 105, alpha), 2*scale, Qt.SolidLine, Qt.RoundCap))
                for k in (-5, 0, 4):
                    p.drawLine(QPointF(k*scale, 0), QPointF((k+3)*scale, -sh-7*scale))
            p.restore()

        if self._daylight['name'] == 'night':
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(26, 51, 78, 115), 42*scale, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.drawPath(path)

    def _paint_tool_hint(self, p, w, h):
        if self.tool == Tool.NONE:
            return
        labels = {Tool.FEED: '喂食 · 轻点水面', Tool.WATER_PLANT: '浇花 · 轻点荷叶',
                  Tool.CHANGE_WATER: '换水 · 轻点水面', Tool.ADD_FISH: '添鱼 · 选择一处水面',
                  Tool.ADD_PLANT: '种荷 · 选择一处水面', Tool.ERASE: '移除 · 轻点鱼或荷花'}
        if self.hover and self.contains(*self.hover, w, h):
            p.setBrush(QColor(255, 253, 228, 28))
            p.setPen(QPen(QColor(255, 253, 228, 195), 1.2, Qt.DashLine))
            p.drawEllipse(QPointF(*self.hover), 24, 12)
        text = labels.get(self.tool, '')+'    /    右键结束'
        f = QFont('Noto Sans CJK SC', 10)
        p.setFont(f)
        width = p.fontMetrics().horizontalAdvance(text)+38
        r = QRectF((w-width)/2, h-57, width, 34)
        p.setBrush(QColor(250, 250, 235, 235))
        p.setPen(QPen(QColor(132, 164, 139, 110), 1))
        p.drawRoundedRect(r, 17, 17)
        p.setPen(QColor('#496E60'))
        p.drawText(r, Qt.AlignCenter, text)

    def paint(self, p: QPainter, w, h, override_hour=None, override_weather=None):
        self._viewport = (w, h)
        r = self.pond_rect(w, h)
        path = self._pond_path(r)
        dl, weather = self.environment(override_hour, override_weather)
        self._daylight = dl
        if self.illustrated:
            self.wallpaper.paint_background(p, w, h, dl, weather)
        self._paint_cached_shore(p, path, r, w, h)
        light = LIGHT[weather]

        p.save()
        p.setClipPath(path)
        self._paint_glass_water_base(p, path, r, max(.62, light))
        self._paint_depth(p, r)
        self._paint_dynamic_water(p, r, dl["ambient"], light)

        # Anime sky/cloud reflections glide slowly across the glassy water.
        p.setPen(Qt.NoPen)
        for i in range(5):
            cx = r.left() + ((.10 + i*.23 + self.t*.0025*(1+i*.08)) % 1.08) * r.width()
            cy = r.top() + (.15 + (i%3)*.25) * r.height()
            rg=QRadialGradient(QPointF(cx,cy), 120+(i%2)*35)
            rg.setColorAt(0,QColor(248,252,247,18)); rg.setColorAt(.58,QColor(229,246,248,9)); rg.setColorAt(1,QColor(255,255,255,0))
            p.setBrush(rg); p.drawEllipse(QPointF(cx,cy),150,42)

        scale = self.entity_scale(r)
        # Fish swim under floating leaves.
        for f in self.state.fish:
            paint_fish(p, f, self.point(f.x, f.y, w, h), scale*.85, self.t, aspect=r.width()/r.height())
        for pl in self.state.plants:
            paint_plant(p, pl, self.point(pl.x, pl.y, w, h), scale*.74, self.t)

        for f in self.food:
            q = self.point(f.x, f.y, w, h)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#8D5B31"))
            p.drawEllipse(q, 3.2, 2.6)
            p.setBrush(QColor(255, 226, 171, 100))
            p.drawEllipse(QPointF(q.x() - 1, q.y() - 1), .8, .6)

        for rp in self.ripples:
            center = self.point(rp.x, rp.y, w, h)
            k = rp.age / rp.max_age
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(225, 255, 250, int(100 * (1 - k))), 1.25))
            p.drawEllipse(center, rp.max_radius * k, rp.max_radius * k * .34)
            # secondary ring gives tool interactions more fluidity
            if k > .16:
                k2 = max(0, k - .16) / .84
                p.setPen(QPen(QColor(225, 255, 250, int(55 * (1 - k2))), .8))
                p.drawEllipse(center, rp.max_radius * k2 * .72, rp.max_radius * k2 * .24)

        for d in self.drops:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(205, 249, 250, int(200 * d.life)))
            p.drawEllipse(QPointF(d.x, d.y), 2.3, 4.2)

        murk = (100 - self.state.water_quality) / 100
        if murk > .02:
            p.fillPath(path, QColor(95, 88, 45, int(105 * murk)))

        tr, tg, tb, ta = dl["tint"]
        p.fillPath(path, QColor(tr, tg, tb, int(ta * (.58 if self.illustrated else .40))))
        if weather == "cloudy":
            p.fillPath(path, QColor(90, 112, 120, 28))
        if weather == "rain":
            p.fillPath(path, QColor(45, 77, 91, 36))
            p.setPen(QPen(QColor(210, 238, 245, 95), 1))
            for i in range(90):
                x = (i * 83 + self.t * 260) % w
                y = (i * 47 + self.t * 420) % h
                p.drawLine(QPointF(x, y), QPointF(x - 4, y + 12))
        if weather == "snow":
            p.fillPath(path, QColor(205, 220, 226, 34))
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(245, 250, 252, 180))
            for i in range(55):
                x = (i * 109 + math.sin(i + self.t) * 18) % w
                y = (i * 61 + self.t * 38 * (1 + i % 3)) % h
                p.drawEllipse(QPointF(x, y), 1.5 + i % 3, 1.5 + i % 3)

        # final glass reflection is above the ecosystem but kept very subtle
        self._paint_glass_finish(p, path, r)
        p.restore()
        if self.illustrated and dl['name'] == 'night':
            self.wallpaper.paint_fireflies(p, w, h, self.t)
        if self.preferences.get('petals', True):
            self.wallpaper.paint_petals(p, w, h, self.t, dl['name'] == 'night')
        if self.preferences.get('show_clock', True):
            self.wallpaper.paint_clock(p, w, h, dl, override_hour)
        self._paint_tool_hint(p, w, h)
