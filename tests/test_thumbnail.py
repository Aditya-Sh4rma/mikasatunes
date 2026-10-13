import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from mikasa.helpers._thumbnails import Thumbnail


def png_bytes(color=(10, 20, 30), size=(640, 360)):
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, "PNG")
    return buffer.getvalue()


def track(video_id="vid1"):
    return SimpleNamespace(
        video_id=video_id,
        title="Some Song Title",
        thumbnail="https://img.youtube.com/vi/x/default.jpg",
        channel="Some Channel",
    )


class ThumbnailCardTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.calls = []

    def tearDown(self):
        self._tmp.cleanup()

    async def _fetcher(self, url):
        self.calls.append(url)
        return png_bytes()

    async def test_generate_builds_card(self):
        card = Thumbnail(cache_dir=self.root, fetcher=self._fetcher)
        path = await card.generate(track(), channel="Some Channel", duration="3:20")
        self.assertIsNotNone(path)
        image_path = Path(path)
        self.assertTrue(image_path.exists())
        self.assertGreater(image_path.stat().st_size, 0)
        with Image.open(image_path) as image:
            self.assertEqual(image.size, (1280, 720))
        self.assertEqual(self.calls, ["https://img.youtube.com/vi/x/default.jpg"])

    async def test_generate_uses_cache(self):
        card = Thumbnail(cache_dir=self.root, fetcher=self._fetcher)
        first = await card.generate(track())
        second = await card.generate(track())
        self.assertEqual(first, second)
        self.assertEqual(len(self.calls), 1)

    async def test_generate_without_thumbnail_returns_none(self):
        card = Thumbnail(cache_dir=self.root, fetcher=self._fetcher)
        item = SimpleNamespace(video_id="vid1", title="Song", thumbnail="")
        self.assertIsNone(await card.generate(item))
        self.assertEqual(self.calls, [])

    async def test_generate_rejects_unsafe_video_id(self):
        card = Thumbnail(cache_dir=self.root, fetcher=self._fetcher)
        item = SimpleNamespace(
            video_id="../escape",
            title="Song",
            thumbnail="https://img.youtube.com/vi/x/default.jpg",
        )
        self.assertIsNone(await card.generate(item))
        self.assertEqual(self.calls, [])
        self.assertEqual(list(self.root.iterdir()), [])

    async def test_generate_fetch_error_returns_none(self):
        async def broken(url):
            raise RuntimeError("boom")

        card = Thumbnail(cache_dir=self.root, fetcher=broken)
        self.assertIsNone(await card.generate(track()))
        leftovers = list(self.root.iterdir())
        self.assertEqual(leftovers, [])

    async def test_generate_invalid_image_returns_none(self):
        async def garbage(url):
            return b"not-an-image"

        card = Thumbnail(cache_dir=self.root, fetcher=garbage)
        self.assertIsNone(await card.generate(track()))
        leftovers = list(self.root.iterdir())
        self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
