import tempfile
import unittest
from pathlib import Path

from mikasa.core.youtube import (
    YouTube,
    chained_api_download,
    devil_api_download,
    is_youtube,
    parse_duration,
    parse_video_id,
    safe_stem,
)
from mikasa.exceptions import DownloadError
from mikasa.helpers._dataclass import Track


class UrlParsingTests(unittest.TestCase):
    def test_watch_url(self):
        self.assertEqual(parse_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ"), "dQw4w9WgXcQ")

    def test_short_url(self):
        self.assertEqual(parse_video_id("https://youtu.be/dQw4w9WgXcQ"), "dQw4w9WgXcQ")

    def test_bare_id(self):
        self.assertEqual(parse_video_id("dQw4w9WgXcQ"), "dQw4w9WgXcQ")

    def test_shorts_and_embed(self):
        self.assertEqual(parse_video_id("https://youtube.com/shorts/dQw4w9WgXcQ"), "dQw4w9WgXcQ")
        self.assertEqual(parse_video_id("https://youtube.com/embed/dQw4w9WgXcQ"), "dQw4w9WgXcQ")

    def test_rejects_other_hosts(self):
        self.assertIsNone(parse_video_id("https://example.com/watch?v=dQw4w9WgXcQ"))
        self.assertFalse(is_youtube("https://vimeo.com/123"))

    def test_duration(self):
        self.assertEqual(parse_duration("3:20"), 200)
        self.assertEqual(parse_duration("1:02:03"), 3723)
        self.assertEqual(parse_duration(None), 0)
        self.assertEqual(parse_duration("LIVE"), 0)

    def test_safe_stem(self):
        stem = safe_stem("A/B: Song? *", "abc12345678")
        self.assertNotIn("/", stem)
        self.assertNotIn("?", stem)
        self.assertIn("abc12345678", stem)


def component(video_id, title, duration):
    return {
        "type": "video",
        "id": video_id,
        "title": title,
        "duration": duration,
        "thumbnails": [{"url": "http://thumb"}],
        "channel": {"name": "Channel"},
    }


class FakeSearcher:
    def __init__(self, result):
        self._result = result

    async def next(self):
        return self._result


class YouTubeSearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_maps_results(self):
        result = {"result": [component("dQw4w9WgXcQ", "Song", "3:20")]}
        youtube = YouTube(search_factory=lambda q, limit: FakeSearcher(result))
        tracks = await youtube.search("query", limit=5)
        self.assertEqual(len(tracks), 1)
        track = tracks[0]
        self.assertEqual(track.video_id, "dQw4w9WgXcQ")
        self.assertEqual(track.title, "Song")
        self.assertEqual(track.duration_seconds, 200)
        self.assertEqual(track.thumbnail, "http://thumb")
        self.assertEqual(track.channel, "Channel")

    async def test_search_skips_non_video_components(self):
        result = {"result": [{"type": "channel", "id": "x"}, component("dQw4w9WgXcQ", "Song", "1:00")]}
        youtube = YouTube(search_factory=lambda q, limit: FakeSearcher(result))
        tracks = await youtube.search("query")
        self.assertEqual([t.video_id for t in tracks], ["dQw4w9WgXcQ"])

    async def test_search_empty_query(self):
        youtube = YouTube()
        with self.assertRaises(ValueError):
            await youtube.search("   ")

    async def test_search_failure(self):
        class Broken:
            async def next(self):
                raise RuntimeError("nope")

        youtube = YouTube(search_factory=lambda q, limit: Broken())
        with self.assertRaises(DownloadError):
            await youtube.search("query")


class YouTubeDownloadTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    async def test_download_success(self):
        def downloader(url, template, audio_only, limit):
            path = self.root / "out.mp3"
            path.write_text("data")
            return path

        youtube = YouTube(downloader=downloader)
        track = Track(video_id="dQw4w9WgXcQ", title="Song", duration_seconds=1, url="https://youtu.be/dQw4w9WgXcQ")
        path = await youtube.download(track, self.root)
        self.assertTrue(path.exists())

    async def test_download_rejects_escape(self):
        outside = self.root.parent / f"escape_{id(self)}.mp3"

        def downloader(url, template, audio_only, limit):
            outside.write_text("data")
            return outside

        youtube = YouTube(downloader=downloader)
        track = Track(video_id="dQw4w9WgXcQ", title="Song", duration_seconds=1, url="u")
        with self.assertRaises(DownloadError):
            await youtube.download(track, self.root)
        outside.unlink(missing_ok=True)

    async def test_download_failure(self):
        def downloader(url, template, audio_only, limit):
            raise RuntimeError("boom")

        youtube = YouTube(downloader=downloader)
        track = Track(video_id="dQw4w9WgXcQ", title="Song", duration_seconds=1, url="u")
        with self.assertRaises(DownloadError):
            await youtube.download(track, self.root)


class FakeApiContent:
    def __init__(self, body):
        self._body = body

    async def iter_chunked(self, size):
        yield self._body


class FakeApiResponse:
    def __init__(self, status=200, body=b"data", headers=None):
        self.status = status
        self.content = FakeApiContent(body)
        self.headers = headers

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class FakeApiSession:
    def __init__(self, response=None, error=None):
        self._response = response if response is not None else FakeApiResponse()
        self._error = error
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": dict(params or {})})
        if self._error is not None:
            raise self._error
        return self._response


def api_factory(session):
    return lambda: session


class DevilApiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    async def test_success_writes_file(self):
        session = FakeApiSession(FakeApiResponse(200, b"audio-data"))
        destination = self.root / "song.mp3"
        path = await devil_api_download(
            "https://api.example", "key", "dQw4w9WgXcQ", "audio", destination,
            session_factory=api_factory(session),
        )
        self.assertEqual(path, destination)
        self.assertEqual(destination.read_bytes(), b"audio-data")
        self.assertTrue(session.calls[0]["url"].endswith("/download"))
        self.assertEqual(
            session.calls[0]["params"],
            {"url": "dQw4w9WgXcQ", "type": "audio", "api_key": "key"},
        )

    async def test_http_error_returns_none(self):
        session = FakeApiSession(FakeApiResponse(500, b"nope"))
        destination = self.root / "song.mp3"
        path = await devil_api_download(
            "https://api.example", "key", "dQw4w9WgXcQ", "audio", destination,
            session_factory=api_factory(session),
        )
        self.assertIsNone(path)
        self.assertFalse(destination.exists())

    async def test_empty_body_returns_none(self):
        session = FakeApiSession(FakeApiResponse(200, b""))
        destination = self.root / "song.mp3"
        path = await devil_api_download(
            "https://api.example", "key", "dQw4w9WgXcQ", "audio", destination,
            session_factory=api_factory(session),
        )
        self.assertIsNone(path)
        self.assertFalse(destination.exists())

    async def test_connection_error_returns_none(self):
        session = FakeApiSession(error=ConnectionError("down"))
        destination = self.root / "song.mp3"
        path = await devil_api_download(
            "https://api.example", "key", "dQw4w9WgXcQ", "audio", destination,
            session_factory=api_factory(session),
        )
        self.assertIsNone(path)
        self.assertFalse(destination.exists())

    async def test_json_response_rejected(self):
        session = FakeApiSession(
            FakeApiResponse(200, b'{"detail":"x"}', {"Content-Type": "application/json"})
        )
        destination = self.root / "song.mp3"
        path = await devil_api_download(
            "https://api.example", "key", "dQw4w9WgXcQ", "audio", destination,
            session_factory=api_factory(session),
        )
        self.assertIsNone(path)
        self.assertFalse(destination.exists())

    async def test_declared_oversize_rejected(self):
        session = FakeApiSession(
            FakeApiResponse(200, b"data", {"Content-Length": "999"})
        )
        destination = self.root / "song.mp3"
        path = await devil_api_download(
            "https://api.example", "key", "dQw4w9WgXcQ", "audio", destination,
            session_factory=api_factory(session),
            limit_bytes=10,
        )
        self.assertIsNone(path)
        self.assertFalse(destination.exists())

    async def test_streamed_oversize_aborted(self):
        session = FakeApiSession(FakeApiResponse(200, b"0123456789"))
        destination = self.root / "song.mp3"
        path = await devil_api_download(
            "https://api.example", "key", "dQw4w9WgXcQ", "audio", destination,
            session_factory=api_factory(session),
            limit_bytes=5,
        )
        self.assertIsNone(path)
        self.assertFalse(destination.exists())


class ChainedApiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    async def test_chain_falls_through_to_working_api(self):
        responses = [
            FakeApiResponse(404, b'{"detail":"not_cached"}'),
            FakeApiResponse(200, b"audio-data"),
        ]
        state = {"n": 0}

        def factory():
            response = responses[min(state["n"], len(responses) - 1)]
            state["n"] += 1
            return FakeApiSession(response)

        path = await chained_api_download(
            [("https://devil.example", "k1"), ("https://shruti.example", "")],
            "dQw4w9WgXcQ",
            "audio",
            self.root / "song.mp3",
            session_factory=factory,
        )
        self.assertIsNotNone(path)
        self.assertEqual(Path(path).read_bytes(), b"audio-data")
        self.assertEqual(state["n"], 2)

    async def test_chain_returns_none_when_all_fail(self):
        path = await chained_api_download(
            [("https://a.example", ""), ("https://b.example", "")],
            "dQw4w9WgXcQ",
            "audio",
            self.root / "song.mp3",
            session_factory=lambda: FakeApiSession(FakeApiResponse(503, b"down")),
        )
        self.assertIsNone(path)

    def test_shruti_only_config_builds_downloader(self):
        youtube = YouTube(shruti_url="https://shruti.example")
        self.assertIsNotNone(youtube._api_downloader)

    def test_no_api_config_builds_no_downloader(self):
        youtube = YouTube()
        self.assertIsNone(youtube._api_downloader)


class ApiFallbackTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _track(self):
        return Track(
            video_id="dQw4w9WgXcQ", title="Song", duration_seconds=1,
            url="https://youtu.be/dQw4w9WgXcQ",
        )

    async def test_api_success_skips_default_downloader(self):
        def fallback(url, template, audio_only, limit):
            raise AssertionError("fallback must not run")

        async def api(video_id, media_type, destination):
            self.assertEqual(video_id, "dQw4w9WgXcQ")
            self.assertEqual(media_type, "audio")
            path = Path(destination)
            path.write_text("api-data")
            return path

        youtube = YouTube(downloader=fallback, api_downloader=api)
        path = await youtube.download(self._track(), self.root)
        self.assertTrue(path.exists())
        self.assertEqual(path.read_text(), "api-data")

    async def test_api_none_falls_back(self):
        used = []

        def fallback(url, template, audio_only, limit):
            used.append(url)
            path = self.root / "out.mp3"
            path.write_text("data")
            return path

        async def api(video_id, media_type, destination):
            return None

        youtube = YouTube(downloader=fallback, api_downloader=api)
        path = await youtube.download(self._track(), self.root)
        self.assertTrue(path.exists())
        self.assertEqual(used, ["https://youtu.be/dQw4w9WgXcQ"])

    async def test_api_oversize_falls_back(self):
        used = []

        def fallback(url, template, audio_only, limit):
            used.append(url)
            path = self.root / "out.mp3"
            path.write_text("data")
            return path

        async def api(video_id, media_type, destination):
            destination = Path(destination)
            destination.write_bytes(b"0123456789")
            return destination

        youtube = YouTube(downloader=fallback, api_downloader=api)
        path = await youtube.download(
            self._track(), self.root, limit_bytes=5
        )
        self.assertTrue(path.exists())
        self.assertEqual(used, ["https://youtu.be/dQw4w9WgXcQ"])
        leftovers = [p for p in self.root.iterdir() if p.suffix == ".mp3" and p.stat().st_size > 5]
        self.assertEqual(leftovers, [])

    async def test_api_error_falls_back(self):
        def fallback(url, template, audio_only, limit):
            path = self.root / "out.mp3"
            path.write_text("data")
            return path

        async def api(video_id, media_type, destination):
            raise RuntimeError("boom")

        youtube = YouTube(downloader=fallback, api_downloader=api)
        path = await youtube.download(self._track(), self.root)
        self.assertTrue(path.exists())
