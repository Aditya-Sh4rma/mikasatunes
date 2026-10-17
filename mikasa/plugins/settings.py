from html import escape as html_escape

from pyrogram import filters
from pyrogram.handlers import CallbackQueryHandler, MessageHandler

from ..context import ctx
from ..logging_config import get_logger
from ..tools.buttons import lang_markup, settings_markup
from ..tools.models import ChatSettings
from ..tools.perms import _allowed_user, chat_play_mode
from .common import _deny_blocked, _set_lang, _t, require_group
from .lang import _current_code, _names

logger = get_logger('mikasa.plugins.settings')


def _lang_name(chat_id: int) -> str:
    names = _names()
    code = _current_code(chat_id)
    return names.get(code) or code


def _labels() -> dict:
    return {
        'play_mode': _t('play_mode'),
        'play_mode_admins': _t('play_mode_admins'),
        'play_mode_everyone': _t('play_mode_everyone'),
        'language': _t('language'),
    }


@require_group
async def settings_cmd(client, message) -> None:
    if await _deny_blocked(message):
        return
    chat_id = message.chat.id
    title = html_escape(getattr(message.chat, 'title', '') or 'this chat')
    markup = settings_markup(await chat_play_mode(chat_id), _lang_name(chat_id), _labels())
    await message.reply_text(_t('settings_menu', chat=title), reply_markup=markup)


async def settings_cb(client, query) -> None:
    await _set_lang(query)
    data = getattr(query, 'data', '') or ''
    parts = data.split(':')
    if len(parts) != 3 or parts[0] != 'mikasa' or parts[1] != 'settings':
        return
    action = parts[2]
    if action == 'noop':
        await query.answer()
        return
    message = getattr(query, 'message', None)
    chat = getattr(message, 'chat', None) if message is not None else None
    chat_id = getattr(chat, 'id', None)
    if chat_id is None:
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
    if action == 'lang':
        names = _names()
        current = _current_code(chat_id)
        await query.answer()
        edit = getattr(message, 'edit_text', None)
        if edit is not None:
            try:
                await edit(
                    _t('lang_choose'),
                    reply_markup=lang_markup(chat_id, current, names, close_label=_t('btn_close')),
                )
            except Exception:
                pass
        return
    if action != 'play':
        return
    database = getattr(ctx, 'database', None)
    if database is None:
        await query.answer(_t('error'), show_alert=True)
        return
    try:
        chat_settings = await database.chat_settings(chat_id)
        if not isinstance(chat_settings, ChatSettings):
            chat_settings = ChatSettings()
        chat_settings.play_mode = not bool(chat_settings.play_mode)
        await database.save_chat(chat_id, chat_settings)
    except Exception as exc:
        logger.warning('settings save failed for %s: %s', chat_id, type(exc).__name__)
        await query.answer(_t('error'), show_alert=True)
        return
    await query.answer()
    edit = getattr(message, 'edit_reply_markup', None)
    if edit is not None:
        try:
            await edit(
                reply_markup=settings_markup(
                    bool(chat_settings.play_mode), _lang_name(chat_id), _labels()
                )
            )
        except Exception:
            pass


HANDLERS = (
    (settings_cmd, 'settings'),
    (settings_cmd, 'playmode'),
)


def register(app) -> None:
    for handler, command in HANDLERS:
        app.add_handler(MessageHandler(handler, filters.command(command)))
    app.add_handler(CallbackQueryHandler(settings_cb, filters.regex(r'^mikasa:settings:')))
