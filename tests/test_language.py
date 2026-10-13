import json
import tempfile
import unittest
from pathlib import Path

from mikasa.core.lang import Language


class LanguageTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        (root / "en.json").write_text(json.dumps({"ping": "Pong {latency}", "only_en": "english"}), encoding="utf-8")
        (root / "tr.json").write_text(json.dumps({"ping": "Ping {latency}"}), encoding="utf-8")
        self.language = Language(root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_available(self):
        self.assertEqual(self.language.available(), ["en", "tr"])

    def test_text_and_format(self):
        self.assertEqual(self.language.text("en", "ping", latency=12), "Pong 12")

    def test_fallback_to_default(self):
        self.assertEqual(self.language.text("tr", "only_en"), "english")

    def test_missing_key_returns_key(self):
        self.assertEqual(self.language.text("en", "absent"), "absent")

    def test_unknown_language_uses_default(self):
        self.assertEqual(self.language.text("zz", "only_en"), "english")
