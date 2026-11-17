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


class HistoryTest(unittest.TestCase):
    def test_contents_include_previous_turns(self):
        history = []
        gemini.add_turn(history, "Bonjour", "Salut !")
        contents = gemini.build_contents("Et toi ?", history=history)
        self.assertEqual([c["role"] for c in contents], ["user", "model", "user"])
        self.assertEqual(contents[1]["parts"], [{"text": "Salut !"}])
        self.assertEqual(contents[2]["parts"], [{"text": "Et toi ?"}])

    def test_no_history(self):
        self.assertEqual(gemini.build_contents("q"), [{"role": "user", "parts": [{"text": "q"}]}])


class ContextTest(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def write(self, name, data):
        path = os.path.join(self.dir.name, name)
        with open(path, "wb") as f:
            f.write(data)
        return path

    def test_text_file(self):
        part = gemini.file_context_part(self.write("notes.txt", "Leçon 1".encode("utf-8")))
        self.assertEqual(part, {"text": "[Fichier : notes.txt]\nLeçon 1"})

    def test_cp1252_text_file(self):
        part = gemini.file_context_part(self.write("vieux.txt", "café".encode("cp1252")))
        self.assertTrue(part["text"].endswith("café"))

    def test_pdf_is_sent_inline(self):
        part = gemini.file_context_part(self.write("cours.PDF", b"abc"))
        self.assertEqual(part["inline_data"], {"mime_type": "application/pdf", "data": "YWJj"})

    def test_binary_file_rejected(self):
        with self.assertRaises(gemini.GeminiError):
            gemini.file_context_part(self.write("prog.exe", b"MZ\0\0"))

    def test_missing_file(self):
        with self.assertRaises(gemini.GeminiError):
            gemini.file_context_part(os.path.join(self.dir.name, "absent.txt"))

    def test_context_goes_before_question_and_not_in_history(self):
        history = []
        gemini.add_turn(history, "Bonjour", "Salut !")
        contents = gemini.build_contents("Résume", history=history,
                                         context=[gemini.text_context_part("abc")])
        last = contents[-1]["parts"]
        self.assertEqual(last[1], {"text": "[Texte]\nabc"})
        self.assertEqual(last[-1], {"text": "Résume"})
        self.assertEqual(contents[0]["parts"], [{"text": "Bonjour"}])


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

        def fake_generate(q, key, name, timeout, image_png=None, history=None, context=None):
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

        def fake_generate(q, key, name, timeout, image_png=None, history=None, context=None):
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

        def fake_generate(q, key, name, timeout, image_png=None, history=None, context=None):
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
