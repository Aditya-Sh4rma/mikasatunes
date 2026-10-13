import asyncio
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from ._dataclass import MediaItem


class AddResult(Enum):
    ADDED = auto()
    DUPLICATE = auto()
    FULL = auto()


@dataclass
class QueueState:
    items: list = field(default_factory=list)


class Queue:
    def __init__(self, limit: int = 0) -> None:
        self._limit = max(0, int(limit))
        self._chats: dict[int, QueueState] = {}
        self._lock = asyncio.Lock()

    async def add(self, chat_id: int, item: MediaItem, allow_duplicate: bool = False) -> AddResult:
        async with self._lock:
            state = self._chats.setdefault(chat_id, QueueState())
            if not allow_duplicate and any(existing.id == item.id for existing in state.items):
                return AddResult.DUPLICATE
            if self._limit and len(state.items) >= self._limit:
                return AddResult.FULL
            state.items.append(item)
            return AddResult.ADDED

    async def pop_next(self, chat_id: int) -> Optional[MediaItem]:
        async with self._lock:
            state = self._chats.get(chat_id)
            if not state or not state.items:
                return None
            return state.items.pop(0)

    async def peek(self, chat_id: int) -> Optional[MediaItem]:
        async with self._lock:
            state = self._chats.get(chat_id)
            if not state or not state.items:
                return None
            return state.items[0]

    async def remove(self, chat_id: int, item_id: str) -> bool:
        async with self._lock:
            state = self._chats.get(chat_id)
            if not state:
                return False
            for index, existing in enumerate(state.items):
                if existing.id == item_id:
                    del state.items[index]
                    return True
            return False

    async def clear(self, chat_id: int) -> int:
        async with self._lock:
            state = self._chats.pop(chat_id, None)
            return len(state.items) if state else 0

    async def items(self, chat_id: int) -> list:
        async with self._lock:
            state = self._chats.get(chat_id)
            return list(state.items) if state else []

    async def size(self, chat_id: int) -> int:
        async with self._lock:
            state = self._chats.get(chat_id)
            return len(state.items) if state else 0

    async def contains(self, chat_id: int, item_id: str) -> bool:
        async with self._lock:
            state = self._chats.get(chat_id)
            if not state:
                return False
            return any(existing.id == item_id for existing in state.items)
