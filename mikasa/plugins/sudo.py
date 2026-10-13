from pyrogram import filters
from pyrogram.handlers import MessageHandler

from ..context import ctx
from .common import _mention_of, _need_database, _need_target, _owner_only, _t

async def sudo_cmd(client, message) -> None:
    if not await _owner_only(client, message):
        return
    database = await _need_database(message)
    if database is None:
        return
    target = await _need_target(client, message)
    if target is None:
        return
    command = (getattr(message, 'command', None) or [''])[0]
    try:
        sudoers = await database.sudo_users()
    except Exception:
        await message.reply_text(_t('error'))
        return
    if command == 'addsudo':
        if target.id in sudoers:
            await message.reply_text(_t('sudo_already', user=_mention_of(target)))
            return
        try:
            await database.add_sudo(target.id)
        except Exception:
            await message.reply_text(_t('error'))
            return
        await message.reply_text(_t('sudo_added', user=_mention_of(target)))
    else:
        if target.id not in sudoers:
            await message.reply_text(_t('sudo_not', user=_mention_of(target)))
            return
        try:
            await database.remove_sudo(target.id)
        except Exception:
            await message.reply_text(_t('error'))
            return
        await message.reply_text(_t('sudo_removed', user=_mention_of(target)))


async def _resolve_mention(client, user_id: int) -> str:
    get_users = getattr(client, 'get_users', None)
    if get_users is not None:
        try:
            user = await get_users(user_id)
            mention = getattr(user, 'mention', None)
            if mention:
                return mention
        except Exception:
            pass
    return f'<a href="tg://user?id={user_id}">{user_id}</a>'


async def sudolist_cmd(client, message) -> None:
    database = getattr(ctx, 'database', None)
    settings = ctx.settings
    owner_id = getattr(settings, 'owner_id', 0) if settings is not None else 0
    sent = await message.reply_text(_t('sudo_fetching'))
    text = _t('sudo_owner', user=await _resolve_mention(client, owner_id))
    sudoers: list = []
    if database is not None:
        try:
            sudoers = sorted(await database.sudo_users())
        except Exception:
            sudoers = []
    if sudoers:
        text += _t('sudo_users')
        for user_id in sudoers:
            text += f'\n- {await _resolve_mention(client, user_id)}'
    edit = getattr(sent, 'edit_text', None)
    if edit is not None:
        try:
            await edit(text)
            return
        except Exception:
            pass
    await message.reply_text(text)


HANDLERS = (
    (sudo_cmd, 'addsudo'),
    (sudo_cmd, 'delsudo'),
    (sudo_cmd, 'rmsudo'),
    (sudolist_cmd, 'listsudo'),
    (sudolist_cmd, 'sudolist'),
)


def register(app) -> None:
    for handler, command in HANDLERS:
        app.add_handler(MessageHandler(handler, filters.command(command)))
