from html import escape as html_escape

from pyrogram import filters
from pyrogram.handlers import MessageHandler

from ..context import ctx
from .common import _arguments, _describe, _t, require_control, require_group

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
                    index=index,
                    title=html_escape(item.title),
                    duration=item_duration,
                )
            )
    await message.reply_text('\n'.join(lines))


@require_group
@require_control
async def remove_cmd(client, message) -> None:
    chat_id = message.chat.id
    args = _arguments(message).split()
    if not args or not args[0].isdigit():
        await message.reply_text(_t('remove_usage'))
        return
    position = int(args[0])
    items = await ctx.queue.items(chat_id)
    if not items:
        await message.reply_text(_t('queue_empty'))
        return
    if position < 1 or position > len(items):
        await message.reply_text(_t('remove_invalid', position=position))
        return
    item = items[position - 1]
    await ctx.queue.remove(chat_id, item.id)
    await message.reply_text(
        _t('remove_done', title=html_escape(item.title), position=position)
    )


@require_group
@require_control
async def shuffle_cmd(client, message) -> None:
    count = await ctx.queue.shuffle(message.chat.id)
    if count < 2:
        await message.reply_text(_t('shuffle_short'))
        return
    await message.reply_text(_t('shuffle_done', count=count))


HANDLERS = (
    (queue_cmd, 'queue'),
    (queue_cmd, 'playing'),
    (remove_cmd, 'remove'),
    (shuffle_cmd, 'shuffle'),
)


def register(app) -> None:
    for handler, command in HANDLERS:
        app.add_handler(MessageHandler(handler, filters.command(command)))
