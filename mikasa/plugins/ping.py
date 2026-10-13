from pyrogram import filters
from pyrogram.handlers import MessageHandler

from ..context import ctx
from ..helpers._utilities import format_uptime
from .common import _fail, _t

async def ping_cmd(client, message) -> None:
    import time

    import psutil

    started = time.time()
    sent = await message.reply_text(_t('pinging'))
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
    await _fail(
        sent,
        message,
        'ping_pong',
        latency=latency,
        uptime=uptime,
        cpu=psutil.cpu_percent(interval=0),
        ram=psutil.virtual_memory().percent,
        disk=psutil.disk_usage('/').percent,
        calls=round(voice_ping, 2) if voice_ping is not None else 'N/A',
    )


HANDLERS = (
    (ping_cmd, 'ping'),
    (ping_cmd, 'alive'),
)


def register(app) -> None:
    for handler, command in HANDLERS:
        app.add_handler(MessageHandler(handler, filters.command(command)))
