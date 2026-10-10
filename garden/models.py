from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any
import random, time, math

@dataclass
class Fish:
    x: float
    y: float
    kind: str = "koi"
    angle: float = 0.0
    speed: float = 0.045
    size: float = 1.0
    hunger: float = 20.0
    health: float = 100.0
    age_hours: float = 0.0
    growth_hours: float | None = None
    phase: float = field(default_factory=lambda: random.random() * 6.283)
    id: int = field(default_factory=lambda: random.randrange(1, 2**31))

@dataclass
class Plant:
    x: float
    y: float
    age_hours: float = 0.0
    moisture: float = 80.0
    growth_hours: float | None = None
    health: float = 100.0
    phase: float = field(default_factory=lambda: random.random() * 6.283)
    id: int = field(default_factory=lambda: random.randrange(1, 2**31))

@dataclass
class Bubble:
    x: float
    y: float
    life: float = 1.0
    radius: float = 3.0

@dataclass
class FoodPellet:
    x: float
    y: float
    life: float = 18.0
    eaten: bool = False

@dataclass
class WaterDrop:
    x: float
    y: float
    vx: float
    vy: float
    life: float = 1.0

@dataclass
class Ripple:
    x: float
    y: float
    age: float = 0.0
    max_age: float = 1.8
    max_radius: float = 90.0

DEFAULT_PREFERENCES = {
    "wallpaper_mode": "scene", "time_mode": "live", "weather_mode": "auto",
    "fps": 30, "petals": True, "show_clock": True,
}


def normalize_preferences(value):
    result = DEFAULT_PREFERENCES.copy()
    if not isinstance(value, dict):
        return result
    choices = {
        "wallpaper_mode": ("scene", "overlay"),
        "time_mode": ("live", "day", "dusk", "night"),
        "weather_mode": ("auto", "sunny", "cloudy", "rain", "snow"),
        "fps": (24, 30, 60),
    }
    for key, allowed in choices.items():
        candidate = value.get(key)
        if candidate in allowed and (key != "fps" or type(candidate) is int):
            result[key] = candidate
    for key in ("petals", "show_clock"):
        if type(value.get(key)) is bool:
            result[key] = value[key]
    return result


@dataclass
class NoteState:
    text: str = ''
    visible: bool = False
    pinned: bool = False
    x: float = .78
    y: float = .12

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict):
            return cls()
        if not isinstance(value.get('text', ''), str):
            raise ValueError('便签内容必须为文本')
        def position(key, default):
            v = value.get(key, default)
            return max(0.0, min(1.0, v)) if isinstance(v, (int, float)) and math.isfinite(v) else default
        return cls(text=value.get('text', ''), visible=value.get('visible') is True,
                   pinned=value.get('pinned') is True, x=position('x', .78), y=position('y', .12))


@dataclass
class AppState:
    fish: list[Fish] = field(default_factory=list)
    plants: list[Plant] = field(default_factory=list)
    water_quality: float = 100.0
    last_saved: float = field(default_factory=time.time)
    weather: str = "sunny"
    weather_until: float = 0.0

    note: NoteState = field(default_factory=NoteState)
    chat: NoteState = field(default_factory=lambda: NoteState(x=.15, y=.2))
    preferences: dict = field(default_factory=lambda: DEFAULT_PREFERENCES.copy())

    def to_dict(self) -> dict[str, Any]:
        return {
            "fish": [asdict(v) for v in self.fish],
            "plants": [asdict(v) for v in self.plants],
            "water_quality": self.water_quality,
            "last_saved": self.last_saved,
            "weather": self.weather,
            "weather_until": self.weather_until,
            "preferences": normalize_preferences(self.preferences),
            "note": asdict(self.note),
            "chat": asdict(self.chat),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AppState":
        if not isinstance(d, dict):
            raise ValueError("状态必须是 JSON 对象")
        for collection in ('fish', 'plants'):
            entities = d.get(collection, [])
            if not isinstance(entities, list) or any(not isinstance(item, dict) for item in entities):
                raise ValueError("生物列表必须由 JSON 对象组成")
        for fish in d.get('fish', []):
            if fish.get('kind', 'koi') not in ('koi', 'goldfish', 'neon', 'betta'):
                raise ValueError("鱼类名称无效")
        return cls(
            fish=[Fish(**x) for x in d.get("fish", [])],
            plants=[Plant(**x) for x in d.get("plants", [])],
            water_quality=float(d.get("water_quality", 100.0)),
            last_saved=float(d.get("last_saved", time.time())),
            weather=str(d.get("weather", "sunny")),
            weather_until=float(d.get("weather_until", 0.0)),
            preferences=normalize_preferences(d.get("preferences")),
            note=NoteState.from_dict(d.get('note')),
            chat=NoteState.from_dict(d.get('chat', {'x': .15, 'y': .2})),
        )
