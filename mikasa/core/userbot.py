# Copyright (c) 2026 Aditya-Sh4rma
# Licensed under the MIT License.
# This file is part of MikasaMusic


import asyncio
from typing import Callable, Optional

import pyrogram

from ..logging_config import get_logger
from config import Config, SessionSlot


class AssistantState:
    def __init__(self, slot: SessionSlot) -> None:
        self.slot = slot.slot
        self.label = slot.label
        self.session = slot.value
        self.client = None
        self.ready = False
        self.error = None
        self.username = None
        self.user_id = None

    def describe(self) -> dict:
        return {
            "slot": self.slot,
            "label": self.label,
            "ready": self.ready,
            "error": self.error,
            "username": self.username,
        }


ClientFactory = Callable[[AssistantState], pyrogram.Client]


class AssistantPool:
    def __init__(self, settings: Config, client_factory: Optional[ClientFactory] = None) -> None:
        self._settings = settings
        self._factory = client_factory or self._build_client
        self._states = [AssistantState(slot) for slot in settings.sessions]
        self._started = False
        self._lock = asyncio.Lock()
        self._claim_lock = asyncio.Lock()
        self._claims: dict[int, int] = {}
        self.log = get_logger("mikasa.assistants")

    def _build_client(self, state: AssistantState) -> pyrogram.Client:
        return pyrogram.Client(
            name=f"mikasa_{state.label}",
            api_id=self._settings.api_id,
            api_hash=self._settings.api_hash,
            session_string=state.session,
        )

    @property
    def started(self) -> bool:
        return self._started

    def states(self) -> list[AssistantState]:
        return list(self._states)

    def get(self, slot: int) -> Optional[AssistantState]:
        for state in self._states:
            if state.slot == slot:
                return state
        return None

    def ready(self) -> list[AssistantState]:
        return [state for state in self._states if state.ready]

    def status(self) -> list[dict]:
        return [state.describe() for state in self._states]

    def claimed_slot(self, chat_id: int) -> Optional[int]:
        return self._claims.get(chat_id)

    def slots(self) -> list[int]:
        return [state.slot for state in self._states]

    async def claim(self, chat_id: int) -> Optional[AssistantState]:
        return await self.claim_specific(chat_id, None)

    async def claim_specific(self, chat_id: int, slot: Optional[int]) -> Optional[AssistantState]:
        async with self._claim_lock:
            current = self._claims.get(chat_id)
            if current is not None:
                state = self.get(current)
                if state is not None and state.ready:
                    return state
                self._claims.pop(chat_id, None)
            if slot is not None:
                state = self.get(slot)
                if (
                    state is not None
                    and state.ready
                    and slot not in set(self._claims.values())
                ):
                    self._claims[chat_id] = slot
                    return state
            used = set(self._claims.values())
            for state in self._states:
                if state.ready and state.slot not in used:
                    self._claims[chat_id] = state.slot
                    return state
            return None

    async def release(self, chat_id: int) -> None:
        async with self._claim_lock:
            self._claims.pop(chat_id, None)

    def _drop_claims(self, slot: int) -> None:
        for chat_id, claimed in list(self._claims.items()):
            if claimed == slot:
                self._claims.pop(chat_id, None)

    async def start(self) -> None:
        async with self._lock:
            if self._started:
                raise RuntimeError("assistant pool already started")
            self._started = True
        started: list[AssistantState] = []
        try:
            for state in self._states:
                await self._start_one(state)
                started.append(state)
        except Exception:
            for state in reversed(started):
                await self._stop_one(state)
            async with self._lock:
                self._started = False
            raise

    async def _start_one(self, state: AssistantState) -> None:
        client = self._factory(state)
        try:
            await client.start()
            me = client.me
        except Exception as exc:
            await self._safe_stop(client)
            state.ready = False
            state.error = type(exc).__name__
            raise
        state.client = client
        state.ready = True
        state.error = None
        state.username = me.username
        state.user_id = me.id
        self.log.info("assistant %s online as %s", state.label, me.username or me.id)

    async def _stop_one(self, state: AssistantState) -> None:
        client = state.client
        state.client = None
        state.ready = False
        state.username = None
        state.user_id = None
        async with self._claim_lock:
            self._drop_claims(state.slot)
        if client is not None:
            await self._safe_stop(client)

    async def _safe_stop(self, client: pyrogram.Client) -> None:
        try:
            await client.stop()
        except Exception as exc:
            self.log.warning("assistant stop error: %s", type(exc).__name__)

    async def stop(self) -> None:
        for state in self._states:
            await self._stop_one(state)
        async with self._claim_lock:
            self._claims.clear()
        async with self._lock:
            self._started = False

    async def reconnect(self, slot: int) -> bool:
        state = self.get(slot)
        if state is None:
            return False
        await self._stop_one(state)
        try:
            await self._start_one(state)
            return True
        except Exception:
            return False
