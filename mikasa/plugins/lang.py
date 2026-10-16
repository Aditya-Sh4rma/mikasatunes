from pyrogram import filters
from pyrogram.handlers import CallbackQueryHandler, MessageHandler

from ..context import ctx
from ..logging_config import get_logger
from ..tools.buttons import lang_markup
from ..tools.perms import _allowed_user
from .common import _deny_blocked, _set_lang, _t

logger = get_logger('mikasa.plugins.lang')


def _names() -> dict:
    language = getattr(ctx, 'language', None)
    if language is None:
        return {'en': 'English'}
    try:
        return language.available_names() or {'en': 'English'}
    except Exception:
        return {'en': 'English'}


def _current_code(chat_id: int) -> str:
    language = getattr(ctx, 'language', None)
    settings = getattr(ctx, 'settings', None)
    default = getattr(settings, 'default_language', None) or 'en'
    if language is None:
        return default
    try:
        return language.cached(chat_id) or default
    except Exception:
        return default


async def lang_cmd(client, message) -> None:
    await _set_lang(message)
    if await _deny_blocked(message):
        return
    chat_id = message.chat.id
    names = _names()
    current = _current_code(chat_id)
    markup = lang_markup(chat_id, current, names, close_label=_t('btn_close'))
    await message.reply_text(_t('lang_choose'), reply_markup=markup)


async def lang_cb(client, query) -> None:
    await _set_lang(query)
    data = getattr(query, 'data', '') or ''
    parts = data.split(':')
    if len(parts) != 3 or parts[0] != 'mikasa' or parts[1] != 'lang':
        return
    code = (parts[2] or '').lower()
    message = getattr(query, 'message', None)
    chat = getattr(message, 'chat', None) if message is not None else None
    chat_id = getattr(chat, 'id', None)
    if chat_id is None:
        return
    names = _names()
    if code not in names:
        return
    user = getattr(query, 'from_user', None)
    if user is None:
        return
    allowed, key = await _allowed_user(client, chat_id, user.id)
    if not allowed:
        if key == 'bl_user_notify':
            settings = ctx.settings
            support = getattr(settings, 'support_chat', '') or 'https://t.me/'
            await query.answer(_t('bl_user_notify', support=support), show_alert=True)
        else:
            await query.answer(_t('not_admin'), show_alert=True)
        return
    current = _current_code(chat_id)
    if current == code:
        await query.answer(_t('lang_same', name=names[code]), show_alert=True)
        return
    database = getattr(ctx, 'database', None)
    language = getattr(ctx, 'language', None)
    if database is None:
        await query.answer(_t('error'), show_alert=True)
        return
    try:
        from ..tools.models import ChatSettings

        settings = await database.chat_settings(chat_id)
        if not isinstance(settings, ChatSettings):
            settings = ChatSettings()
        settings.language = code
        await database.save_chat(chat_id, settings)
    except Exception as exc:
        logger.warning('lang save failed for %s: %s', chat_id, type(exc).__name__)
        await query.answer(_t('error'), show_alert=True)
        return
    if language is not None:
        try:
            language.set_cached(chat_id, code)
        except Exception:
            pass
    await query.answer(ctx.language.text(code, 'lang_changed', name=names[code]), show_alert=True)
    if message is not None:
        edit = getattr(message, 'edit_text', None)
        if edit is not None:
            try:
                await edit(
                    ctx.language.text(code, 'lang_choose'),
                    reply_markup=lang_markup(chat_id, code, names, close_label=ctx.language.text(code, 'btn_close')),
                )
            except Exception:
                pass


HANDLERS = (
    (lang_cmd, 'lang'),
    (lang_cmd, 'language'),
)


def register(app) -> None:
    for handler, command in HANDLERS:
        app.add_handler(MessageHandler(handler, filters.command(command)))
    app.add_handler(CallbackQueryHandler(lang_cb, filters.regex(r'^mikasa:lang:')))
