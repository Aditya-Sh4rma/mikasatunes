import time
from pathlib import Path

from config import Config

from . import __version__
from .context import ctx
from .core.bot import MusicBot
from .core.calls import Player, make_backend_factory
from .core.db import MongoDB
from .core.dir import ensure_dirs
from .core.lang import Language
from .core.telegram import Telegram
from .core.userbot import AssistantPool
from .core.watch import start_timer, start_watchers, stop_watchers
from .core.youtube import MediaResolver, YouTube
from .logging_config import get_logger
from .plugins import load_plugins
from .plugins.autoplay import on_track_start
from .tools.queue import Queue
from .tools.thumbs import Thumbnail


async def _shutdown(log, steps) -> None:
    for name, coro in steps:
        try:
            await coro
        except Exception as exc:
            log.warning("shutdown: %s failed: %s", name, type(exc).__name__)


async def boot() -> dict:
    log = get_logger("mikasa")
    settings = Config()
    settings.validate()
    ctx.settings = settings
    ensure_dirs()
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
    factory = make_backend_factory(settings.video_enabled)

    player = Player(
        assistants,
        queue,
        factory,
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
    ctx.thumbs = Thumbnail()

    loaded = load_plugins(bot)
    log.info("plugins loaded: %s", ",".join(loaded))
    bot.watch_errors()

    try:
        await database.connect()
        await bot.boot()
        await assistants.start()
        for state in assistants.ready():
            try:
                await factory(state).start()
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
        raise
    log.info("MikasaMusic %s online", __version__)
    log.info("assistants: %s", [state.label for state in assistants.ready()])

    watchers = start_watchers(settings, assistants, player)
    watchers.append(start_timer(bot, player, language, settings.default_language or "en"))
    return {
        "settings": settings,
        "database": database,
        "bot": bot,
        "assistants": assistants,
        "player": player,
        "watchers": watchers,
    }


async def shutdown(log, state: dict) -> None:
    stop_watchers(state.get("watchers"))
    await _shutdown(log, [
        ("player", state["player"].close()),
        ("assistants", state["assistants"].stop()),
        ("bot", state["bot"].exit()),
        ("database", state["database"].close()),
    ])
