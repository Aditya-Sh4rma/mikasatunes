# Copyright (c) 2026 Aditya-Sh4rma
# Licensed under the MIT License.
# This file is part of MikasaMusic


from pyrogram import filters
from pyrogram.handlers import MessageHandler

from ..context import ctx
from ..tools.utils import format_uptime
from .common import _fail, _set_lang, _t

async def ping_cmd(client, message) -> None:
    await _set_lang(message)
    import time

    import psutil

    started = time.time()
    photo = getattr(ctx.settings, 'ping_image', '') or ''
    if photo:
        try:
            sent = await message.reply_photo(photo=photo, caption=_t('pinging'))
            use_photo = True
        except Exception:
            sent = await message.reply_text(_t('pinging'))
            use_photo = False
    else:
        sent = await message.reply_text(_t('pinging'))
        use_photo = False
    latency = round((time.time() - started) * 1000, 2)
    boot = getattr(ctx, 'started_at', None) or time.time()
    uptime = format_uptime(time.time() - boot)
    voice_ping = None
    controller = getattr(ctx, 'controller', None)
    if controller is not None:
        try:
            voice_ping = controller.voice_ping()
        except Exception:
            voice_ping = None
    args = dict(
        latency=latency,
        uptime=uptime,
        cpu=psutil.cpu_percent(interval=0),
        ram=psutil.virtual_memory().percent,
        disk=psutil.disk_usage('/').percent,
        calls=round(voice_ping, 2) if voice_ping is not None else 'N/A',
    )
    if use_photo:
        edit_caption = getattr(sent, 'edit_caption', None)
        if edit_caption is not None:
            try:
                await edit_caption(_t('ping_pong', **args))
                return
            except Exception:
                pass
    await _fail(sent, message, 'ping_pong', **args)


HANDLERS = (
    (ping_cmd, 'ping'),
    (ping_cmd, 'alive'),
)


def register(app) -> None:
    for handler, command in HANDLERS:
        app.add_handler(MessageHandler(handler, filters.command(command)))
