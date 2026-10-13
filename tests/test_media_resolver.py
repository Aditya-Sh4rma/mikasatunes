import tempfile
import unittest
from pathlib import Path

from mikasa.core.youtube import MediaResolver
from mikasa.exceptions import DownloadError
from mikasa.helpers._dataclass import Media, Track


class FakeYouTube:
    def __init__(self):
        self.calls = []

    async def download(self, track, directory, *, audio_only=True, limit_bytes=None):
        self.calls.append((track.video_id, audio_only, limit_bytes))
        path = Path(directory) / f"{track.video_id}.mp3"
        path.write_text("data")
        return path


class FakeIntake:
    def __init__(self):
        self.calls = []

    async def from_url(self, url, directory, *, title=None, is_video=False):
        self.calls.append((url, title, is_video))
        path = Path(directory) / "url.mp3"
        path.write_text("data")
        return Media(file_id="u", title=title or "u", duration_seconds=0, file_path=str(path), url=url)


class ResolverTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    async def test_resolves_track(self):
        youtube = FakeYouTube()
        resolver = MediaResolver(youtube, FakeIntake(), max_bytes=123)
        track = Track(video_id="dQw4w9WgXcQ", title="T", duration_seconds=1, url="u")
        path = await resolver(1, track, self.root / "1")
        self.assertTrue(path.exists())
        self.assertEqual(youtube.calls, [("dQw4w9WgXcQ", True, 123)])

    async def test_reuses_existing_file(self):
        existing = self.root / "x.mp3"
        existing.write_text("data")
        resolver = MediaResolver(FakeYouTube(), FakeIntake())
        media = Media(file_id="m", title="t", duration_seconds=1, file_path=str(existing))
        path = await resolver(1, media, self.root / "1")
        self.assertEqual(path, existing)

    async def test_resolves_url_media(self):
        intake = FakeIntake()
        resolver = MediaResolver(FakeYouTube(), intake)
        media = Media(file_id="m", title="t", duration_seconds=1, file_path="", url="https://host/a.mp3")
        path = await resolver(1, media, self.root / "1")
        self.assertTrue(path.exists())
        self.assertEqual(intake.calls[0][0], "https://host/a.mp3")

    async def test_unresolvable(self):
        resolver = MediaResolver(FakeYouTube(), FakeIntake())
        media = Media(file_id="m", title="t", duration_seconds=1, file_path="")
        with self.assertRaises(DownloadError):
            await resolver(1, media, self.root / "1")
