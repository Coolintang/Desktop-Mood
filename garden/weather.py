from __future__ import annotations
import random, time
from .constants import WEATHER_CHANGE_HOURS

TRANSITIONS = {
    "sunny": [("sunny",.58),("cloudy",.30),("rain",.08),("snow",.04)],
    "cloudy": [("sunny",.35),("cloudy",.35),("rain",.22),("snow",.08)],
    "rain": [("cloudy",.55),("rain",.25),("sunny",.18),("snow",.02)],
    "snow": [("cloudy",.52),("snow",.25),("sunny",.20),("rain",.03)],
}
LIGHT = {"sunny":1.0,"cloudy":.72,"rain":.55,"snow":.62}

def update_weather(state, force: str | None = None):
    now=time.time()
    if force:
        state.weather=force; state.weather_until=now+3600*3; return
    if now < state.weather_until: return
    r=random.random(); acc=0
    for name,p in TRANSITIONS.get(state.weather,TRANSITIONS["sunny"]):
        acc += p
        if r <= acc: state.weather=name; break
    state.weather_until=now+random.uniform(*WEATHER_CHANGE_HOURS)*3600
