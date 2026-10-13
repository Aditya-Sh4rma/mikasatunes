import unittest

from mikasa.helpers._dataclass import Track
from mikasa.helpers._queue import AddResult, Queue


def track(identifier: str) -> Track:
    return Track(video_id=identifier, title=identifier, duration_seconds=1, url="u")


class QueueTests(unittest.IsolatedAsyncioTestCase):
    async def test_fifo_order(self):
        queue = Queue()
        await queue.add(1, track("a"))
        await queue.add(1, track("b"))
        self.assertEqual((await queue.pop_next(1)).id, "a")
        self.assertEqual((await queue.pop_next(1)).id, "b")
        self.assertIsNone(await queue.pop_next(1))

    async def test_duplicate_protection(self):
        queue = Queue()
        self.assertEqual(await queue.add(1, track("a")), AddResult.ADDED)
        self.assertEqual(await queue.add(1, track("a")), AddResult.DUPLICATE)
        self.assertEqual(await queue.add(1, track("a"), allow_duplicate=True), AddResult.ADDED)

    async def test_limit(self):
        queue = Queue(limit=1)
        self.assertEqual(await queue.add(1, track("a")), AddResult.ADDED)
        self.assertEqual(await queue.add(1, track("b")), AddResult.FULL)

    async def test_isolated_per_chat(self):
        queue = Queue()
        await queue.add(1, track("a"))
        await queue.add(2, track("b"))
        self.assertEqual((await queue.pop_next(1)).id, "a")
        self.assertEqual((await queue.pop_next(2)).id, "b")

    async def test_remove_clear_contains(self):
        queue = Queue()
        await queue.add(1, track("a"))
        await queue.add(1, track("b"))
        self.assertTrue(await queue.contains(1, "a"))
        self.assertTrue(await queue.remove(1, "a"))
        self.assertFalse(await queue.remove(1, "a"))
        self.assertEqual(await queue.size(1), 1)
        self.assertEqual(await queue.clear(1), 1)
        self.assertEqual(await queue.items(1), [])
