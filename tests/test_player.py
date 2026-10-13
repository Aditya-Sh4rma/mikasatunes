import tempfile
import unittest
from pathlib import Path

from mikasa.core.calls import PlaybackBackend, Player
from mikasa.helpers._dataclass import Media
from mikasa.helpers._queue import AddResult, Queue


class FakeState:
    def __init__(self, slot: int) -> None:
        self.slot = slot
        self.ready = True


class FakePool:
    def __init__(self, slots=(1, 2)) -> None:
        self._states = {slot: FakeState(slot) for slot in slots}
        self._claims = {}

    def get(self, slot):
        return self._states.get(slot)

    def claimed_slot(self, chat_id):
        return self._claims.get(chat_id)

    def slots(self):
        return list(self._states)

    async def claim(self, chat_id):
        return await self.claim_specific(chat_id, None)

    async def claim_specific(self, chat_id, slot):
        claimed = self._claims.get(chat_id)
        if claimed is not None:
            return self._states[claimed]
        if slot is not None:
            state = self._states.get(slot)
            if state is not None and state.ready and slot not in set(self._claims.values()):
                self._claims[chat_id] = slot
                return state
        used = set(self._claims.values())
        for slot, state in self._states.items():
            if state.ready and slot not in used:
                self._claims[chat_id] = slot
                return state
        return None

    async def release(self, chat_id):
        self._claims.pop(chat_id, None)


class FakeBackend(PlaybackBackend):
    def __init__(self) -> None:
        self.played = []
        self.stopped = []
        self.left = []
        self.closed = 0

    async def play(self, chat_id, file_path, is_video=False):
        self.played.append((chat_id, file_path, is_video))

    async def stop(self, chat_id):
        self.stopped.append(chat_id)

    async def leave(self, chat_id):
        self.left.append(chat_id)

    async def close(self):
        self.closed += 1

    async def pause(self, chat_id):
        return True

    async def resume(self, chat_id):
        return True


def media(identifier: str, path: Path) -> Media:
    return Media(file_id=identifier, title=identifier, duration_seconds=1, file_path=str(path))


class PlayerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.pool = FakePool()
        self.queue = Queue(limit=5)
        self.backend = FakeBackend()
        self.player = Player(
            self.pool,
            self.queue,
            lambda state: self.backend,
            resolver=self._resolve,
            temp_root=self.root,
        )

    def tearDown(self):
        self._tmp.cleanup()

    async def _resolve(self, chat_id, item, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{item.id}.mp3"
        path.write_text("data")
        return path

    async def test_enqueue_deduplicates(self):
        item = media("a", self.root / "a.mp3")
        self.assertEqual(await self.player.enqueue(1, item), AddResult.ADDED)
        self.assertEqual(await self.player.enqueue(1, item), AddResult.DUPLICATE)

    async def test_start_plays_and_claims(self):
        item = media("a", self.root / "a.mp3")
        await self.player.enqueue(10, item)
        self.assertTrue(await self.player.start(10))
        self.assertEqual(self.pool.claimed_slot(10), 1)
        self.assertEqual(len(self.backend.played), 1)
        self.assertIs(await self.player.current(10), item)
        self.assertFalse(await self.player.start(10))

    async def test_advance_plays_next_and_removes_owned_file(self):
        await self.player.enqueue(10, media("a", self.root / "a.mp3"))
        await self.player.enqueue(10, media("b", self.root / "b.mp3"))
        await self.player.start(10)
        first = self.root / "10" / "a.mp3"
        self.assertTrue(first.exists())
        self.assertTrue(await self.player.advance(10))
        self.assertFalse(first.exists())
        self.assertEqual(len(self.backend.played), 2)
        self.assertEqual((await self.player.current(10)).id, "b")

    async def test_skip_stops_and_plays_next(self):
        await self.player.enqueue(10, media("a", self.root / "a.mp3"))
        await self.player.enqueue(10, media("b", self.root / "b.mp3"))
        await self.player.start(10)
        self.assertTrue(await self.player.skip(10))
        self.assertIn(10, self.backend.stopped)
        self.assertEqual(len(self.backend.played), 2)

    async def test_stop_releases_and_cleans(self):
        await self.player.enqueue(10, media("a", self.root / "a.mp3"))
        await self.player.enqueue(10, media("b", self.root / "b.mp3"))
        await self.player.start(10)
        self.assertTrue(await self.player.stop(10))
        self.assertIsNone(self.pool.claimed_slot(10))
        self.assertIn(10, self.backend.left)
        self.assertEqual(await self.queue.size(10), 0)
        self.assertFalse((self.root / "10" / "a.mp3").exists())

    async def test_play_failure_advances_to_next(self):
        flaky = FakeBackend()
        attempts = {"n": 0}

        async def play(chat_id, file_path, is_video=False):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise RuntimeError("boom")
            flaky.played.append((chat_id, file_path, is_video))

        flaky.play = play
        player = Player(
            FakePool(),
            Queue(limit=5),
            lambda state: flaky,
            resolver=self._resolve,
            temp_root=self.root,
        )
        await player.enqueue(10, media("a", self.root / "a.mp3"))
        await player.enqueue(10, media("b", self.root / "b.mp3"))
        self.assertTrue(await player.start(10))
        self.assertEqual(len(flaky.played), 1)
        self.assertEqual((await player.current(10)).id, "b")

    async def test_skip_last_track_leaves_voice_chat(self):
        await self.player.enqueue(10, media("a", self.root / "a.mp3"))
        await self.player.start(10)
        self.assertFalse(await self.player.skip(10))
        self.assertIn(10, self.backend.left)
        self.assertIsNone(self.pool.claimed_slot(10))

    async def test_advance_empty_queue_leaves_voice_chat(self):
        await self.player.enqueue(10, media("a", self.root / "a.mp3"))
        await self.player.start(10)
        self.assertFalse(await self.player.advance(10))
        self.assertIn(10, self.backend.left)

    async def test_stop_keeps_unowned_files(self):
        keep = self.root / "keep.mp3"
        keep.write_text("data")
        await self.player.enqueue(10, media("k", keep))
        await self.player.start(10)
        await self.player.stop(10)
        self.assertTrue(keep.exists())

    async def test_close_stops_playback_and_closes_backends(self):
        await self.player.enqueue(10, media("a", self.root / "a.mp3"))
        await self.player.start(10)
        owned = self.root / "10" / "a.mp3"
        self.assertTrue(owned.exists())
        await self.player.close()
        self.assertIn(10, self.backend.left)
        self.assertEqual(self.backend.closed, 1)
        self.assertFalse(owned.exists())
        self.assertIsNone(self.pool.claimed_slot(10))

    async def test_close_is_idempotent(self):
        await self.player.enqueue(10, media("a", self.root / "a.mp3"))
        await self.player.start(10)
        await self.player.close()
        await self.player.close()
        self.assertEqual(self.backend.closed, 1)

    async def test_stored_slot_preferred_and_persisted(self):
        stored = {}

        class FakeDatabase:
            async def assistant_slot(self, chat_id, slots):
                return stored.get(chat_id, slots[-1])

            async def set_assistant_slot(self, chat_id, slot):
                stored[chat_id] = slot

        player = Player(
            FakePool(),
            Queue(limit=5),
            lambda state: self.backend,
            resolver=self._resolve,
            temp_root=self.root,
            database=FakeDatabase(),
        )
        await player.enqueue(10, media("a", self.root / "a.mp3"))
        self.assertTrue(await player.start(10))
        self.assertEqual(player._pool.claimed_slot(10), 2)
        self.assertEqual(stored[10], 2)

    async def test_close_continues_when_a_backend_fails(self):
        bad = FakeBackend()
        good = FakeBackend()

        async def bad_close():
            raise RuntimeError("boom")

        bad.close = bad_close
        backends = {1: bad, 2: good}
        player = Player(
            FakePool(),
            Queue(limit=5),
            lambda state: backends[state.slot],
            resolver=self._resolve,
            temp_root=self.root,
        )
        await player.enqueue(10, media("a", self.root / "a.mp3"))
        await player.start(10)
        await player.enqueue(20, media("b", self.root / "b.mp3"))
        await player.start(20)
        await player.close()
        self.assertEqual(good.closed, 1)


class NoActiveCallTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.pool = FakePool()

    async def _resolve(self, chat_id, item, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{item.id}.mp3"
        path.write_text("data")
        return path

    def _media(self, identifier):
        return media(identifier, self.root / f"{identifier}.mp3")

    def _player(self, backend):
        return Player(
            self.pool,
            Queue(limit=5),
            lambda state: backend,
            resolver=self._resolve,
            temp_root=self.root,
        )

    async def test_start_propagates_no_active_call_and_releases(self):
        from pytgcalls.exceptions import NoActiveGroupCall

        backend = FakeBackend()

        async def boom(chat_id, file_path, is_video=False):
            raise NoActiveGroupCall()

        backend.play = boom
        player = self._player(backend)
        await player.enqueue(10, self._media("a"))
        with self.assertRaises(NoActiveGroupCall):
            await player.start(10)
        self.assertIsNone(self.pool.claimed_slot(10))
        self.assertIsNone(await player.current(10))

    async def test_advance_converts_no_active_call_to_false(self):
        from pytgcalls.exceptions import NoActiveGroupCall

        backend = FakeBackend()
        player = self._player(backend)
        await player.enqueue(10, self._media("a"))
        self.assertTrue(await player.start(10))

        async def boom(chat_id, file_path, is_video=False):
            raise NoActiveGroupCall()

        backend.play = boom
        await player.enqueue(10, self._media("b"))
        self.assertFalse(await player.advance(10))
        self.assertIsNone(self.pool.claimed_slot(10))

    async def test_skip_converts_no_active_call_to_false(self):
        from pytgcalls.exceptions import NoActiveGroupCall

        backend = FakeBackend()
        player = self._player(backend)
        await player.enqueue(10, self._media("a"))
        self.assertTrue(await player.start(10))

        async def boom(chat_id, file_path, is_video=False):
            raise NoActiveGroupCall()

        backend.play = boom
        await player.enqueue(10, self._media("b"))
        self.assertFalse(await player.skip(10))
        self.assertIsNone(self.pool.claimed_slot(10))
        self.assertIsNone(await player.current(10))
