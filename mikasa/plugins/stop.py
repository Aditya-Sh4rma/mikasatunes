from pyrogram import filters
from pyrogram.handlers import MessageHandler

from ..context import ctx
from .common import _display_user, _queue_buttons, _t, require_control, require_group

@require_group
@require_control
async def stop(client, message) -> None:
    await ctx.controller.stop(message.chat.id)
    await message.reply_text(
        _t('play_stopped', user=_display_user(message)),
        reply_markup=_queue_buttons(message.chat.id),
    )


HANDLERS = (
    (stop, 'stop'),
    (stop, 'end'),
)


def register(app) -> None:
    for handler, command in HANDLERS:
        app.add_handler(MessageHandler(handler, filters.command(command)))
