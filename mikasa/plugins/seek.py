from pyrogram import filters
from pyrogram.handlers import MessageHandler

from ..context import ctx
from .common import _display_user, _fail, _support_chat, _t, require_control, require_group

@require_group
@require_control
async def seek_cmd(client, message) -> None:
    command = (getattr(message, 'command', None) or [''])[0]
    args = (getattr(message, 'command', None) or [])[1:]
    if not args:
        await message.reply_text(_t('play_seek_usage', command=command))
        return
    try:
        amount = int(args[0])
    except (TypeError, ValueError):
        await message.reply_text(_t('play_seek_usage', command=command))
        return
    if amount < 10:
        await message.reply_text(_t('play_seek_min'))
        return
    controller = ctx.controller
    chat_id = message.chat.id
    current = await controller.current(chat_id)
    if current is None:
        await message.reply_text(_t('not_playing'))
        return
    if controller.is_paused(chat_id):
        await message.reply_text(_t('play_already_paused'))
        return
    duration = int(getattr(current, 'duration_seconds', 0) or 0)
    if not duration:
        await message.reply_text(_t('play_seek_no_dur'))
        return
    try:
        position = int(controller.position(chat_id))
    except Exception:
        position = 0
    if command == 'seekback':
        direction = _t('backward')
        start_from = position - amount
        if start_from < 1:
            start_from = 1
    else:
        direction = _t('forward')
        start_from = position + amount
        if start_from + 10 > duration:
            start_from = duration - 5
    if not getattr(current, 'file_path', ''):
        await message.reply_text(_t('error_no_file', support=_support_chat()))
        return
    sent = await message.reply_text(_t('play_seeking'))
    try:
        moved = await controller.seek(chat_id, start_from)
    except Exception:
        moved = False
    if not moved:
        await message.reply_text(_t('error'))
        return
    await _fail(
        sent,
        message,
        'play_seeked',
        direction=direction,
        seconds=start_from,
        user=_display_user(message),
    )


HANDLERS = (
    (seek_cmd, 'seek'),
    (seek_cmd, 'seekback'),
)


def register(app) -> None:
    for handler, command in HANDLERS:
        app.add_handler(MessageHandler(handler, filters.command(command)))
