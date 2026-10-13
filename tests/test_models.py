import unittest

from mikasa.helpers._dataclass import ChatSettings, Media, Track


class TrackTests(unittest.TestCase):
    def test_id_and_file_flag(self):
        track = Track(video_id="abc", title="Song", duration_seconds=200, url="u")
        self.assertEqual(track.id, "abc")
        self.assertFalse(track.has_file)
        track.file_path = "/tmp/a.mp3"
        self.assertTrue(track.has_file)


class MediaTests(unittest.TestCase):
    def test_id_is_file_id(self):
        media = Media(file_id="f1", title="Clip", duration_seconds=10, file_path="/tmp/a.mp4")
        self.assertEqual(media.id, "f1")
        self.assertTrue(media.has_file)


class ChatSettingsTests(unittest.TestCase):
    def test_defaults(self):
        settings = ChatSettings.from_document({})
        self.assertEqual(settings.language, "en")
        self.assertEqual(settings.loop, 0)
        self.assertFalse(settings.paused)

    def test_roundtrip(self):
        original = ChatSettings(language="tr", loop=2, paused=True, assistant=3, autoplay=True)
        restored = ChatSettings.from_document(original.to_document())
        self.assertEqual(restored, original)
