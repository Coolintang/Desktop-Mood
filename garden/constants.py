from __future__ import annotations
from enum import Enum

FPS = 30
MAX_ENTITIES = 50
HOURS_PER_DAY = 24.0
WATER_QUALITY_INIT = 100.0
WATER_DECAY_PER_HOUR = 1.5
FEED_POLLUTION = 5.0
FISH_LIFESPAN_DAYS = 7
FISH_HUNGER_PER_HOUR = 3.0
FISH_STARVE_THRESHOLD = 80.0
PLANT_STAGE_HOURS = [6, 12, 24, 36]
PLANT_BLOOM_CYCLE = 48
WEATHER_CHANGE_HOURS = (2, 8)
OFFLINE_SETTLE_HOURS = 12.0
TIMEZONE = "Asia/Shanghai"

class Tool(str, Enum):
    NONE = "none"
    FEED = "feed"
    WATER_PLANT = "water_plant"
    CHANGE_WATER = "change_water"
    ADD_FISH = "add_fish"
    ADD_PLANT = "add_plant"
    ERASE = "erase"

FISH_KINDS = ("goldfish", "neon", "koi", "betta")

PALETTE = {
    "water_deep": "#147E91",
    "water_mid": "#2AA7B4",
    "water_edge": "#70D1C9",
    "caustic": "#D9FFF3",
    "leaf_dark": "#185C4B",
    "leaf_mid": "#2F8061",
    "leaf_light": "#83B95B",
    "lotus_pink": "#F29AB4",
    "lotus_white": "#FFF6F7",
}
