import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import gemini
import settings


class ParseHotkeyTest(unittest.TestCase):
    def test_default(self):
        self.assertEqual(settings.parse_hotkey("Ctrl+Alt+G"), (0x2 | 0x1, ord("G")))

    def test_case_spaces_and_function_key(self):
        self.assertEqual(settings.parse_hotkey(" ctrl + shift + f2 "), (0x2 | 0x4, 0x71))

    def test_digit(self):
        self.assertEqual(settings.parse_hotkey("Win+5"), (0x8, ord("5")))

    def test_invalid(self):
        for bad in ("G", "Ctrl+", "Hyper+G", "Ctrl+Espace", "Ctrl+F13"):
            with self.assertRaises(ValueError, msg=bad):
                settings.parse_hotkey(bad)


class ReadableTextTest(unittest.TestCase):
    def test_light_text_on_dark_background(self):
        self.assertEqual(settings.readable_text("#202124")[0], "#f1f3f4")

    def test_dark_text_on_light_background(self):
        self.assertEqual(settings.readable_text("#ffffff")[0], "#202124")


class ConfigFileTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        patcher = mock.patch.object(settings, "app_dir", return_value=self.dir.name)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_defaults_fill_missing_values(self):
        with open(settings.config_path(), "w", encoding="utf-8") as f:
            json.dump({"api_key": "abc", "opacity": 0.9}, f)
        cfg = settings.load_config()
        self.assertEqual((cfg["api_key"], cfg["opacity"], cfg["hotkey"]), ("abc", 0.9, "Ctrl+Alt+G"))

    def test_broken_file_gives_defaults(self):
        with open(settings.config_path(), "w", encoding="utf-8") as f:
            f.write("{pas du json")
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            self.assertEqual(settings.load_config(), settings.DEFAULTS)

    def test_save_does_not_copy_environment_key(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "from-env"}):
            settings.save_config(dict(settings.DEFAULTS, api_key="from-env"))
        self.assertEqual(settings.read_config_file()["api_key"], "")

    def test_save_round_trip(self):
        cfg = dict(settings.DEFAULTS, api_key="k", font_size=14)
        settings.save_config(cfg)
        self.assertEqual(settings.read_config_file(), cfg)


class InstructionsTest(unittest.TestCase):
    def test_system_instruction_added(self):
        body = gemini.build_body("q", instructions="Réponds en anglais.")
        self.assertEqual(body["systemInstruction"], {"parts": [{"text": "Réponds en anglais."}]})

    def test_no_instruction(self):
        self.assertNotIn("systemInstruction", gemini.build_body("q", instructions=""))


if __name__ == "__main__":
    unittest.main()
