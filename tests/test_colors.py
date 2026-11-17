import os
import sys
import unittest

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import app


class AverageColorTest(unittest.TestCase):
    def test_uniform_image(self):
        img = Image.new("RGB", (400, 200), (200, 30, 30))
        self.assertEqual(app.average_color(img), (200, 30, 30))

    def test_mixes_all_colors(self):
        # Moitié noire, moitié blanche : la moyenne est un gris moyen, pas la couleur majoritaire.
        img = Image.new("RGB", (400, 200), (0, 0, 0))
        ImageDraw.Draw(img).rectangle((200, 0, 399, 199), fill=(255, 255, 255))
        r, g, b = app.average_color(img)
        self.assertTrue(110 < r < 145 and r == g == b)

    def test_excluded_area_is_ignored(self):
        # La popup (bleue) couvre la majorité de l'image mais doit être ignorée.
        img = Image.new("RGB", (400, 200), (240, 240, 240))
        ImageDraw.Draw(img).rectangle((0, 0, 300, 200), fill=(10, 10, 200))
        r, g, b = app.average_color(img, exclude=(0, 0, 300, 200))
        self.assertTrue(r > 200 and g > 200)

    def test_everything_excluded_falls_back_to_white(self):
        img = Image.new("RGB", (100, 100), (0, 0, 0))
        self.assertEqual(app.average_color(img, exclude=(0, 0, 100, 100)), (255, 255, 255))


class ScreenColorsTest(unittest.TestCase):
    def test_only_the_area_around_counts(self):
        from unittest import mock
        # Écran 1000x500 : moitié gauche rouge foncé, moitié droite blanche.
        screen = Image.new("RGB", (1000, 500), (255, 255, 255))
        ImageDraw.Draw(screen).rectangle((0, 0, 499, 499), fill=(120, 0, 0))
        with mock.patch.object(app.ImageGrab, "grab", return_value=screen), \
                mock.patch.object(app.user32, "GetSystemMetrics", return_value=1000):
            bg, fg, _border = app.screen_colors(area=(50, 50, 300, 300))
        self.assertEqual(bg, "#780000")  # seulement la zone rouge, pas le blanc de droite
        self.assertEqual(fg, "#f1f3f4")  # texte clair sur fond sombre


if __name__ == "__main__":
    unittest.main()
