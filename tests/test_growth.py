"""Care, age, visible growth and offline continuity use one simulation."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from garden.models import AppState, Fish, Plant
from garden.growth import (advance_growth, fish_size, fish_stage, fish_progress,
                           plant_phase, FISH_MATURITY_HOURS)
from garden.state import StateStore
from garden.scene import PondScene
from garden.constants import Tool


class GrowthTests(unittest.TestCase):
    def test_added_fish_and_plants_start_young(self):
        state = AppState()
        scene = PondScene(state)
        point = scene.pond_rect(1600, 900).center()
        scene.apply_tool(Tool.ADD_FISH, point.x(), point.y(), 1600, 900)
        scene.apply_tool(Tool.ADD_PLANT, point.x(), point.y(), 1600, 900)
        self.assertEqual(fish_stage(state.fish[0]), '幼鱼')
        self.assertLess(fish_size(state.fish[0]), state.fish[0].size*.5)
        self.assertEqual(plant_phase(state.plants[0])[0], '萌芽')
        self.assertEqual(state.plants[0].age_hours, 0)

    def test_fish_grow_continuously_to_species_specific_adult_sizes(self):
        for kind, duration in FISH_MATURITY_HOURS.items():
            with self.subTest(kind=kind):
                fish = Fish(.5, .5, kind, size=1.1, growth_hours=0)
                state = AppState(fish=[fish])
                sizes = [fish_size(fish)]
                for _ in range(int(duration)+1):
                    fish.hunger = 15
                    state.water_quality = 100
                    advance_growth(state, 1)
                    sizes.append(fish_size(fish))
                self.assertTrue(all(a <= b for a, b in zip(sizes, sizes[1:])))
                self.assertAlmostEqual(fish_size(fish), 1.1)
                self.assertEqual(fish_stage(fish), '成鱼')

    def test_poor_care_slows_growth_and_good_care_recovers_health(self):
        healthy = AppState(fish=[Fish(.5, .5, growth_hours=0)], plants=[Plant(.5, .5, growth_hours=0)])
        neglected = copy.deepcopy(healthy)
        neglected.water_quality = 15
        neglected.fish[0].hunger = 95
        neglected.plants[0].moisture = 0
        advance_growth(healthy, 4)
        advance_growth(neglected, 4)
        self.assertGreater(healthy.fish[0].growth_hours, neglected.fish[0].growth_hours)
        self.assertGreater(healthy.plants[0].growth_hours, neglected.plants[0].growth_hours)
        self.assertLess(neglected.fish[0].health, 100)
        self.assertLess(neglected.plants[0].health, 100)
        health = neglected.fish[0].health
        neglected.water_quality = 100
        neglected.fish[0].hunger = 10
        neglected.plants[0].moisture = 100
        advance_growth(neglected, 2)
        self.assertGreater(neglected.fish[0].health, health)
        self.assertGreater(neglected.fish[0].growth_hours, 0)

    def test_lotus_buds_blooms_fades_rests_and_reblooms(self):
        plant = Plant(.5, .5, growth_hours=0)
        for hour, expected in ((0, '萌芽'), (7, '展叶'), (20, '孕蕾'), (32, '盛放'),
                               (49, '凋谢'), (56, '休眠'), (68, '孕蕾'), (80, '盛放')):
            plant.growth_hours = hour
            self.assertEqual(plant_phase(plant)[0], expected)

    def test_online_and_offline_have_identical_care_and_growth(self):
        original = AppState(fish=[Fish(.5, .5, growth_hours=0)],
                            plants=[Plant(.5, .5, growth_hours=0)], last_saved=10000)
        online = copy.deepcopy(original)
        for _ in range(12*60):
            advance_growth(online, 1/60)
        offline = copy.deepcopy(original)
        with patch('garden.state.time.time', return_value=10000+12*3600):
            StateStore('/unused/test.json')._settle_offline(offline)
        for field in ('age_hours', 'growth_hours', 'health', 'hunger'):
            self.assertAlmostEqual(getattr(online.fish[0], field), getattr(offline.fish[0], field), places=6)
        for field in ('age_hours', 'growth_hours', 'moisture', 'health'):
            self.assertAlmostEqual(getattr(online.plants[0], field), getattr(offline.plants[0], field), places=6)
        self.assertEqual(online.water_quality, offline.water_quality)

    def test_scene_does_not_double_count_fish_age(self):
        state = AppState(fish=[Fish(.5, .5, growth_hours=0)], weather_until=4102444800)
        scene = PondScene(state)
        for _ in range(120):
            scene.update(.25)
        self.assertAlmostEqual(state.fish[0].age_hours, 30/3600, places=9)
        self.assertGreater(state.fish[0].growth_hours, 0)

    def test_legacy_fish_size_and_flower_progress_survive_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'legacy.json'
            path.write_text(json.dumps({'fish': [{'x': .5, 'y': .5, 'size': 1.18}],
                                        'plants': [{'x': .4, 'y': .5, 'age_hours': 32}]}))
            store = StateStore(path)
            state = store.load()
            self.assertEqual(fish_size(state.fish[0]), 1.18)
            self.assertEqual(fish_progress(state.fish[0]), 1)
            self.assertEqual(plant_phase(state.plants[0])[0], '盛放')
            self.assertTrue(store.save(state))
            self.assertEqual(fish_size(StateStore(path).load().fish[0]), 1.18)

    def test_partial_growth_round_trip_does_not_reset_to_adult(self):
        state = AppState(fish=[Fish(.5, .5, growth_hours=10)], plants=[Plant(.5, .5, growth_hours=7)])
        restored = AppState.from_dict(state.to_dict())
        self.assertEqual(restored.fish[0].growth_hours, 10)
        self.assertEqual(plant_phase(restored.plants[0])[0], '展叶')
        self.assertLess(fish_size(restored.fish[0]), restored.fish[0].size)
