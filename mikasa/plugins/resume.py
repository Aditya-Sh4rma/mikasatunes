from pyrogram import filters
from pyrogram.handlers import MessageHandler

from ..context import ctx
from .common import _display_user, _t, require_control, require_group

@require_group
@require_control
async def resume(client, message) -> None:
    controller = ctx.controller
    if await controller.current(message.chat.id) is None:
        await message.reply_text(_t('not_playing'))
        return
    if not controller.is_paused(message.chat.id):
        await message.reply_text(_t('play_not_paused'))
        return
    if await controller.resume(message.chat.id):
        await message.reply_text(_t('play_resumed', user=_display_user(message)))
    else:
        await message.reply_text(_t('not_playing'))


HANDLERS = (
    (resume, 'resume'),
)


def register(app) -> None:
    for handler, command in HANDLERS:
        app.add_handler(MessageHandler(handler, filters.command(command)))
