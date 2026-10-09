from __future__ import annotations
import math
from pathlib import Path
from functools import lru_cache
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor, QPainter, QPainterPath, QPen, QLinearGradient, QRadialGradient,
    QPixmap
)

# Fish are rendered from illustrated sprite sequences derived from the project's
# approved style reference. Each sequence has 16 travelling-wave frames so the
# tail and rear body actually sweep laterally instead of merely changing size.
_ASSET_ROOT = Path(__file__).resolve().parents[1] / "assets" / "fish"
_FRAME_COUNT = 16
_PIXMAP_CACHE: dict[tuple[str, int], QPixmap] = {}

COLORS={
 "goldfish":("#F7A43A","#FFE5A3","#E06A24"),
 "neon":("#278BA7","#8DE9EA","#E95B78"),
 "koi":("#FFF8ED","#F7FFFF","#E84531"),
 "betta":("#A34C9B","#E890C4","#5A397E")}


def _sprite(kind: str, frame: int) -> QPixmap | None:
    key=(kind,frame)
    if key in _PIXMAP_CACHE:
        pm=_PIXMAP_CACHE[key]
        return None if pm.isNull() else pm
    path=_ASSET_ROOT/kind/f"{frame:02d}.png"
    pm=QPixmap(str(path))
    _PIXMAP_CACHE[key]=pm
    return None if pm.isNull() else pm


