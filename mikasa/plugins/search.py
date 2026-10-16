import re
from html import escape as html_escape

from pyrogram import filters
from pyrogram.handlers import CallbackQueryHandler, MessageHandler

from ..context import ctx
from ..tools.buttons import search_results
from ..tools.users import _display_user
from .common import (
    _arguments,
    _deny_blocked,
    _fail,
    _is_group,
    _send_resolve_error,
    _set_lang,
    _support_chat,
    _t,
)
from .play import _play_item

_pending: dict[int, dict[str, object]] = {}

_VIDEO_ID_RE = re.compile(r'^[A-Za-z0-9_-]{1,20}$')


def _short_title(title: str, width: int = 35) -> str:
    title = ' '.join((title or '').split())
    if not title:
        return 'Unknown'
    if len(title) <= width:
        return title
    return title[:width - 1].rstrip() + '…'


def remember_search(chat_id: int, tracks) -> None:
    if len(_pending) >= 50 and chat_id not in _pending:
        _pending.pop(next(iter(_pending)))
    _pending[chat_id] = {track.video_id: track for track in tracks if track.video_id}


async def search_cmd(client, message) -> None:
    await _set_lang(message)
    if not _is_group(message):
        await message.reply_text(_t('unsupported'))
        return
    if await _deny_blocked(message):
        return
    text = _arguments(message)
    if not text:
        await message.reply_text(_t('play_usage'))
        return
    sent = await message.reply_text(_t('play_searching'))
    try:
        tracks = await ctx.search.search(text, limit=5)
    except Exception as exc:
        await _send_resolve_error(sent, message, exc)
        return
    if not tracks:
        await _fail(sent, message, 'play_not_found', support=_support_chat())
        return
    chat_id = message.chat.id
    remember_search(chat_id, tracks)
    entries = [(track.video_id, _short_title(track.title)) for track in tracks]
    caption = _t('search_results', query=html_escape(text))
    markup = search_results(chat_id, entries, close_label=_t('btn_close'))
    edit = getattr(sent, 'edit_text', None)
    if edit is not None:
        try:
            await edit(caption, reply_markup=markup)
            return
        except Exception:
            pass
    await message.reply_text(caption, reply_markup=markup)


async def select_cb(client, query) -> None:
    await _set_lang(query)
    data = getattr(query, 'data', '') or ''
    parts = data.split(':')
    if len(parts) != 3 or parts[0] != 'mikasa' or parts[1] != 'select':
        return
    video_id = parts[2]
    if not _VIDEO_ID_RE.match(video_id):
        return
    message = getattr(query, 'message', None)
    if message is None:
        await query.answer(_t('error'), show_alert=True)
        return
    chat = getattr(message, 'chat', None)
    if chat is None:
        await query.answer(_t('error'), show_alert=True)
        return
    chat_id = chat.id
    user = getattr(query, 'from_user', None)
    if user is None:
        await query.answer(_t('not_admin'), show_alert=True)
        return
    database = getattr(ctx, 'database', None)
    if database is not None:
        try:
            blocked = await database.blocked_users()
        except Exception:
            blocked = set()
        if user.id in blocked:
            await query.answer(_t('bl_user_notify', support=_support_chat()), show_alert=True)
            return
    track = _pending.get(chat_id, {}).get(video_id)
    if track is None:
        await query.answer(_t('search_expired'), show_alert=True)
        return
    track.requested_by = _display_user(query)
    await query.answer()
    await _play_item(client, message, message, track, chat_id)


HANDLERS = (
    (search_cmd, 'search'),
)


def register(app) -> None:
    for handler, command in HANDLERS:
        app.add_handler(MessageHandler(handler, filters.command(command)))
    app.add_handler(CallbackQueryHandler(select_cb, filters.regex(r'^mikasa:select:')))
