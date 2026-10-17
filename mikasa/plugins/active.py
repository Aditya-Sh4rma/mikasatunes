from html import escape as html_escape

from pyrogram import filters
from pyrogram.handlers import MessageHandler

from ..context import ctx
from .common import _owner_only, _set_lang, _t

async def active_cmd(client, message) -> None:
    await _set_lang(message)
    if not await _owner_only(client, message):
        return
    controller = getattr(ctx, 'controller', None)
    chats = []
    if controller is not None:
        try:
            chats = list(controller.active_chats())
        except Exception:
            chats = []
    if not chats:
        await message.reply_text(_t('vc_empty'))
        return
    command = (getattr(message, 'command', None) or [''])[0]
    if command == 'ac':
        await message.reply_text(_t('vc_count', count=len(chats)))
        return
    lines = [_t('vc_list')]
    for index, chat_id in enumerate(chats, 1):
        title = ''
        try:
            current = await controller.current(chat_id)
        except Exception:
            current = None
        if current is not None:
            title = html_escape(getattr(current, 'title', '') or '')[:25]
        lines.append(f'\n<b>{index}.</b> {title}\n     <code>{chat_id}</code>')
    await message.reply_text(''.join(lines))


HANDLERS = (
    (active_cmd, 'ac'),
    (active_cmd, 'activevc'),
)


def register(app) -> None:
    for handler, command in HANDLERS:
        app.add_handler(MessageHandler(handler, filters.command(command)))