def _paint_shadow(p:QPainter,L:float,H:float,tail_phase:float):
    # Soft submerged shadow; offset is intentionally small so it reads as depth,
    # not as a desktop-game drop shadow.
    sway=math.sin(tail_phase)*H*.035
    for k,a in ((1.00,23),(1.18,13),(1.38,6)):
        g=QRadialGradient(QPointF(L*.045, H*.08+sway),L*.52*k)
        g.setColorAt(0,QColor(4,35,48,a)); g.setColorAt(.72,QColor(4,35,48,a//2)); g.setColorAt(1,QColor(4,35,48,0))
        p.setPen(Qt.NoPen); p.setBrush(g)
        p.drawEllipse(QRectF(-L*.48*k,-H*.34*k+H*.10,L*.96*k,H*.68*k))


def paint_fish(p:QPainter, fish, center:QPointF, scale:float, t:float, aspect:float=1.0):
    # A relaxed fish completes ~1.45 tail beats/s. The visual phase is stable per
    # fish, while faster food-seeking motion raises the cadence slightly.
    hz=1.45 + min(.65,max(0.0,(fish.speed-.035)*8.0))
    phase=t*math.tau*hz + fish.phase
    frame=int(((phase % math.tau)/math.tau)*_FRAME_COUNT)%_FRAME_COUNT
    pm=_sprite(fish.kind,frame)

    # The old 78 px fish was too small to retain the approved illustration detail.
    # 132 px nominal length keeps scales/fins readable on a 1600x900 desktop.
    L=132.0*fish.size*scale
    # Positions live in a normalized ellipse. Correct the illustrated heading
    # for its on-screen aspect so a diagonal fish actually follows its nose.
    heading=math.atan2(math.sin(fish.angle), math.cos(fish.angle)*max(.01,aspect))
    p.save(); p.translate(center); p.rotate(math.degrees(heading))

    # tiny breathing/roll variation prevents sprite-like mechanical motion
    roll=1.0 + .018*math.sin(phase*.5+1.2)
    if pm is not None:
        aspect=pm.height()/max(1,pm.width())
        H=L*aspect
        _paint_shadow(p,L,H,phase)
        p.setRenderHint(QPainter.SmoothPixmapTransform,True)
        p.scale(1.0,roll)
        p.drawPixmap(QRectF(-L*.5,-H*.5,L,H),pm,QRectF(pm.rect()))
        p.restore(); return

    # Fallback vector renderer if assets are missing. It still bends the rear body
    # and swings the tail around the peduncle, unlike the original static body.
    H=42*fish.size*scale
    _paint_shadow(p,L,H,phase)
    base,light,accent=COLORS.get(fish.kind,COLORS['koi'])
    sway=math.sin(phase)
    rear=H*.18*sway
    body=QPainterPath(); body.moveTo(-L*.42,rear)
    body.cubicTo(-L*.25,-H*.48+rear*.45,L*.20,-H*.50,L*.44,0)
    body.cubicTo(L*.20,H*.50,-L*.25,H*.48+rear*.45,-L*.42,rear); body.closeSubpath()
    grad=QLinearGradient(0,-H*.55,0,H*.55); grad.setColorAt(0,QColor(light)); grad.setColorAt(.46,QColor(base)); grad.setColorAt(1,QColor('#79C7C4'))
    p.setPen(QPen(QColor(45,65,70,120),.8)); p.setBrush(grad); p.drawPath(body)
    tail=QPainterPath(); tail.moveTo(-L*.39,rear)
    tail.cubicTo(-L*.58,-H*(.55+.12*sway),-L*.68,-H*(.76+.18*sway),-L*.72,rear-H*.08)
    tail.cubicTo(-L*.68,H*(.76-.18*sway),-L*.58,H*(.55-.12*sway),-L*.39,rear); tail.closeSubpath()
    p.setPen(QPen(QColor(60,80,84,80),.6)); p.setBrush(QColor(light+'B8')); p.drawPath(tail)
    p.restore()


# The pond's normalized outline is a circle of radius .5. Leave enough room
# inside it for the illustrated head and tail, including at diagonal headings.
SWIM_RADIUS = .43


def _angle_delta(goal, current):
    return (goal-current+math.pi) % math.tau-math.pi


def _swim_bounds(fish, pond_size, render_scale):
    if pond_size is None:
        return SWIM_RADIUS, SWIM_RADIUS
    width, height = pond_size
    padding = 132*fish.size*render_scale*.5+3
    return (max(.02, min(SWIM_RADIUS, .5-padding/width)),
            max(.02, min(SWIM_RADIUS, .5-padding/height)))


def _confine(fish, bounds=(SWIM_RADIUS, SWIM_RADIUS)):
    """Keep the entire illustrated fish within the viewport's safe ellipse."""
    rx, ry = bounds
    dx, dy = fish.x-.5, fish.y-.5
    radius = math.hypot(dx/rx, dy/ry)
    if radius <= 1:
        return
    fish.x = .5+dx/radius
    fish.y = .5+dy/radius
    # The normal of an ellipse differs from its center-to-edge direction.
    nx, ny = dx/(rx*rx), dy/(ry*ry)
    normal_length = math.hypot(nx, ny)
    nx, ny = nx/normal_length, ny/normal_length
    vx, vy = math.cos(fish.angle), math.sin(fish.angle)
    outward = vx*nx+vy*ny
    if outward > 0:
        vx -= 2*outward*nx
        vy -= 2*outward*ny
        fish.angle = math.atan2(vy, vx)


@lru_cache(maxsize=512)
def _reachable_food_point(x, y, rx, ry, width, height):
    """Closest screen-space point inside the safe ellipse, including corners.

    A radial projection in normalized coordinates leaves diagonal shore pellets
    too far from a fish in a wide, shallow pond. The closest Euclidean point lets
    its nose reach those pellets while its center stays safely in the water.
    """
    tx, ty = (x-.5)*width, (y-.5)*height
    ax, ay = rx*width*.995, ry*height*.995
    if (tx/ax)**2+(ty/ay)**2 <= 1:
        return x, y
    low, high = 0.0, max(ax*abs(tx), ay*abs(ty))
    def outside(value):
        return (ax*tx/(value+ax*ax))**2+(ay*ty/(value+ay*ay))**2 > 1
    while outside(high):
        high *= 2
    for _ in range(28):
        middle = (low+high)*.5
        if outside(middle):
            low = middle
        else:
            high = middle
    return (.5+ax*ax*tx/(high+ax*ax)/width,
            .5+ay*ay*ty/(high+ay*ay)/height)


def _food_target(fish, food, bounds, pond_size, render_scale):
    target = None
    best = .32
    for pellet in food:
        if pellet.eaten:
            continue
        distance = math.hypot(pellet.x-fish.x, pellet.y-fish.y)
        if distance < best:
            best, target = distance, pellet
    if target is None:
        return None
    if pond_size is None:
        # Preserve the original normalized API for callers without a viewport.
        radius = math.hypot(target.x-.5, target.y-.5)
        reach = .026+max(0.0, min(.5, radius)-SWIM_RADIUS)
        can_eat = best <= reach
        width = height = 1.0
    else:
        width, height = pond_size
        dx, dy = (target.x-fish.x)*width, (target.y-fish.y)*height
        distance = math.hypot(dx, dy)
        heading_x, heading_y = math.cos(fish.angle)*width, math.sin(fish.angle)*height
        heading_length = math.hypot(heading_x, heading_y)
        facing = (dx*heading_x+dy*heading_y)/max(1e-9, distance*heading_length)
        can_eat = distance <= 132*fish.size*render_scale*.5+4 and facing > .35
        can_eat = can_eat or distance < 5
        # The extra .43 center cap intentionally reserves quiet water along the
        # shore. A tiny fish cannot physically bridge that whole margin on a
        # wide display; reaching the nearest safe feeding point still succeeds.
        goal = _reachable_food_point(target.x, target.y, *bounds, width, height)
        at_goal = math.hypot((goal[0]-fish.x)*width, (goal[1]-fish.y)*height) < 6
        can_eat = can_eat or (at_goal and facing > .35)
    if can_eat:
        target.eaten = True
        fish.hunger = max(0.0, fish.hunger-22)
        return None
    return _reachable_food_point(target.x, target.y, *bounds, width, height)


def update_fish(fish_list, food, dt, pond_size=None, render_scale=1.0):
    """Advance relaxed swimming, with seconds-based steering and ellipse bounds."""
    if dt <= 0 or not math.isfinite(dt):
        return
    # Fixed-size substeps make steering stable across 24/30/60 Hz. Limit work
    # after a suspended desktop; the geometric guard still handles large steps.
    steps = min(240, max(1, math.ceil(dt*60)))
    step = dt/steps
    bounds_by_fish = [_swim_bounds(fish, pond_size, render_scale) for fish in fish_list]
    for fish, bounds in zip(fish_list, bounds_by_fish):
        _confine(fish, bounds)
    for _ in range(steps):
        # Use the same flock center for every neon in this substep, so list
        # order does not make the first fish lead the others accidentally.
        neons = [f for f in fish_list if f.kind == "neon"]
        school = None
        if len(neons) > 1:
            school = (sum(f.x for f in neons)/len(neons),
                      sum(f.y for f in neons)/len(neons))
        for f, bounds in zip(fish_list, bounds_by_fish):
            target = _food_target(f, food, bounds, pond_size, render_scale)
            speed = f.speed*(1.3 if target else .8)
            if target:
                desired = math.atan2(target[1]-f.y, target[0]-f.x)
            else:
                seconds = f.age_hours*3600
                wander = (math.sin(f.phase+seconds*.31)
                         +.45*math.sin(f.phase*.73+seconds*.17))
                desired = f.angle+wander*.22
                if school and f.kind == "neon":
                    separation = math.hypot(school[0]-f.x, school[1]-f.y)
                    if separation > .08:
                        group = math.atan2(school[1]-f.y, school[0]-f.x)
                        desired += _angle_delta(group, desired)*.35
            dx, dy = f.x-.5, f.y-.5
            radius = math.hypot(dx/bounds[0], dy/bounds[1])
            soft_edge = .985 if target else .78
            if radius > soft_edge:
                proximity = min(1.0, (radius-soft_edge)/(1-soft_edge))
                ease = proximity*proximity*(3-2*proximity)
                inward = math.atan2(-dy, -dx)
                desired += _angle_delta(inward, desired)*ease
            # Exponential smoothing has the same time constant at every FPS.
            f.angle += _angle_delta(desired, f.angle)*(1-math.exp(-2.3*step))
            f.angle = (f.angle+math.pi) % math.tau-math.pi
            f.x += math.cos(f.angle)*speed*step
            f.y += math.sin(f.angle)*speed*step
            _confine(f, bounds)
            f.age_hours += step/3600
