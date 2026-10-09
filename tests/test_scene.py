"""Tool actions and wallpaper rendering, independent of any desktop or save."""
import math
import os
import unittest
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication
from garden.constants import MAX_ENTITIES, Tool
from garden.models import AppState, Fish, Plant
from garden.scene import PondScene


class SceneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.state = AppState(weather_until=4102444800)
        self.scene = PondScene(self.state)

    def click(self, tool, nx=.5, ny=.5):
        point = self.scene.point(nx, ny, 1600, 900)
        return self.scene.apply_tool(tool, point.x(), point.y(), 1600, 900)

    def render(self, hour=13, weather='sunny', width=640, height=420):
        image = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        self.scene.paint(painter, width, height, hour, weather)
        painter.end()
        return image

    def test_tools_ignore_desktop_outside_both_pond_layouts(self):
        for mode in ('scene', 'overlay'):
            self.state.preferences['wallpaper_mode'] = mode
            for tool in Tool:
                self.assertIsNone(self.scene.apply_tool(tool, 0, 0, 1600, 900))
            self.assertEqual(len(self.state.fish)+len(self.state.plants)+len(self.scene.food), 0)

    def test_feeding_is_bounded_and_water_change_cleans(self):
        for _ in range(100):
            self.assertTrue(self.click(Tool.FEED))
        self.assertLessEqual(len(self.scene.food), 75)
        self.assertGreaterEqual(self.state.water_quality, 0)
        del self.scene.food[:2]
        self.click(Tool.FEED)
        self.assertEqual(len(self.scene.food), 75)
        for food in self.scene.food:
            self.assertLess(math.hypot(food.x-.5, food.y-.5), .5)
        self.click(Tool.CHANGE_WATER)
        self.assertEqual(self.state.water_quality, 100)
        self.assertEqual(self.scene.food, [])

    def test_new_residents_are_inside_water_and_population_is_bounded(self):
        self.click(Tool.ADD_FISH, .985, .5)
        self.click(Tool.ADD_PLANT, .015, .5)
        for obj in self.state.fish+self.state.plants:
            self.assertLessEqual(math.hypot(obj.x-.5, obj.y-.5), .401)
        for _ in range(MAX_ENTITIES+10):
            self.click(Tool.ADD_FISH)
        self.assertEqual(len(self.state.fish)+len(self.state.plants), MAX_ENTITIES)

    def test_watering_and_erasing_use_visible_target_positions(self):
        plant = Plant(.5, .5, moisture=30)
        fish = Fish(.75, .5)
        self.state.plants.append(plant)
        self.state.fish.append(fish)
        self.click(Tool.WATER_PLANT, .2, .5)
        self.assertEqual(plant.moisture, 30)
        self.click(Tool.WATER_PLANT)
        self.assertEqual(plant.moisture, 65)
        self.click(Tool.ERASE, .75, .5)
        self.assertEqual(self.state.fish, [])
        self.assertEqual(self.state.plants, [plant])

    def test_effects_expire_and_plants_grow_while_running(self):
        plant = Plant(.5, .5, age_hours=5, moisture=30)
        self.state.plants.append(plant)
        self.click(Tool.FEED)
        self.click(Tool.WATER_PLANT)
        for _ in range(80):
            self.scene.update(.25)
        self.assertFalse(self.scene.food or self.scene.ripples or self.scene.drops)
        self.assertGreater(plant.age_hours, 5)
        self.assertLess(plant.moisture, 65)

    def test_legacy_plants_are_reachable_inside_water(self):
        state = AppState(plants=[Plant(.9, .9)])
        scene = PondScene(state)
        plant = state.plants[0]
        self.assertLessEqual(math.hypot(plant.x-.5, plant.y-.5), .4+1e-12)
        point = scene.point(plant.x, plant.y, 1600, 900)
        scene.apply_tool(Tool.ERASE, point.x(), point.y(), 1600, 900)
        self.assertFalse(state.plants)

    def test_render_modes_weather_and_motion(self):
        day = self.render()
        self.assertEqual(day.pixelColor(0, 0).alpha(), 255)
        for hour, weather in ((23, 'sunny'), (18.6, 'sunny'), (13, 'rain'), (9, 'snow')):
            image = self.render(hour, weather)
            self.assertNotEqual(image, day)
            self.assertEqual(image.pixelColor(0, 0).alpha(), 255)
        self.state.preferences.update(wallpaper_mode='overlay', show_clock=False, petals=False)
        image = self.render(width=960, height=600)
        self.assertEqual(image.pixelColor(0, 0).alpha(), 0)
        self.assertGreater(image.pixelColor(480, 300).alpha(), 100)
        self.scene.update(.25)
        self.assertNotEqual(image, self.render(width=960, height=600))


if __name__ == '__main__':
    unittest.main()
