import time
from pathlib import Path

from config import Config

from . import __version__
from .context import ctx
from .core.bot import MusicBot
from .core.calls import Player, PyTgCallsBackend
from .core.db import MongoDB
from .core.dir import ensure_dirs
from .core.lang import Language
from .core.telegram import Telegram
from .core.userbot import AssistantPool
from .core.watch import start_timer, start_watchers, stop_watchers
from .core.youtube import MediaResolver, YouTube
from .exceptions import MikasaError
from .logging_config import get_logger
from .plugins import load_plugins
from .tools.queue import Queue
from .tools.thumbs import Thumbnail


async def _shutdown(log, steps) -> None:
    for name, coro in steps:
        try:
            await coro
        except Exception as exc:
            log.warning("shutdown: %s failed: %s", name, type(exc).__name__)


async def on_stream_end(chat_id: int) -> None:
    controller = ctx.controller
    if controller is not None:
        await controller.advance(chat_id)


async def on_track_start(chat_id: int, item) -> None:
    if getattr(item, 'requested_by', '') != 'autoplay':
        return
    from .plugins.autoplay import announce_autoplay

    log = get_logger("mikasa")
    try:
        await announce_autoplay(chat_id, item)
    except Exception as exc:
        log.warning('autoplay announce failed for %s: %s', chat_id, type(exc).__name__)


def backend_factory(backends: dict, video_enabled: bool, state):
    backend = backends.get(state.slot)
    if backend is None:
        backend = PyTgCallsBackend(
            state,
            on_stream_end=on_stream_end,
            video_enabled=video_enabled,
        )
        backends[state.slot] = backend
    return backend


async def _auto_left_notify(chat_id: int) -> None:
    from .plugins.common import _tc

    bot = getattr(ctx, 'bot', None)
    if bot is None:
        return
    try:
        await bot.send_message(chat_id, _tc(chat_id, 'auto_left'))
    except Exception:
        pass


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
    backends = {}

    def factory(state):
        return backend_factory(backends, settings.video_enabled, state)

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

    watchers = start_watchers(settings, assistants, player, _auto_left_notify)
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
