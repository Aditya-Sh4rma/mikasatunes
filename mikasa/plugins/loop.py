from pyrogram import filters
from pyrogram.handlers import MessageHandler

from ..context import ctx
from .common import _need_database, _t, require_control, require_group

@require_group
@require_control
async def loop_cmd(client, message) -> None:
    chat_id = message.chat.id
    if await ctx.controller.current(chat_id) is None:
        await message.reply_text(_t('not_playing'))
        return
    database = await _need_database(message)
    if database is None:
        return
    args = (getattr(message, 'command', None) or [])[1:]
    if not args:
        try:
            count = int(getattr(await database.chat_settings(chat_id), 'loop', 0) or 0)
        except Exception:
            await message.reply_text(_t('error'))
            return
        if count:
            await message.reply_text(_t('loop_count', count=count))
        else:
            await message.reply_text(_t('loop_usage'))
        return
    raw = str(args[0]).lower()
    if raw in ('off', 'disable'):
        count = 0
    elif raw.isdigit():
        count = int(raw)
        if count < 1:
            count = 0
        elif count > 10:
            count = 10
    else:
        await message.reply_text(_t('loop_usage'))
        return
    try:
        settings = await database.chat_settings(chat_id)
        settings.loop = count
        await database.save_chat(chat_id, settings)
    except Exception:
        await message.reply_text(_t('error'))
        return
    if count == 0:
        await message.reply_text(_t('loop_off'))
    else:
        await message.reply_text(_t('loop_set', count=count))


HANDLERS = (
    (loop_cmd, 'loop'),
)


def register(app) -> None:
    for handler, command in HANDLERS:
        app.add_handler(MessageHandler(handler, filters.command(command)))
