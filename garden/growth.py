"""Care-dependent, real-hour simulation shared by online and offline updates.

These are deliberately shortened garden simulation cycles, not biological
lifespans. Fish remain in the garden when old; perennial lotus flowers rebloom.
"""
from __future__ import annotations
import math
from .constants import FISH_HUNGER_PER_HOUR, WATER_DECAY_PER_HOUR

FISH_MATURITY_HOURS = {'koi': 168.0, 'goldfish': 120.0, 'neon': 48.0, 'betta': 72.0}
FISH_NAMES = {'koi': '锦鲤', 'goldfish': '金鱼', 'neon': '霓虹鱼', 'betta': '斗鱼'}
PLANT_FIRST_BLOOM = 30.0
PLANT_CYCLE_HOURS = 48.0


def clamp(value, low=0.0, high=1.0):
    return max(low, min(high, value))


def fish_progress(fish):
    if fish.growth_hours is None:  # Existing fish keep their original adult size.
        return 1.0
    return clamp(fish.growth_hours / FISH_MATURITY_HOURS.get(fish.kind, 120.0))


def fish_size(fish):
    return fish.size * (.36 + .64 * fish_progress(fish) ** .72)


def fish_stage(fish):
    progress = fish_progress(fish)
    if progress < .2:
        return '幼鱼'
    if progress < .65:
        return '成长鱼'
    if progress < 1:
        return '亚成鱼'
    if fish.age_hours >= FISH_MATURITY_HOURS.get(fish.kind, 120)*30:
        return '老成鱼'
    return '成鱼'


def plant_growth(plant):
    return plant.age_hours if plant.growth_hours is None else plant.growth_hours


def plant_phase(plant):
    age = plant_growth(plant)
    if age < 6:
        return '萌芽', age/6
    if age < 18:
        return '展叶', (age-6)/12
    if age < PLANT_FIRST_BLOOM:
        return '孕蕾', (age-18)/12
    cycle = (age-PLANT_FIRST_BLOOM) % PLANT_CYCLE_HOURS
    if cycle < 18:
        return '盛放', cycle/18
    if cycle < 24:
        return '凋谢', (cycle-18)/6
    if cycle < 36:
        return '休眠', (cycle-24)/12
    return '孕蕾', (cycle-36)/12


def advance_growth(state, hours):
    """Integrate in at most one-minute steps so offline care matches online care."""
    if not math.isfinite(hours) or hours <= 0:
        return
    steps = max(1, math.ceil(hours*60))
    dt = hours/steps
    for _ in range(steps):
        quality = clamp(state.water_quality-WATER_DECAY_PER_HOUR*dt*.5, 0, 100)
        water = clamp((quality-15)/60)
        for fish in state.fish:
            hunger = clamp(fish.hunger+FISH_HUNGER_PER_HOUR*dt*.5, 0, 100)
            nutrition = clamp((100-hunger)/65)
            if fish.growth_hours is not None:
                fish.growth_hours += dt*nutrition*water*clamp(fish.health/80)
            fish.age_hours += dt
            if hunger > 80 or quality < 35:
                damage = max(0, hunger-80)/20*2.2 + max(0, 35-quality)/35*1.6
                fish.health = clamp(fish.health-damage*dt, 0, 100)
            elif hunger < 60 and quality > 60:
                fish.health = clamp(fish.health+dt, 0, 100)
            fish.hunger = clamp(fish.hunger+FISH_HUNGER_PER_HOUR*dt, 0, 100)
        for plant in state.plants:
            if plant.growth_hours is None:
                plant.growth_hours = plant.age_hours
            moisture = clamp(plant.moisture-1.4*dt*.5, 0, 100)
            plant.growth_hours += dt*clamp(moisture/45)*(.25+.75*water)*clamp(plant.health/70)
            plant.age_hours += dt
            plant.moisture = clamp(plant.moisture-1.4*dt, 0, 100)
            if moisture < 20:
                plant.health = clamp(plant.health-(20-moisture)/20*3*dt, 0, 100)
            elif moisture > 45 and quality > 45:
                plant.health = clamp(plant.health+2*dt, 0, 100)
        state.water_quality = clamp(state.water_quality-WATER_DECAY_PER_HOUR*dt, 0, 100)


def describe_fish(fish):
    return (f'{FISH_NAMES.get(fish.kind, "鱼")} · {fish_stage(fish)} · {fish.age_hours:.1f} 小时'
            f'\n饥饿 {fish.hunger:.0f}% · 健康 {fish.health:.0f}% · 成长 {fish_progress(fish):.0%}')


def describe_plant(plant):
    phase, _ = plant_phase(plant)
    return (f'荷花 · {phase} · {plant.age_hours:.1f} 小时'
            f'\n水分 {plant.moisture:.0f}% · 健康 {plant.health:.0f}%')


def growth_summary(state):
    young = sum(fish_progress(fish) < 1 for fish in state.fish)
    blooming = sum(plant_phase(plant)[0] == '盛放' for plant in state.plants)
    summary = f'成长中的鱼 {young} 尾  ·  盛放的花 {blooming} 株'
    details = '\n\n'.join([describe_fish(f) for f in state.fish]+[describe_plant(p) for p in state.plants])
    return summary, details or '添一尾幼鱼，或种下一株新芽，开始照料吧。'
