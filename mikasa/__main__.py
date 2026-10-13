import asyncio
import sys
import time
from pathlib import Path

from pyrogram import idle

from config import Config

from . import __version__
from .context import ctx
from .core.bot import MusicBot
from .core.calls import Player, PyTgCallsBackend
from .core.lang import Language
from .core.mongo import MongoDB
from .core.telegram import Telegram
from .core.userbot import AssistantPool
from .core.youtube import MediaResolver, YouTube
from .exceptions import MikasaError
from .helpers._queue import Queue
from .helpers._thumbnails import Thumbnail
from .logging_config import get_logger, setup_logging
from .plugins import load_plugins


async def _shutdown(log, steps) -> None:
    for name, coro in steps:
        try:
            await coro
        except Exception as exc:
            log.warning("shutdown: %s failed: %s", name, type(exc).__name__)


async def run() -> int:
    log = get_logger("mikasa")
    try:
        settings = Config()
        settings.validate()
    except MikasaError as exc:
        log.error("startup failed: %s", exc)
        return 2
    ctx.settings = settings
    database = MongoDB(settings.mongo_url)
    language = Language()
    bot = MusicBot(settings)
    assistants = AssistantPool(settings)
    ctx.database = database
    ctx.language = language
    ctx.bot = bot
    ctx.assistants = assistants

    youtube = YouTube(
        cookies_file=settings.cookies_file,
        api_url=settings.devil_api_url,
        api_key=settings.devil_api_key,
        shruti_url=settings.shruti_api_url,
        shruti_key=settings.shruti_api_key,
    )
    intake = Telegram(max_bytes=settings.cache_limit_mb * 1024 * 1024)
    queue = Queue(limit=settings.queue_limit)
    resolver = MediaResolver(youtube, intake, max_bytes=settings.cache_limit_mb * 1024 * 1024)
    backends = {}

    async def on_stream_end(chat_id: int) -> None:
        controller = ctx.controller
        if controller is not None:
            await controller.advance(chat_id)

    def backend_factory(state):
        backend = backends.get(state.slot)
        if backend is None:
            backend = PyTgCallsBackend(
                state,
                on_stream_end=on_stream_end,
                video_enabled=settings.video_enabled,
            )
            backends[state.slot] = backend
        return backend

    player = Player(
        assistants,
        queue,
        backend_factory,
        resolver=resolver,
        temp_root=Path('downloads'),
        database=database,
    )
    ctx.started_at = time.time()
    ctx.queue = queue
    ctx.search = youtube
    ctx.downloader = intake
    ctx.controller = player
    ctx.thumbs = Thumbnail(cache_dir='cache')

    loaded = load_plugins(bot)
    log.info("plugins loaded: %s", ",".join(loaded))

    try:
        await database.connect()
        await bot.boot()
        await assistants.start()
        for state in assistants.ready():
            try:
                await backend_factory(state).start()
            except Exception as exc:
                log.warning(
                    "assistant %s voice init failed: %s",
                    state.label,
                    type(exc).__name__,
                )
    except Exception as exc:
        log.error("startup failed: %s", type(exc).__name__)
        await _shutdown(log, [
            ("player", player.close()),
            ("assistants", assistants.stop()),
            ("bot", bot.exit()),
            ("database", database.close()),
        ])
        return 2
    log.info("MikasaMusic %s online", __version__)
    log.info("assistants: %s", [state.label for state in assistants.ready()])
    try:
        await idle()
    finally:
        await _shutdown(log, [
            ("player", player.close()),
            ("assistants", assistants.stop()),
            ("bot", bot.exit()),
            ("database", database.close()),
        ])
        log.info("shutdown complete")
    return 0


def main() -> int:
    setup_logging()
    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
