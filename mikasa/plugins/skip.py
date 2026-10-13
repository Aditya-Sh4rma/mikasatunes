from pyrogram import filters
from pyrogram.handlers import MessageHandler

from ..context import ctx
from ..tools.users import _display_user
from .common import _queue_buttons, _t, require_control, require_group

@require_group
@require_control
async def skip(client, message) -> None:
    chat_id = message.chat.id
    controller = ctx.controller
    if await controller.current(chat_id) is None:
        await message.reply_text(_t('not_playing'))
        return
    played = await controller.skip(chat_id)
    user = _display_user(message)
    await message.reply_text(
        _t('play_skipped', user=user) if played else _t('play_stopped', user=user),
        reply_markup=_queue_buttons(chat_id),
    )


HANDLERS = (
    (skip, 'skip'),
    (skip, 'next'),
)


def register(app) -> None:
    for handler, command in HANDLERS:
        app.add_handler(MessageHandler(handler, filters.command(command)))
