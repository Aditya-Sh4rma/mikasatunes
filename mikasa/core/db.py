# Copyright (c) 2026 Aditya-Sh4rma
# Licensed under the MIT License.
# This file is part of MikasaMusic


import random
from typing import Optional

from pymongo import AsyncMongoClient

from ..tools.models import ChatSettings


class MongoDB:
    def __init__(self, url: str, name: str = "mikasa", client: Optional[AsyncMongoClient] = None) -> None:
        self._url = url
        self._name = name
        self._client = client
        self._owns_client = client is None
        self._db = None

    @property
    def connected(self) -> bool:
        return self._db is not None

    async def connect(self) -> None:
        if self._db is not None:
            return
        if self._client is None:
            self._client = AsyncMongoClient(self._url)
        self._db = self._client[self._name]

    async def close(self) -> None:
        client = self._client
        self._db = None
        self._client = None
        if client is not None and self._owns_client:
            await client.close()

    def _collection(self, name: str):
        if self._db is None:
            raise RuntimeError("database not connected")
        return self._db[name]

    async def chat_settings(self, chat_id: int) -> ChatSettings:
        document = await self._collection("chats").find_one({"_id": chat_id})
        return ChatSettings.from_document(document or {})

    async def save_chat(self, chat_id: int, settings: ChatSettings) -> None:
        await self._collection("chats").update_one(
            {"_id": chat_id},
            {"$set": settings.to_document()},
            upsert=True,
        )

    async def assistant_slot(self, chat_id: int, slots: list[int]) -> Optional[int]:
        if not slots:
            return None
        settings = await self.chat_settings(chat_id)
        if settings.assistant in slots:
            return settings.assistant
        slot = random.choice(slots)
        settings.assistant = slot
        await self.save_chat(chat_id, settings)
        return slot

    async def set_assistant_slot(self, chat_id: int, slot: int) -> None:
        settings = await self.chat_settings(chat_id)
        settings.assistant = slot
        await self.save_chat(chat_id, settings)

    async def add_chat(self, chat_id: int) -> None:
        await self._collection("served_chats").update_one(
            {"_id": chat_id}, {"$set": {"_id": chat_id}}, upsert=True
        )

    async def remove_chat(self, chat_id: int) -> None:
        await self._collection("served_chats").delete_one({"_id": chat_id})

    async def served_chats(self) -> list[int]:
        cursor = self._collection("served_chats").find({})
        return sorted({int(document["_id"]) async for document in cursor})

    async def add_user(self, user_id: int) -> None:
        await self._collection("served_users").update_one(
            {"_id": user_id}, {"$set": {"_id": user_id}}, upsert=True
        )

    async def remove_user(self, user_id: int) -> None:
        await self._collection("served_users").delete_one({"_id": user_id})

    async def served_users(self) -> list[int]:
        cursor = self._collection("served_users").find({})
        return sorted({int(document["_id"]) async for document in cursor})

    async def _auth_ids(self, chat_id: int) -> set[int]:
        document = await self._collection("auth").find_one({"_id": chat_id})
        return {int(user_id) for user_id in (document or {}).get("user_ids", [])}

    async def is_auth(self, chat_id: int, user_id: int) -> bool:
        return user_id in await self._auth_ids(chat_id)

    async def chat_auth_users(self, chat_id: int) -> list[int]:
        return sorted(await self._auth_ids(chat_id))

    async def add_auth(self, chat_id: int, user_id: int) -> None:
        users = await self._auth_ids(chat_id)
        users.add(user_id)
        await self._collection("auth").update_one(
            {"_id": chat_id}, {"$set": {"user_ids": sorted(users)}}, upsert=True
        )

    async def remove_auth(self, chat_id: int, user_id: int) -> None:
        users = await self._auth_ids(chat_id)
        users.discard(user_id)
        await self._collection("auth").update_one(
            {"_id": chat_id}, {"$set": {"user_ids": sorted(users)}}, upsert=True
        )

    async def _blocked_ids(self, collection: str) -> set[int]:
        cursor = self._collection(collection).find({})
        return {int(document["_id"]) async for document in cursor}

    async def add_blocked_chat(self, chat_id: int) -> None:
        await self._collection("blocked_chats").update_one(
            {"_id": chat_id}, {"$set": {"_id": chat_id}}, upsert=True
        )

    async def remove_blocked_chat(self, chat_id: int) -> None:
        await self._collection("blocked_chats").delete_one({"_id": chat_id})

    async def blocked_chats(self) -> set[int]:
        return await self._blocked_ids("blocked_chats")

    async def add_blocked_user(self, user_id: int) -> None:
        await self._collection("blocked_users").update_one(
            {"_id": user_id}, {"$set": {"_id": user_id}}, upsert=True
        )

    async def remove_blocked_user(self, user_id: int) -> None:
        await self._collection("blocked_users").delete_one({"_id": user_id})

    async def blocked_users(self) -> set[int]:
        return await self._blocked_ids("blocked_users")

    async def logger_enabled(self) -> bool:
        document = await self._collection("meta").find_one({"_id": "logger"})
        return bool((document or {}).get("status", False))

    async def set_logger(self, status: bool) -> None:
        await self._collection("meta").update_one(
            {"_id": "logger"}, {"$set": {"status": status}}, upsert=True
        )

    async def sudo_users(self) -> set[int]:
        cursor = self._collection("sudo").find({})
        return {int(document["_id"]) async for document in cursor}

    async def add_sudo(self, user_id: int) -> None:
        await self._collection("sudo").update_one({"_id": user_id}, {"$set": {"_id": user_id}}, upsert=True)

    async def remove_sudo(self, user_id: int) -> None:
        await self._collection("sudo").delete_one({"_id": user_id})
