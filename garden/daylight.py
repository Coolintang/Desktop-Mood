from __future__ import annotations
from datetime import datetime
from zoneinfo import ZoneInfo
import math
from .constants import TIMEZONE

def local_hour(now: datetime | None = None) -> float:
    now = now or datetime.now(ZoneInfo(TIMEZONE))
    return now.hour + now.minute/60 + now.second/3600

def daylight(hour: float | None = None) -> dict:
    h = local_hour() if hour is None else hour
    sun = max(0.0, math.sin((h-6.5)/13.0*math.pi)) if 6.5 <= h <= 19.5 else 0.0
    if h < 5 or h >= 21: name, tint, ambient = "night", (25,45,85,150), .25
    elif h < 6.5: name, tint, ambient = "dawn", (116,89,126,75), .48
    elif h < 9: name, tint, ambient = "sunrise", (255,174,121,48), .76
    elif h < 16.5: name, tint, ambient = "day", (255,255,235,10), 1.0
    elif h < 18: name, tint, ambient = "golden", (255,178,95,50), .83
    elif h < 20: name, tint, ambient = "dusk", (118,74,126,85), .55
    else: name, tint, ambient = "night", (25,45,85,150), .25
    return {"name":name,"sun":sun,"ambient":ambient,"tint":tint}
