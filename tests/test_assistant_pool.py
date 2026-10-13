import unittest
from types import SimpleNamespace

from mikasa.core.userbot import AssistantPool

from config import Config, SessionSlot


class FakeClient:
    def __init__(self, state):
        self.slot = state.slot
        self.started = False
        self.me = SimpleNamespace(username=f"assistant{state.slot}", id=state.slot)

    async def start(self):
        self.started = True

    async def stop(self):
        self.started = False


def make_settings(slots=(1, 2, 3)):
    settings = Config.__new__(Config)
    settings.sessions = [SessionSlot(index, f"session-{index}") for index in slots]
    return settings


class AssistantPoolTests(unittest.IsolatedAsyncioTestCase):
    def build(self, slots=(1, 2, 3), fail_on=None):
        settings = make_settings(slots)
        created = []

        def factory(state):
            if fail_on is not None and state.slot == fail_on:
                raise RuntimeError("boom")
            client = FakeClient(state)
            created.append(client)
            return client

        return AssistantPool(settings, client_factory=factory), created

    async def test_start_marks_ready(self):
        pool, created = self.build()
        await pool.start()
        self.assertTrue(pool.started)
        self.assertEqual([state.label for state in pool.ready()], ["assistant-1", "assistant-2", "assistant-3"])
        self.assertTrue(all(client.started for client in created))
        await pool.stop()
        self.assertFalse(pool.started)
        self.assertEqual(pool.ready(), [])
        self.assertTrue(all(not client.started for client in created))

    async def test_double_start_rejected(self):
        pool, _ = self.build()
        await pool.start()
        with self.assertRaises(RuntimeError):
            await pool.start()
        await pool.stop()

    async def test_partial_failure_rolls_back(self):
        pool, created = self.build(fail_on=3)
        with self.assertRaises(RuntimeError):
            await pool.start()
        self.assertFalse(pool.started)
        self.assertEqual(pool.ready(), [])
        self.assertTrue(all(not client.started for client in created))

    async def test_reconnect(self):
        pool, _ = self.build()
        await pool.start()
        self.assertTrue(await pool.reconnect(2))
        self.assertTrue(pool.get(2).ready)
        self.assertFalse(await pool.reconnect(9))
        await pool.stop()

    async def test_status_hides_secret(self):
        pool, _ = self.build()
        await pool.start()
        rows = pool.status()
        for row in rows:
            self.assertNotIn("session", row)
        self.assertNotIn("session-1", str(rows))
        await pool.stop()
