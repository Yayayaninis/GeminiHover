import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import gemini


class ExtractTextTest(unittest.TestCase):
    def test_joins_parts(self):
        payload = {"candidates": [{"content": {"parts": [{"text": "Bon"}, {"text": "jour "}]}}]}
        self.assertEqual(gemini.extract_text(payload), "Bonjour")

    def test_blocked(self):
        with self.assertRaises(gemini.GeminiError):
            gemini.extract_text({"promptFeedback": {"blockReason": "SAFETY"}})

    def test_missing_key(self):
        with self.assertRaises(gemini.GeminiError):
            gemini.ask("q", "", "m")


class BuildPartsTest(unittest.TestCase):
    def test_text_only(self):
        self.assertEqual(gemini.build_parts("q"), [{"text": "q"}])

    def test_with_image(self):
        parts = gemini.build_parts("q", b"abc")
        self.assertEqual(parts[1]["inline_data"], {"mime_type": "image/png", "data": "YWJj"})


class RankModelsTest(unittest.TestCase):
    def m(self, *names):
        return [{"name": "models/" + n, "supportedGenerationMethods": ["generateContent"]} for n in names]

    def test_order(self):
        models = self.m("gemini-2.5-flash", "gemini-3.6-flash", "gemini-3.7-flash-lite",
                        "gemini-3.6-flash-image", "gemini-3.1-pro", "gemini-3.8-flash-preview")
        self.assertEqual(gemini.rank_models(models),
                         ["gemini-3.6-flash", "gemini-2.5-flash", "gemini-3.7-flash-lite", "gemini-3.8-flash-preview"])

    def test_none(self):
        with self.assertRaises(gemini.GeminiError):
            gemini.rank_models(self.m("gemini-3.1-pro"))


class FallbackTest(unittest.TestCase):
    def test_skips_overloaded_model(self):
        import io
        import urllib.error
        from unittest import mock

        def fake_generate(q, key, name, timeout, image_png=None):
            if name == "gemini-3.6-flash":
                raise urllib.error.HTTPError("u", 503, "busy", {}, io.BytesIO(b"{}"))
            return "ok"

        models = [{"name": "models/" + n, "supportedGenerationMethods": ["generateContent"]}
                  for n in ("gemini-3.6-flash", "gemini-2.5-flash")]
        with mock.patch.object(gemini, "list_models", return_value=models),                 mock.patch.object(gemini, "_generate", side_effect=fake_generate):
            self.assertEqual(gemini.ask("q", "k", "auto"), ("ok", "gemini-2.5-flash"))


class TimeoutFallbackTest(unittest.TestCase):
    def test_skips_model_that_times_out(self):
        from unittest import mock

        def fake_generate(q, key, name, timeout, image_png=None):
            if name == "gemini-3.6-flash":
                raise TimeoutError("The read operation timed out")
            return "ok"

        models = [{"name": "models/" + n, "supportedGenerationMethods": ["generateContent"]}
                  for n in ("gemini-3.6-flash", "gemini-2.5-flash")]
        gemini._working_model = None
        with mock.patch.object(gemini, "list_models", return_value=models),                 mock.patch.object(gemini, "_generate", side_effect=fake_generate):
            self.assertEqual(gemini.ask("q", "k", "auto"), ("ok", "gemini-2.5-flash"))


class PreferredModelTest(unittest.TestCase):
    def test_preferred_is_tried_first(self):
        from unittest import mock
        tried = []

        def fake_generate(q, key, name, timeout, image_png=None):
            tried.append(name)
            return "ok"

        models = [{"name": "models/" + n, "supportedGenerationMethods": ["generateContent"]}
                  for n in ("gemini-3.6-flash", "gemini-3.5-flash-lite")]
        gemini._working_model = None
        with mock.patch.object(gemini, "list_models", return_value=models),                 mock.patch.object(gemini, "_generate", side_effect=fake_generate):
            gemini.ask("q", "k", "auto", preferred="gemini-3.5-flash-lite")
        self.assertEqual(tried, ["gemini-3.5-flash-lite"])


if __name__ == "__main__":
    unittest.main()
