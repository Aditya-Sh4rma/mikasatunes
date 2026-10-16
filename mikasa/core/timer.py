import asyncio
from typing import Awaitable, Callable, Optional

from ..logging_config import get_logger
from ..tools.utils import progress_text

logger = get_logger("mikasa.core.timer")

TIMER_INTERVAL = 7

MarkupFactory = Callable[[int, str, bool], object]


async def _build_markup(chat_id: int, timer: str, paused: bool, language, default_lang: str):
    from ..plugins.common import _control_labels, _current_lang
    from ..tools.buttons import player_controls

    code = ""
    if language is not None:
        try:
            code = language.cached(chat_id) or ""
        except Exception:
            code = ""
    token = _current_lang.set(code or default_lang)
    try:
        return player_controls(chat_id, paused=paused, labels=_control_labels(), timer=timer)
    finally:
        _current_lang.reset(token)


async def timer_tick(bot, controller, language, default_lang: str = "en") -> list:
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
            markup = await _build_markup(chat_id, text, False, language, default_lang)
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
    interval: int = TIMER_INTERVAL,
) -> None:
    while True:
        await asyncio.sleep(interval)
        await timer_tick(bot, controller, language, default_lang)


def start_timer(
    bot,
    controller,
    language,
    default_lang: str = "en",
    interval: int = TIMER_INTERVAL,
):
    return asyncio.create_task(
        timer_loop(bot, controller, language, default_lang, interval),
        name="mikasa-timer",
    )
