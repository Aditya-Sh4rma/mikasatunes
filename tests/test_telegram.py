import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from mikasa.exceptions import UnsupportedMedia
from mikasa.core.telegram import Telegram, extension_of, is_direct_url, is_supported_url


class UrlTests(unittest.TestCase):
    def test_direct(self):
        self.assertTrue(is_direct_url("https://host/a.mp3"))
        self.assertFalse(is_direct_url("https://youtu.be/dQw4w9WgXcQ"))
        self.assertFalse(is_direct_url("ftp://host/a.mp3"))

    def test_supported(self):
        self.assertTrue(is_supported_url("https://host/a.mp3"))
        self.assertTrue(is_supported_url("https://youtu.be/dQw4w9WgXcQ"))
        self.assertFalse(is_supported_url("https://host/page.html"))
        self.assertFalse(is_supported_url("notaurl"))

    def test_extension(self):
        self.assertEqual(extension_of("https://host/a.MP3?x=1"), ".mp3")


class IntakeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    async def test_from_message_audio(self):
        async def download_media(message, file_name=None):
            Path(file_name).write_text("data")
            return file_name

        client = SimpleNamespace(download_media=download_media)
        audio = SimpleNamespace(file_id="f1", file_size=10, title="Title", file_name="a.mp3", duration=120)
        message = SimpleNamespace(
            audio=audio,
            video=None,
            voice=None,
            document=None,
            id=7,
            from_user=SimpleNamespace(id=99),
        )
        media = await Telegram().from_message(message, client, self.root)
        self.assertEqual(media.file_id, "f1")
        self.assertEqual(media.duration_seconds, 120)
        self.assertEqual(media.requested_by, "99")
        self.assertTrue(Path(media.file_path).exists())

    async def test_from_message_unsupported(self):
        client = SimpleNamespace(download_media=None)
        message = SimpleNamespace(audio=None, video=None, voice=None, document=None, id=1, from_user=None)
        with self.assertRaises(UnsupportedMedia):
            await Telegram().from_message(message, client, self.root)

    async def test_from_message_rejects_oversize(self):
        client = SimpleNamespace(download_media=None)
        audio = SimpleNamespace(file_id="f1", file_size=1000, title="T", file_name="a.mp3", duration=1)
        message = SimpleNamespace(audio=audio, video=None, voice=None, document=None, id=1, from_user=None)
        with self.assertRaises(UnsupportedMedia):
            await Telegram(max_bytes=10).from_message(message, client, self.root)

    async def test_from_url(self):
        async def downloader(url, destination):
            Path(destination).write_text("data")
            return destination

        intake = Telegram(downloader=downloader)
        media = await intake.from_url("https://host/song.mp3", self.root, title="Song")
        self.assertEqual(media.title, "Song")
        self.assertTrue(Path(media.file_path).exists())

    async def test_from_url_unsupported(self):
        async def downloader(url, destination):
            return destination

        intake = Telegram(downloader=downloader)
        with self.assertRaises(UnsupportedMedia):
            await intake.from_url("https://host/page.html", self.root)
