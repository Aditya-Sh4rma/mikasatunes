import asyncio
import sys
import time
from pathlib import Path

from pyrogram import idle

from config import Config

from . import __version__
from .context import ctx
from .core.bot import MusicBot
from .core.cache import prune_cache
from .core.calls import Player, PyTgCallsBackend
from .core.dir import ensure_dirs
from .core.watch import start_timer, start_watchers, stop_watchers
from .core.lang import Language
from .core.db import MongoDB
from .core.telegram import Telegram
from .core.userbot import AssistantPool
from .core.youtube import MediaResolver, YouTube
from .exceptions import MikasaError
from .tools.queue import Queue
from .tools.thumbs import Thumbnail
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
    try:
        ensure_dirs()
    except RuntimeError as exc:
        log.error("startup failed: %s", exc)
        return 2
    report = prune_cache()
    if report["removed"]:
        log.info("pruned %d stale thumbnails", report["removed"])
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
        api_url=settings.mikasa_api_url,
        api_key=settings.mikasa_api_key,
    )
    intake = Telegram()
    queue = Queue(limit=settings.queue_limit)
    resolver = MediaResolver(youtube, intake)
    backends = {}

    async def on_stream_end(chat_id: int) -> None:
        controller = ctx.controller
        if controller is not None:
            await controller.advance(chat_id)

    async def on_track_start(chat_id: int, item) -> None:
        if getattr(item, 'requested_by', '') != 'autoplay':
            return
        from .plugins.autoplay import announce_autoplay

        try:
            await announce_autoplay(chat_id, item)
        except Exception as exc:
            log.warning('autoplay announce failed for %s: %s', chat_id, type(exc).__name__)

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
        youtube=youtube,
        duration_limit=settings.duration_limit,
        on_track_start=on_track_start,
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

    async def _auto_left_notify(chat_id: int) -> None:
        from .plugins.common import _tc

        try:
            await bot.send_message(chat_id, _tc(chat_id, 'auto_left'))
        except Exception:
            pass

    watchers = start_watchers(settings, assistants, player, _auto_left_notify)
    watchers.append(start_timer(bot, player, language, settings.default_language or "en"))
    try:
        await idle()
    finally:
        stop_watchers(watchers)
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
