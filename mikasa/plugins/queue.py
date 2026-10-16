# Copyright (c) 2026 Aditya-Sh4rma
# Licensed under the MIT License.
# This file is part of MikasaMusic


from html import escape as html_escape

from pyrogram import filters
from pyrogram.handlers import MessageHandler

from ..context import ctx
from .common import _describe, _t, require_group

@require_group
async def queue_cmd(client, message) -> None:
    chat_id = message.chat.id
    current = await ctx.controller.current(chat_id)
    items = await ctx.queue.items(chat_id)
    if current is None:
        await message.reply_text(_t('not_playing'))
        return
    duration, user = _describe(current)
    lines = [
        _t(
            'queue_curr',
            url=current.url or '',
            title=html_escape(current.title),
            duration=duration,
            user=user,
        )
    ]
    if items:
        for index, item in enumerate(items, 1):
            item_duration, _ = _describe(item)
            lines.append(
                _t(
                    'queue_item',
                    index=index + 1,
                    title=html_escape(item.title),
                    duration=item_duration,
                )
            )
    await message.reply_text('\n'.join(lines))


HANDLERS = (
    (queue_cmd, 'queue'),
    (queue_cmd, 'playing'),
)


def register(app) -> None:
    for handler, command in HANDLERS:
        app.add_handler(MessageHandler(handler, filters.command(command)))
