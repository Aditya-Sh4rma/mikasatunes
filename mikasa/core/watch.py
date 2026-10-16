import asyncio
from typing import Awaitable, Callable, Optional

from pyrogram import enums

from ..logging_config import get_logger

logger = get_logger("mikasa.core.watch")

LEAVE_INTERVAL = 1800
END_INTERVAL = 60
MIN_LISTENERS = 2
MIN_POSITION = 30
RECENT_DIALOGS = 20

Notify = Callable[[int], Awaitable[None]]


def _group_ids(dialogs) -> list:
    ids = []
    for dialog in dialogs:
        chat = getattr(dialog, "chat", None)
        chat_type = getattr(chat, "type", None)
        if chat_type in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP):
            ids.append(chat.id)
    return ids


async def auto_leave_tick(assistants, active: set, skip: set) -> list:
    left = []
    try:
        states = assistants.ready()
    except Exception:
        return left
    for state in states:
        client = getattr(state, "client", None)
        if client is None:
            continue
        try:
            dialogs = [dialog async for dialog in client.get_dialogs()]
        except Exception as exc:
            logger.warning("dialog list failed: %s", type(exc).__name__)
            continue
        for chat_id in _group_ids(dialogs)[-RECENT_DIALOGS:]:
            if chat_id in skip or chat_id in active:
                continue
            try:
                await client.leave_chat(chat_id)
                left.append(chat_id)
            except Exception as exc:
                logger.warning("auto leave failed for %s: %s", chat_id, type(exc).__name__)
    return left


async def auto_end_tick(controller, notify: Optional[Notify] = None) -> list:
    stopped = []
    try:
        chats = list(controller.active_chats())
    except Exception:
        return stopped
    for chat_id in chats:
        try:
            if controller.is_paused(chat_id):
                continue
            count = await controller.participants(chat_id)
            position = controller.position(chat_id)
        except Exception:
            continue
        if count is None or count >= MIN_LISTENERS or position <= MIN_POSITION:
            continue
        try:
            await controller.stop(chat_id)
        except Exception as exc:
            logger.warning("auto end failed for %s: %s", chat_id, type(exc).__name__)
            continue
        stopped.append(chat_id)
        logger.info("auto ended empty call in %s", chat_id)
        if notify is not None:
            try:
                await notify(chat_id)
            except Exception:
                pass
    return stopped


async def auto_leave_loop(assistants, controller, skip: set, interval: int = LEAVE_INTERVAL) -> None:
    while True:
        await asyncio.sleep(interval)
        try:
            active = set(controller.active_chats())
        except Exception:
            active = set()
        await auto_leave_tick(assistants, active, skip)


async def auto_end_loop(controller, notify: Optional[Notify] = None, interval: int = END_INTERVAL) -> None:
    while True:
        await asyncio.sleep(interval)
        await auto_end_tick(controller, notify)


def start_watchers(settings, assistants, player, notify: Optional[Notify] = None) -> list:
    tasks = []
    if getattr(settings, 'auto_leave', False):
        skip = {getattr(settings, 'log_chat_id', 0)}
        tasks.append(asyncio.create_task(
            auto_leave_loop(assistants, player, skip), name='mikasa-auto-leave'
        ))
    if getattr(settings, 'auto_end', False):
        tasks.append(asyncio.create_task(
            auto_end_loop(player, notify), name='mikasa-auto-end'
        ))
    return tasks


def stop_watchers(tasks) -> None:
    for task in tasks or []:
        try:
            task.cancel()
        except Exception:
            pass
