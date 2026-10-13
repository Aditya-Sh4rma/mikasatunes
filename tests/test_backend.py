import unittest

from mikasa.core import calls as backend_module
from mikasa.core.calls import PyTgCallsBackend


class FakeExecutor:
    def __init__(self):
        self.shutdown_calls = []

    def shutdown(self, wait=True, cancel_futures=False):
        self.shutdown_calls.append((wait, cancel_futures))


class FakeCall:
    def __init__(self, chats=()):
        self._chats = list(chats)
        self.left = []
        self.executor = FakeExecutor()

    @property
    async def calls(self):
        return {chat: None for chat in self._chats}

    async def leave_call(self, chat_id, close=False):
        self.left.append(chat_id)


class FakeState:
    slot = 1
    client = None


def make_backend(chats=()):
    backend = PyTgCallsBackend(FakeState())
    call = FakeCall(chats)
    backend._call = call
    backend._started = True
    return backend, call


class BackendCloseTests(unittest.IsolatedAsyncioTestCase):
    async def test_close_leaves_active_calls(self):
        backend, call = make_backend([-100, -200])
        await backend.close()
        self.assertEqual(sorted(call.left), [-200, -100])
        self.assertIsNone(backend.call)
        self.assertEqual(call.executor.shutdown_calls, [])

    async def test_close_is_idempotent(self):
        backend, call = make_backend([-100])
        await backend.close()
        await backend.close()
        self.assertEqual(call.left, [-100])

    async def test_close_without_call_is_safe(self):
        backend = PyTgCallsBackend(FakeState())
        await backend.close()
        self.assertIsNone(backend.call)

    async def test_close_survives_leave_errors(self):
        backend, call = make_backend([-100, -200])

        async def boom(chat_id, close=False):
            raise RuntimeError("nope")

        call.leave_call = boom
        await backend.close()
        self.assertIsNone(backend.call)


class FakeTgCalls:
    instances = []

    def __init__(self, client):
        self.client = client
        self.left = []
        FakeTgCalls.instances.append(self)

    def on_update(self):
        def decorator(func):
            return func

        return decorator

    async def start(self):
        return None

    @property
    async def calls(self):
        return {-100: None}

    async def leave_call(self, chat_id, close=False):
        self.left.append(chat_id)


class FakeStateWithClient:
    slot = 1
    client = object()


class BackendPlayTests(unittest.IsolatedAsyncioTestCase):
    async def test_play_does_not_auto_start_call(self):
        played = []

        class FakePlayCalls(FakeTgCalls):
            async def play(self, chat_id, stream, config=None):
                played.append((chat_id, config))

        old = backend_module.PyTgCalls
        backend_module.PyTgCalls = FakePlayCalls
        try:
            backend = PyTgCallsBackend(FakeStateWithClient())
            backend._started = True
            backend._call = FakePlayCalls(object())
            await backend.play(-100, "/tmp/x.mp3")
            self.assertEqual(len(played), 1)
            self.assertFalse(played[0][1].auto_start)
        finally:
            backend_module.PyTgCalls = old


class BackendStartTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._real = backend_module.PyTgCalls
        backend_module.PyTgCalls = FakeTgCalls
        FakeTgCalls.instances = []
        self.addCleanup(self._restore)

    def _restore(self):
        backend_module.PyTgCalls = self._real

    async def test_start_leaves_stale_calls(self):
        backend = PyTgCallsBackend(FakeStateWithClient())
        await backend.start()
        self.assertEqual(len(FakeTgCalls.instances), 1)
        self.assertEqual(FakeTgCalls.instances[0].left, [-100])

    async def test_start_requires_connected_assistant(self):
        backend = PyTgCallsBackend(FakeState())
        with self.assertRaises(RuntimeError):
            await backend.start()
