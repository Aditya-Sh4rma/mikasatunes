# Copyright (c) 2026 Aditya-Sh4rma
# Licensed under the MIT License.
# This file is part of MikasaMusic


from pyrogram import filters
from pyrogram.handlers import MessageHandler

from ..context import ctx
from .common import _bot_name, _is_group, _set_lang, _t

async def stats_cmd(client, message) -> None:
    await _set_lang(message)
    import platform
    import sys

    import psutil

    if not _is_group(message):
        await message.reply_text(_t('unsupported'))
        return
    settings = ctx.settings
    database = getattr(ctx, 'database', None)
    assistants = getattr(ctx, 'assistants', None)
    sudo_count = 0
    chats: list = []
    users: list = []
    blocked_chats = 0
    blocked_users = 0
    if database is not None:
        try:
            sudo_count = len(await database.sudo_users())
        except Exception:
            sudo_count = 0
        try:
            chats = await database.served_chats()
        except Exception:
            chats = []
        try:
            users = await database.served_users()
        except Exception:
            users = []
        try:
            blocked_chats = len(await database.blocked_chats())
        except Exception:
            blocked_chats = 0
        try:
            blocked_users = len(await database.blocked_users())
        except Exception:
            blocked_users = 0
    try:
        assistant_count = len(assistants.slots()) if assistants is not None else 0
    except Exception:
        assistant_count = 0
    text = _t(
        'stats_user',
        name=_bot_name(),
        assistants=assistant_count,
        auto_leave=bool(getattr(settings, 'auto_leave', False)),
        blocked_chats=blocked_chats,
        blocked_users=blocked_users,
        sudoers=sudo_count,
        chats=len(chats),
        users=len(users),
    )
    user = getattr(message, 'from_user', None)
    owner_id = getattr(settings, 'owner_id', 0)
    if user is not None and owner_id and user.id == owner_id:
        try:
            import pyrogram

            pyrogram_ver = getattr(pyrogram, '__version__', 'unknown')
        except Exception:
            pyrogram_ver = 'unknown'
        try:
            import pytgcalls

            pytgcalls_ver = getattr(pytgcalls, '__version__', 'unknown')
        except Exception:
            pytgcalls_ver = 'unknown'
        process = psutil.Process()
        storage = psutil.disk_usage('/')
        from mikasa.plugins import all_plugins

        text += _t(
            'stats_sudo',
            modules=len(all_plugins),
            platform=platform.system(),
            ram_mb=f'{process.memory_info().rss / 1024 ** 2:.2f}',
            ram_gb=round(psutil.virtual_memory().total / (1024.0 ** 3)),
            cpu=process.cpu_percent(interval=0),
            cores=psutil.cpu_count(),
            disk_used=f'{storage.used / (1024.0 ** 3):.2f}',
            disk_total=f'{storage.total / (1024.0 ** 3):.2f}',
            python=sys.version.split()[0],
            pyrogram=pyrogram_ver,
            pytgcalls=pytgcalls_ver,
        )
    await message.reply_text(text)


HANDLERS = (
    (stats_cmd, 'stats'),
)


def register(app) -> None:
    for handler, command in HANDLERS:
        app.add_handler(MessageHandler(handler, filters.command(command)))
