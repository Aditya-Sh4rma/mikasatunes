import unittest
from types import SimpleNamespace

from mikasa.core.userbot import AssistantPool

from config import Config, SessionSlot


class FakeClient:
    def __init__(self, state):
        self.slot = state.slot
        self.me = SimpleNamespace(username=f"assistant{state.slot}", id=state.slot)

    async def start(self):
        return None

    async def stop(self):
        return None


def make_pool(slots=(1, 2)):
    settings = Config.__new__(Config)
    settings.sessions = [SessionSlot(index, f"session-{index}") for index in slots]
    return AssistantPool(settings, client_factory=lambda state: FakeClient(state))


class ClaimTests(unittest.IsolatedAsyncioTestCase):
    async def test_claims_are_unique(self):
        pool = make_pool()
        await pool.start()
        first = await pool.claim(10)
        second = await pool.claim(20)
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertNotEqual(first.slot, second.slot)
        self.assertIsNone(await pool.claim(30))
        await pool.stop()

    async def test_claim_is_stable_per_chat(self):
        pool = make_pool()
        await pool.start()
        first = await pool.claim(10)
        again = await pool.claim(10)
        self.assertEqual(first.slot, again.slot)
        await pool.stop()

    async def test_release_frees_slot(self):
        pool = make_pool(slots=(1,))
        await pool.start()
        first = await pool.claim(10)
        self.assertIsNone(await pool.claim(20))
        await pool.release(10)
        reused = await pool.claim(20)
        self.assertEqual(reused.slot, first.slot)
        await pool.stop()

    async def test_stop_clears_claims(self):
        pool = make_pool()
        await pool.start()
        await pool.claim(10)
        await pool.stop()
        self.assertIsNone(pool.claimed_slot(10))

    async def test_unready_assistant_not_claimed(self):
        pool = make_pool(slots=(1, 2))
        await pool.start()
        pool.get(1).ready = False
        claimed = await pool.claim(10)
        self.assertEqual(claimed.slot, 2)
        await pool.stop()

    async def test_claim_specific_honors_preferred_slot(self):
        pool = make_pool(slots=(1, 2, 3))
        await pool.start()
        claimed = await pool.claim_specific(10, 3)
        self.assertEqual(claimed.slot, 3)
        self.assertEqual(pool.claimed_slot(10), 3)
        await pool.stop()

    async def test_claim_specific_falls_back_when_busy(self):
        pool = make_pool(slots=(1, 2))
        await pool.start()
        first = await pool.claim_specific(10, 1)
        self.assertEqual(first.slot, 1)
        second = await pool.claim_specific(20, 1)
        self.assertEqual(second.slot, 2)
        await pool.stop()

    async def test_claim_specific_falls_back_when_unknown(self):
        pool = make_pool(slots=(1, 2))
        await pool.start()
        claimed = await pool.claim_specific(10, 9)
        self.assertEqual(claimed.slot, 1)
        await pool.stop()

    async def test_slots_lists_configured(self):
        pool = make_pool(slots=(1, 3))
        self.assertEqual(pool.slots(), [1, 3])
