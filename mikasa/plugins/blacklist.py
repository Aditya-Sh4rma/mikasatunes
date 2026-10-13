from pyrogram import filters
from pyrogram.handlers import MessageHandler

from .common import _need_database, _owner_only, _t

async def blacklist_cmd(client, message) -> None:
    if not await _owner_only(client, message):
        return
    command = (getattr(message, 'command', None) or [''])[0]
    args = (getattr(message, 'command', None) or [])[1:]
    if not args:
        await message.reply_text(_t('bl_usage', command=command))
        return
    raw = str(args[0]).strip()
    target = None
    if raw.startswith('@'):
        get_chat = getattr(client, 'get_chat', None)
        if get_chat is not None:
            try:
                chat = await get_chat(raw)
                target = getattr(chat, 'id', None)
            except Exception:
                target = None
    else:
        try:
            target = int(raw)
        except (TypeError, ValueError):
            target = None
    if target is None:
        await message.reply_text(_t('bl_invalid'))
        return
    database = await _need_database(message)
    if database is None:
        return
    is_chat = str(target).startswith('-')
    try:
        if command == 'blacklist':
            if is_chat:
                listed = target in await database.blocked_chats()
            else:
                listed = target in await database.blocked_users()
            if listed:
                await message.reply_text(_t('bl_already'))
                return
            if is_chat:
                await database.add_blocked_chat(target)
            else:
                await database.add_blocked_user(target)
            await message.reply_text(_t('bl_added'))
        else:
            if is_chat:
                listed = target in await database.blocked_chats()
            else:
                listed = target in await database.blocked_users()
            if not listed:
                await message.reply_text(_t('bl_not'))
                return
            if is_chat:
                await database.remove_blocked_chat(target)
            else:
                await database.remove_blocked_user(target)
            await message.reply_text(_t('bl_removed'))
    except Exception:
        await message.reply_text(_t('error'))


HANDLERS = (
    (blacklist_cmd, 'blacklist'),
    (blacklist_cmd, 'unblacklist'),
    (blacklist_cmd, 'whitelist'),
)


def register(app) -> None:
    for handler, command in HANDLERS:
        app.add_handler(MessageHandler(handler, filters.command(command)))
