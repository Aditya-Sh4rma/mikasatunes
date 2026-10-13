import unittest

from mikasa.core.mongo import MongoDB
from mikasa.helpers._dataclass import ChatSettings


class FakeCursor:
    def __init__(self, documents):
        self._documents = list(documents)
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._documents):
            raise StopAsyncIteration
        document = self._documents[self._index]
        self._index += 1
        return document


class FakeCollection:
    def __init__(self):
        self.documents = {}

    async def find_one(self, query):
        return self.documents.get(query["_id"])

    async def update_one(self, query, update, upsert=False):
        document = self.documents.setdefault(query["_id"], {})
        document.update(update.get("$set", {}))

    async def delete_one(self, query):
        self.documents.pop(query["_id"], None)

    def find(self, query):
        return FakeCursor(list(self.documents.values()))


class FakeDatabase:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, FakeCollection())


class FakeClient:
    def __init__(self):
        self.databases = {}
        self.closed = False

    def __getitem__(self, name):
        return self.databases.setdefault(name, FakeDatabase())

    async def close(self):
        self.closed = True


def make_database(client):
    return MongoDB("mongodb://unused", client=client)


class DatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_defaults_without_document(self):
        database = make_database(FakeClient())
        await database.connect()
        settings = await database.chat_settings(10)
        self.assertEqual(settings, ChatSettings())

    async def test_save_and_load(self):
        database = make_database(FakeClient())
        await database.connect()
        await database.save_chat(10, ChatSettings(language="tr", loop=2, paused=True, assistant=3))
        settings = await database.chat_settings(10)
        self.assertEqual(settings.language, "tr")
        self.assertEqual(settings.loop, 2)
        self.assertTrue(settings.paused)
        self.assertEqual(settings.assistant, 3)

    async def test_sudo_lifecycle(self):
        database = make_database(FakeClient())
        await database.connect()
        await database.add_sudo(5)
        await database.add_sudo(7)
        self.assertEqual(await database.sudo_users(), {5, 7})
        await database.remove_sudo(5)
        self.assertEqual(await database.sudo_users(), {7})

    async def test_close_safe_when_never_connected(self):
        database = MongoDB("mongodb://unused")
        await database.close()
        self.assertFalse(database.connected)

    async def test_operations_require_connection(self):
        database = MongoDB("mongodb://unused")
        with self.assertRaises(RuntimeError):
            await database.chat_settings(1)

    async def test_assistant_slot_assigns_and_persists(self):
        database = make_database(FakeClient())
        await database.connect()
        self.assertEqual(await database.assistant_slot(10, [3]), 3)
        self.assertEqual(await database.assistant_slot(10, [1, 2, 3]), 3)

    async def test_assistant_slot_reassigns_out_of_range(self):
        database = make_database(FakeClient())
        await database.connect()
        await database.set_assistant_slot(10, 5)
        self.assertEqual(await database.assistant_slot(10, [2]), 2)

    async def test_assistant_slot_without_slots(self):
        database = make_database(FakeClient())
        await database.connect()
        self.assertIsNone(await database.assistant_slot(10, []))

    async def test_served_chats_lifecycle(self):
        database = make_database(FakeClient())
        await database.connect()
        await database.add_chat(-100)
        await database.add_chat(-200)
        self.assertEqual(await database.served_chats(), [-200, -100])
        await database.remove_chat(-100)
        self.assertEqual(await database.served_chats(), [-200])

    async def test_served_users_lifecycle(self):
        database = make_database(FakeClient())
        await database.connect()
        await database.add_user(5)
        self.assertEqual(await database.served_users(), [5])
        await database.remove_user(5)
        self.assertEqual(await database.served_users(), [])
