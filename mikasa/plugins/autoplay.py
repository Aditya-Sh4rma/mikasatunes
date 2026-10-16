from html import escape as html_escape

from pyrogram import filters
from pyrogram.handlers import MessageHandler

from ..context import ctx
from ..logging_config import get_logger
from ..tools.buttons import player_controls
from ..tools.models import Track
from .common import (
    _control_labels,
    _current_lang,
    _duration_text,
    _t,
    require_control,
    require_group,
)

logger = get_logger('mikasa.plugins.autoplay')


async def announce_autoplay(chat_id: int, item) -> None:
    bot = getattr(ctx, 'bot', None)
    if bot is None:
        return
    language = getattr(ctx, 'language', None)
    settings = getattr(ctx, 'settings', None)
    default = getattr(settings, 'default_language', None) or 'en'
    code = (language.cached(chat_id) if language is not None else '') or default
    token = _current_lang.set(code)
    try:
        await _announce_in_lang(bot, chat_id, item)
    finally:
        _current_lang.reset(token)


async def _announce_in_lang(bot, chat_id: int, item) -> None:
    title = html_escape(getattr(item, 'title', '') or 'Unknown')
    url = getattr(item, 'url', '') or ''
    duration = _duration_text(getattr(item, 'duration_seconds', 0) or 0)
    user = getattr(item, 'requested_by', '') or 'autoplay'
    thumbs = getattr(ctx, 'thumbs', None)
    settings = ctx.settings
    card = None
    if (
        thumbs is not None
        and bool(getattr(settings, 'thumbnails', True))
        and isinstance(item, Track)
    ):
        try:
            card = await thumbs.generate(item, channel=item.channel or '', duration=duration)
        except Exception as exc:
            logger.warning('autoplay card failed: %s', type(exc).__name__)
            card = None
    markup = player_controls(chat_id, paused=False, labels=_control_labels())
    caption = _t('play_media', url=url, title=title, duration=duration, user=user)
    photo = card or (getattr(settings, 'default_thumb', '') or '')
    try:
        if photo:
            sent = await bot.send_photo(photo=photo, caption=caption, reply_markup=markup, chat_id=chat_id)
            item.message_id = getattr(sent, 'id', 0) or 0
        else:
            sent = await bot.send_message(chat_id, caption, reply_markup=markup)
            item.message_id = getattr(sent, 'id', 0) or 0
    except Exception as exc:
        logger.warning('autoplay announce failed for %s: %s', chat_id, type(exc).__name__)


@require_group
@require_control
async def autoplay_cmd(client, message) -> None:
    chat_id = message.chat.id
    controller = getattr(ctx, 'controller', None)
    if controller is None or await controller.current(chat_id) is None:
        await message.reply_text(_t('not_playing'))
        return
    args = (getattr(message, 'command', None) or [])[1:]
    if not args:
        if controller.autoplay_enabled(chat_id):
            await message.reply_text(_t('autoplay_on'))
        else:
            await message.reply_text(_t('autoplay_usage'))
        return
    raw = str(args[0]).lower()
    if raw in ('on', 'enable'):
        enabled = True
    elif raw in ('off', 'disable'):
        enabled = False
    else:
        await message.reply_text(_t('autoplay_usage'))
        return
    try:
        controller.set_autoplay(chat_id, enabled)
    except Exception:
        await message.reply_text(_t('error'))
        return
    if enabled:
        await message.reply_text(_t('autoplay_on'))
    else:
        await message.reply_text(_t('autoplay_off'))


HANDLERS = (
    (autoplay_cmd, 'autoplay'),
)


def register(app) -> None:
    for handler, command in HANDLERS:
        app.add_handler(MessageHandler(handler, filters.command(command)))
