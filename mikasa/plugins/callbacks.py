from pyrogram import filters
from pyrogram.handlers import CallbackQueryHandler

from ..context import ctx
from ..tools.buttons import (
    HELP_TOPICS,
    help_markup,
    parse_callback,
    player_controls,
)
from ..tools.perms import _allowed_user
from ..tools.users import _display_user
from ..tools.utils import progress_text
from .common import (
    _bot_username,
    _control_labels,
    _help_labels,
    _queue_buttons,
    _set_lang,
    _start_keyboard,
    _start_pm_caption,
    _t,
)


async def _refresh_markup(query, chat_id: int, paused: bool) -> None:
    message = getattr(query, 'message', None)
    if message is None:
        return
    edit = getattr(message, 'edit_reply_markup', None)
    if edit is None:
        return
    try:
        await edit(player_controls(chat_id, paused=paused, labels=_control_labels()))
    except Exception:
        pass


async def control_cb(client, query) -> None:
    await _set_lang(query)
    action, chat_id = parse_callback(getattr(query, 'data', ''))
    if action is None or chat_id is None:
        return
    message = getattr(query, 'message', None)
    if action == 'close':
        await query.answer()
        if message is not None:
            try:
                await message.delete()
            except Exception:
                pass
        return
    user = getattr(query, 'from_user', None)
    if user is None:
        await query.answer(_t('not_admin'), show_alert=True)
        return
    if action == 'status':
        controller = ctx.controller
        item = await controller.current(chat_id) if controller is not None else None
        if item is None:
            await query.answer(_t('not_playing'), show_alert=True)
            return
        try:
            played = int(controller.position(chat_id))
        except Exception:
            played = 0
        total = int(getattr(item, 'duration_seconds', 0) or 0)
        text = progress_text(played, total) or _t('not_playing')
        await query.answer(text, show_alert=True)
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
    controller = ctx.controller
    if controller is None:
        await query.answer(_t('error'), show_alert=True)
        return
    name = _display_user(query)
    if action == 'pause':
        if await controller.current(chat_id) is None:
            await query.answer(_t('not_playing'), show_alert=True)
            return
        if controller.is_paused(chat_id):
            await query.answer(_t('play_already_paused'), show_alert=True)
            return
        if await controller.pause(chat_id):
            await query.answer(_t('play_paused', user=name))
            await _refresh_markup(query, chat_id, paused=True)
        else:
            await query.answer(_t('not_playing'), show_alert=True)
    elif action == 'resume':
        if await controller.current(chat_id) is None:
            await query.answer(_t('not_playing'), show_alert=True)
            return
        if not controller.is_paused(chat_id):
            await query.answer(_t('play_not_paused'), show_alert=True)
            return
        if await controller.resume(chat_id):
            await query.answer(_t('play_resumed', user=name))
            await _refresh_markup(query, chat_id, paused=False)
        else:
            await query.answer(_t('not_playing'), show_alert=True)
    elif action == 'skip':
        if await controller.current(chat_id) is None:
            await query.answer(_t('not_playing'), show_alert=True)
            return
        played = await controller.skip(chat_id)
        await query.answer()
        if message is not None:
            try:
                await message.reply_text(
                    _t('play_skipped', user=name) if played else _t('play_stopped', user=name),
                    reply_markup=_queue_buttons(chat_id),
                )
            except Exception:
                pass
            try:
                await message.delete()
            except Exception:
                pass
    elif action == 'stop':
        if await controller.current(chat_id) is None:
            await query.answer(_t('not_playing'), show_alert=True)
            return
        await controller.stop(chat_id)
        await query.answer()
        if message is not None:
            try:
                await message.reply_text(
                    _t('play_stopped', user=name),
                    reply_markup=_queue_buttons(chat_id),
                )
            except Exception:
                pass
            try:
                await message.delete()
            except Exception:
                pass


async def help_cb(client, query) -> None:
    await _set_lang(query)
    data = getattr(query, 'data', '') or ''
    message = getattr(query, 'message', None)
    if data == 'mikasa:help':
        username = _bot_username()
        if username:
            try:
                await query.answer(url=f'https://t.me/{username}?start=help')
                return
            except Exception:
                pass
        topic = None
    elif data.startswith('mikasa:help:'):
        parts = data.split(':')
        topic = parts[2] if len(parts) == 3 else None
    else:
        return
    if topic == 'close':
        await query.answer()
        if message is not None:
            try:
                await message.delete()
            except Exception:
                pass
            try:
                replied = getattr(message, 'reply_to_message', None)
                if replied is not None:
                    await replied.delete()
            except Exception:
                pass
        return
    await query.answer()
    if message is None:
        return
    edit = getattr(message, 'edit_text', None)
    if edit is None:
        return
    try:
        if topic == 'back' or topic is None:
            await edit(_t('help_menu'), reply_markup=help_markup(_help_labels()))
        elif topic in HELP_TOPICS:
            await edit(
                _t(f'help_{topic}'), reply_markup=help_markup(_help_labels(), back=True)
            )
    except Exception:
        pass





async def start_cb(client, query) -> None:
    await _set_lang(query)
    data = getattr(query, 'data', '') or ''
    message = getattr(query, 'message', None)
    if data == 'mikasa:start:help':
        await query.answer()
        if message is None:
            return
        edit = getattr(message, 'edit_text', None)
        if edit is None:
            return
        try:
            await edit(
                _t('help_menu'),
                reply_markup=help_markup(_help_labels(), origin='start'),
            )
        except Exception:
            pass
        return
    if data == 'mikasa:start:back':
        await query.answer()
        if message is None:
            return
        try:
            caption = _start_pm_caption(query)
            markup = _start_keyboard()
        except Exception:
            return
        edited = False
        if getattr(message, 'photo', None):
            edit_caption = getattr(message, 'edit_caption', None)
            if edit_caption is not None:
                try:
                    await edit_caption(caption, reply_markup=markup)
                    edited = True
                except Exception:
                    pass
        if not edited:
            edit = getattr(message, 'edit_text', None)
            if edit is not None:
                try:
                    await edit(caption, reply_markup=markup)
                except Exception:
                    pass
        return
    if data.startswith('mikasa:start:'):
        parts = data.split(':')
        topic = parts[2] if len(parts) == 3 else None
        if topic not in HELP_TOPICS:
            return
        await query.answer()
        if message is None:
            return
        edit = getattr(message, 'edit_text', None)
        if edit is None:
            return
        try:
            await edit(
                _t(f'help_{topic}'),
                reply_markup=help_markup(_help_labels(), back=True, origin='start'),
            )
        except Exception:
            pass
        return


def register(app) -> None:
    app.add_handler(
        CallbackQueryHandler(
            control_cb,
            filters.regex(r'^mikasa:(pause|resume|skip|stop|close):'),
        )
    )
    app.add_handler(
        CallbackQueryHandler(
            help_cb,
            filters.regex(r'^mikasa:help($|:)'),
        )
    )
    app.add_handler(
        CallbackQueryHandler(
            start_cb,
            filters.regex(r'^mikasa:start:'),
        )
    )
