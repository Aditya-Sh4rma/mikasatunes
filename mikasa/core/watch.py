import asyncio
from typing import Awaitable, Callable, Optional

from pyrogram import enums

from ..logging_config import get_logger
from ..tools.utils import progress_text

logger = get_logger("mikasa.core.watch")

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
        for chat_id in _group_ids(dialogs)[-20:]:
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
        if count is None or count >= 2 or position <= 30:
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


async def auto_leave_loop(assistants, controller, skip: set, interval: int = 1800) -> None:
    while True:
        await asyncio.sleep(interval)
        try:
            active = set(controller.active_chats())
        except Exception:
            active = set()
        await auto_leave_tick(assistants, active, skip)


async def auto_end_loop(controller, notify: Optional[Notify] = None, interval: int = 60) -> None:
    while True:
        await asyncio.sleep(interval)
        await auto_end_tick(controller, notify)


async def auto_left_notify(chat_id: int) -> None:
    from ..context import ctx
    from ..plugins.common import _tc

    bot = getattr(ctx, 'bot', None)
    if bot is None:
        return
    try:
        await bot.send_message(chat_id, _tc(chat_id, 'auto_left'))
    except Exception:
        pass


def start_watchers(settings, assistants, player, notify: Optional[Notify] = None) -> list:
    tasks = []
    notify = notify or auto_left_notify
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


async def timer_tick(bot, controller, language, default_lang: str = "en") -> list:
    from ..plugins.common import _control_labels, _current_lang
    from ..tools.buttons import player_controls

    updated = []
    try:
        chats = list(controller.active_chats())
    except Exception:
        return updated
    for chat_id in chats:
        try:
            if controller.is_paused(chat_id):
                continue
            item = await controller.current(chat_id)
            if item is None:
                continue
            total = int(getattr(item, "duration_seconds", 0) or 0)
            message_id = int(getattr(item, "message_id", 0) or 0)
            if not total or not message_id:
                continue
            try:
                played = int(controller.position(chat_id))
            except Exception:
                continue
            text = progress_text(played, total)
            if not text:
                continue
            try:
                code = language.cached(chat_id) if language is not None else ""
            except Exception:
                code = ""
            token = _current_lang.set(code or default_lang)
            try:
                markup = player_controls(
                    chat_id, paused=False, labels=_control_labels(), timer=text
                )
            finally:
                _current_lang.reset(token)
            try:
                await bot.edit_message_reply_markup(chat_id, message_id, reply_markup=markup)
            except Exception as exc:
                logger.warning("timer edit failed for %s: %s", chat_id, type(exc).__name__)
                continue
            updated.append(chat_id)
        except Exception as exc:
            logger.warning("timer tick failed for %s: %s", chat_id, type(exc).__name__)
    return updated


async def timer_loop(
    bot,
    controller,
    language,
    default_lang: str = "en",
    interval: int = 7,
) -> None:
    while True:
        await asyncio.sleep(interval)
        await timer_tick(bot, controller, language, default_lang)


def start_timer(
    bot,
    controller,
    language,
    default_lang: str = "en",
    interval: int = 7,
):
    return asyncio.create_task(
        timer_loop(bot, controller, language, default_lang, interval),
        name="mikasa-timer",
    )
