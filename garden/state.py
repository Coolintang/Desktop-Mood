from __future__ import annotations
import json, time, os, tempfile, math
from pathlib import Path
from .models import AppState, Fish, Plant
from .constants import *

class StateStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.last_error = None
        self._read_failed = False

    def load(self) -> AppState:
        if not self.path.exists():
            s = AppState(
                fish=[Fish(.44,.49,"koi", size=1.18), Fish(.34,.39,"goldfish", angle=.5, size=1.0), Fish(.62,.38,"neon", angle=2.4,size=.72)],
                plants=[Plant(.65,.50, age_hours=30), Plant(.31,.33, age_hours=18), Plant(.77,.28, age_hours=40)]
            )
            return s
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("状态文件必须是 JSON 对象")
            s = AppState.from_dict(raw)
            for number in (s.last_saved, s.water_quality, s.weather_until):
                if not math.isfinite(number):
                    raise ValueError("状态文件包含无效数值")
            for entity in [*s.fish, *s.plants]:
                for key, value in vars(entity).items():
                    if key != "kind" and (not isinstance(value, (int, float)) or not math.isfinite(value)):
                        raise ValueError("生物状态包含无效数值")
        except (OSError, ValueError, TypeError, KeyError) as exc:
            self.last_error = str(exc)
            self._read_failed = True
            return AppState()
        self._settle_offline(s)
        return s

    def _settle_offline(self, s: AppState):
        now = time.time(); hours = min(OFFLINE_SETTLE_HOURS, max(0.0, (now-s.last_saved)/3600.0))
        s.water_quality = max(0.0, s.water_quality - WATER_DECAY_PER_HOUR * hours)
        for f in s.fish:
            f.age_hours += hours; f.hunger = min(100.0, f.hunger + FISH_HUNGER_PER_HOUR*hours)
            if f.hunger >= FISH_STARVE_THRESHOLD: f.health = max(0.0, f.health - 3.5*hours)
        for p in s.plants:
            p.age_hours += hours; p.moisture = max(0.0, p.moisture - 1.4*hours)
        s.last_saved = now

    def save(self, s: AppState) -> bool:
        # Preserve an unreadable original rather than overwrite user data.
        if self._read_failed:
            return False
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = s.to_dict()
            payload["last_saved"] = time.time()
            encoded = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                             prefix=f".{self.path.name}.", delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            s.last_saved = payload["last_saved"]
            self.last_error = None
            return True
        except (OSError, ValueError, TypeError) as exc:
            self.last_error = str(exc)
            return False
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
