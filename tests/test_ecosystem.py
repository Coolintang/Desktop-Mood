"""Behavioral regressions for pond movement and sprite alpha statistics."""
import copy
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from PySide6.QtGui import QColor, QImage

from garden.fish import SWIM_RADIUS, update_fish
from garden.models import Fish, FoodPellet
from tools.inspect_sprites import inspect


class SwimmingTests(unittest.TestCase):
    def test_diagonal_and_legacy_positions_stay_inside_ellipse(self):
        fish = [Fish(.5+math.cos(a)*radius, .5+math.sin(a)*radius,
                     angle=a, phase=.6)
                for a in (0, .7, 1.6, 2.6, 4.2)
                for radius in (.30, .43, .60)]
        for _ in range(240):
            update_fish(fish, [], .1)
            for current in fish:
                self.assertLessEqual(math.hypot(current.x-.5, current.y-.5),
                                     SWIM_RADIUS+1e-12)
        self.assertTrue(all(current.age_hours > 0 for current in fish))

    def test_frame_rates_produce_the_same_motion(self):
        initial = Fish(.73, .69, angle=.7, phase=1.2)
        results = []
        for fps in (24, 30, 60):
            fish = copy.deepcopy(initial)
            for _ in range(fps*8):
                update_fish([fish], [], 1/fps)
            results.append(fish)
            self.assertAlmostEqual(fish.age_hours, 8/3600, places=8)
        for fish in results:
            self.assertLess(math.hypot(fish.x-results[-1].x,
                                      fish.y-results[-1].y), .006)

    def test_shore_pellets_remain_reachable(self):
        for angle in (0, math.pi/4, math.pi, math.pi*1.5):
            fish = Fish(.5+math.cos(angle)*.35, .5+math.sin(angle)*.35,
                        angle=angle, hunger=55, phase=.8)
            pellet = FoodPellet(.5+math.cos(angle)*.495,
                               .5+math.sin(angle)*.495)
            for _ in range(30*10):
                update_fish([fish], [pellet], 1/30)
                if pellet.eaten:
                    break
            self.assertTrue(pellet.eaten)
            self.assertEqual(fish.hunger, 33)
            self.assertLessEqual(math.hypot(fish.x-.5, fish.y-.5), SWIM_RADIUS)

    def test_viewport_bounds_leave_room_for_fish_heads_at_both_banks(self):
        kinds = (("koi", 1.18), ("goldfish", 1), ("neon", .72), ("betta", 1.08))
        for screen in ((1600, 900), (640, 420)):
            width, height = screen[0]*.735, screen[1]*.415
            scale = max(.2, min(1.35, width/900, height/360))*.85
            for kind, size in kinds:
                for y, angle in ((.07, -math.pi/2), (.93, math.pi/2)):
                    with self.subTest(screen=screen, kind=kind, y=y):
                        fish = Fish(.5, y, kind, size=size, angle=angle, phase=0)
                        update_fish([fish], [], 1/30,
                                    pond_size=(width, height), render_scale=scale)
                        half_length = 132*size*scale*.5
                        self.assertGreaterEqual(fish.y*height-half_length, 2.9)
                        self.assertGreaterEqual((1-fish.y)*height-half_length, 2.9)
                        self.assertGreaterEqual(fish.x*width-half_length, 2.9)
                        self.assertGreaterEqual((1-fish.x)*width-half_length, 2.9)

    def test_viewport_shore_food_is_reachable_including_diagonal_banks(self):
        kinds = (("koi", 1.18), ("goldfish", 1), ("neon", .72), ("betta", 1.08))
        for screen in ((1600, 900), (640, 420)):
            width, height = screen[0]*.735, screen[1]*.415
            scale = max(.2, min(1.35, width/900, height/360))*.85
            for kind, size in kinds:
                for direction in range(8):
                    angle = direction*math.pi/4
                    with self.subTest(screen=screen, kind=kind, direction=direction):
                        fish = Fish(.5+math.cos(angle)*.22,
                                    .5+math.sin(angle)*.22, kind,
                                    size=size, angle=angle, phase=0, hunger=55)
                        pellet = FoodPellet(.5+math.cos(angle)*.495,
                                           .5+math.sin(angle)*.495)
                        for _ in range(30*17):
                            update_fish([fish], [pellet], 1/30,
                                        pond_size=(width, height), render_scale=scale)
                            if pellet.eaten:
                                break
                        self.assertTrue(pellet.eaten)
                        self.assertEqual(fish.hunger, 33)

    def test_invalid_elapsed_time_does_not_change_fish(self):
        fish = Fish(.4, .5, phase=0)
        before = copy.deepcopy(fish)
        for dt in (0, -.1, math.inf, math.nan):
            update_fish([fish], [], dt)
        self.assertEqual(fish, before)


class SpriteStatisticsTests(unittest.TestCase):
    def _write_sprite(self, directory, name, point):
        image = QImage(12, 6, QImage.Format_RGBA8888)
        image.fill(QColor(0, 0, 0, 0))
        image.setPixelColor(*point, QColor(255, 255, 255, 255))
        self.assertTrue(image.save(str(directory/name)))

    def test_centroid_is_not_divided_by_frame_count_twice(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)/"sample"
            directory.mkdir()
            for index in range(5):
                self._write_sprite(directory, f"{index:02}.png", (9, 4))
            report = inspect("sample", temporary)
        self.assertEqual(report["mean_center"], [9.0, 4.0])
        self.assertEqual(report["sample_count"], 5)

    def test_mass_distribution_includes_each_sample(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)/"sample"
            directory.mkdir()
            self._write_sprite(directory, "00.png", (1, 1))
            self._write_sprite(directory, "01.png", (10, 4))
            report = inspect("sample", temporary)
        self.assertEqual(report["mass_x_thirds"], [.5, 0.0, .5])
        self.assertEqual(report["mass_y_thirds"], [.5, 0.0, .5])
        self.assertEqual(report["mean_center"], [5.5, 2.5])

    def test_import_has_no_file_or_application_side_effects(self):
        root = Path(__file__).resolve().parents[1]
        code = ("from tools import inspect_sprites; "
                "from PySide6.QtWidgets import QApplication; "
                "assert QApplication.instance() is None")
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(root)
        with tempfile.TemporaryDirectory() as temporary:
            result = subprocess.run([sys.executable, "-c", code],
                                    cwd=temporary, env=environment,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(list(Path(temporary).iterdir()), [])
            self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
