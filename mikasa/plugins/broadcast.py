# Copyright (c) 2026 Aditya-Sh4rma
# Licensed under the MIT License.
# This file is part of MikasaMusic


from pyrogram import filters
from pyrogram.handlers import MessageHandler

from .common import _need_database, _owner_only, _set_lang, _t

_broadcast_lock = None


def _broadcast_lock_holder():
    global _broadcast_lock
    if _broadcast_lock is None:
        import asyncio

        _broadcast_lock = asyncio.Lock()
    return _broadcast_lock


async def broadcast_cmd(client, message) -> None:
    await _set_lang(message)
    import asyncio

    if not await _owner_only(client, message):
        return
    source = getattr(message, 'reply_to_message', None)
    if source is None:
        await message.reply_text(_t('gcast_usage'))
        return
    database = await _need_database(message)
    if database is None:
        return
    lock = _broadcast_lock_holder()
    if lock.locked():
        await message.reply_text(_t('gcast_active'))
        return
    command = getattr(message, 'command', None) or []
    copy = '-copy' in command
    include_users = '-user' in command
    skip_chats = '-nochat' in command
    count = 0
    user_count = 0
    await message.reply_text(_t('gcast_start'))
    async with lock:
        if not skip_chats:
            try:
                chats = await database.served_chats()
            except Exception:
                chats = []
            for chat_id in chats:
                try:
                    if copy:
                        await source.copy(chat_id)
                    else:
                        await source.forward(chat_id)
                    count += 1
                    await asyncio.sleep(0.1)
                except Exception as exc:
                    if type(exc).__name__ == 'FloodWait':
                        await asyncio.sleep(getattr(exc, 'value', 5) + 10)
                    continue
        if include_users:
            try:
                users = await database.served_users()
            except Exception:
                users = []
            for user_id in users:
                try:
                    if copy:
                        await source.copy(user_id)
                    else:
                        await source.forward(user_id)
                    user_count += 1
                    await asyncio.sleep(0.1)
                except Exception as exc:
                    if type(exc).__name__ == 'FloodWait':
                        await asyncio.sleep(getattr(exc, 'value', 5) + 10)
                    continue
    await message.reply_text(_t('gcast_end', chats=count, users=user_count))


HANDLERS = (
    (broadcast_cmd, 'broadcast'),
)


def register(app) -> None:
    for handler, command in HANDLERS:
        app.add_handler(MessageHandler(handler, filters.command(command)))
