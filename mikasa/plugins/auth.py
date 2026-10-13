import time
from html import escape as html_escape

from pyrogram import filters
from pyrogram.handlers import MessageHandler

from ..tools.admins import member_is_admin, reload_admins
from ..tools.users import _mention_of
from .common import (
    _allowed,
    _is_group,
    _need_database,
    _need_target,
    _t,
)

_rel_hist: dict[int, float] = {}


async def auth_cmd(client, message) -> None:
    if not _is_group(message):
        await message.reply_text(_t('unsupported'))
        return
    if not await _allowed(client, message, allow_auth=False):
        return
    database = await _need_database(message)
    if database is None:
        return
    target = await _need_target(client, message)
    if target is None:
        return
    command = (getattr(message, 'command', None) or [''])[0]
    chat_id = message.chat.id
    if command == 'auth':
        try:
            already_admin = await member_is_admin(client, chat_id, target.id)
        except Exception:
            already_admin = False
        if already_admin:
            await message.reply_text(_t('auth_is_admin'))
            return
        try:
            await database.add_auth(chat_id, target.id)
        except Exception:
            await message.reply_text(_t('error'))
            return
        await message.reply_text(_t('auth_added', user=_mention_of(target)))
    else:
        try:
            await database.remove_auth(chat_id, target.id)
        except Exception:
            await message.reply_text(_t('error'))
            return
        await message.reply_text(_t('auth_removed', user=_mention_of(target)))


async def authlist_cmd(client, message) -> None:
    if not _is_group(message):
        await message.reply_text(_t('unsupported'))
        return
    if not await _allowed(client, message, allow_auth=False):
        return
    database = await _need_database(message)
    if database is None:
        return
    try:
        users = await database.chat_auth_users(message.chat.id)
    except Exception:
        await message.reply_text(_t('error'))
        return
    if not users:
        await message.reply_text(_t('auth_empty'))
        return
    title = getattr(message.chat, 'title', '') or ''
    text = _t('auth_list', chat=html_escape(title))
    for index, user_id in enumerate(users, 1):
        text += f'\n{index}. <a href="tg://user?id={user_id}">{user_id}</a>'
    await message.reply_text(text)


async def reload_cmd(client, message) -> None:
    if not _is_group(message):
        await message.reply_text(_t('unsupported'))
        return
    user = getattr(message, 'from_user', None)
    if user is None:
        return
    now = time.time()
    for known_id, expires in list(_rel_hist.items()):
        if expires <= now:
            _rel_hist.pop(known_id, None)
    if _rel_hist.get(user.id, 0) > now:
        await message.reply_text(_t('admin_cache_wait'))
        return
    _rel_hist[user.id] = now + 600
    sent = await message.reply_text(_t('admin_cache_reloading'))
    try:
        await reload_admins(client, message.chat.id)
    except Exception:
        pass
    edit = getattr(sent, 'edit_text', None)
    if edit is not None:
        try:
            await edit(_t('admin_cache_reloaded'))
            return
        except Exception:
            pass
    await message.reply_text(_t('admin_cache_reloaded'))


HANDLERS = (
    (auth_cmd, 'auth'),
    (auth_cmd, 'unauth'),
    (authlist_cmd, 'authlist'),
    (reload_cmd, 'reload'),
    (reload_cmd, 'admincache'),
)


def register(app) -> None:
    for handler, command in HANDLERS:
        app.add_handler(MessageHandler(handler, filters.command(command)))
