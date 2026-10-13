import os
import unittest
from unittest.mock import patch

from mikasa.exceptions import ConfigurationError

from config import Config


BASE = {
    "API_ID": "1",
    "API_HASH": "hash",
    "BOT_TOKEN": "token",
    "MONGO_URL": "mongodb://localhost",
    "LOGGER_ID": "-100",
    "OWNER_ID": "5",
}


class SettingsTests(unittest.TestCase):
    def test_missing_required(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = Config()
            self.assertEqual(sorted(settings.missing()), sorted(BASE.keys()))

    def test_loads_five_sessions(self):
        env = dict(BASE)
        env.update({f"SESSION_{index}": f"s{index}" for index in range(1, 6)})
        with patch.dict(os.environ, env, clear=True):
            settings = Config()
            settings.validate()
            self.assertEqual(settings.session_slots(), [1, 2, 3, 4, 5])
            self.assertEqual(settings.session_count, 5)

    def test_legacy_session_names(self):
        env = dict(BASE)
        env.update({"SESSION": "one", "SESSION2": "two"})
        with patch.dict(os.environ, env, clear=True):
            settings = Config()
            self.assertEqual(settings.session_slots(), [1, 2])

    def test_no_sessions_rejected(self):
        with patch.dict(os.environ, dict(BASE), clear=True):
            settings = Config()
            with self.assertRaises(ConfigurationError):
                settings.validate()

    def test_api_defaults(self):
        with patch.dict(os.environ, dict(BASE), clear=True):
            settings = Config()
            self.assertEqual(settings.devil_api_url, "")
            self.assertEqual(settings.devil_api_key, "")
            self.assertEqual(settings.shruti_api_url, "https://api.shrutibots.site")
            self.assertEqual(settings.shruti_api_key, "")
