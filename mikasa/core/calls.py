import asyncio
import time
from pathlib import Path
from typing import Awaitable, Callable, Optional

from pytgcalls import PyTgCalls
from pytgcalls.exceptions import NoActiveGroupCall, NotInCallError
from pytgcalls.types import (
    AudioQuality,
    GroupCallConfig,
    MediaStream,
    StreamEnded,
    VideoQuality,
)

from ..tools.models import MediaItem, Track
from ..tools.utils import normalize_title
from ..exceptions import DownloadError
from ..tools.queue import AddResult, Queue
from ..logging_config import get_logger

logger = get_logger('mikasa.core.calls')

StreamEndHandler = Callable[[int], Awaitable[None]]

Resolver = Callable[[int, MediaItem, Path], Awaitable[Path]]


class PlaybackBackend:
    async def play(self, chat_id: int, file_path: str, is_video: bool = False) -> None:
        raise NotImplementedError

    async def play_at(
        self, chat_id: int, file_path: str, is_video: bool = False, seek_seconds: int = 0
    ) -> None:
        await self.play(chat_id, file_path, is_video)

    async def stop(self, chat_id: int) -> None:
        raise NotImplementedError

    async def leave(self, chat_id: int) -> None:
        raise NotImplementedError

    async def pause(self, chat_id: int) -> bool:
        return False

    async def resume(self, chat_id: int) -> bool:
        return False

    @property
    def ping(self):
        return None

    async def close(self) -> None:
        return None


class PyTgCallsBackend(PlaybackBackend):
    def __init__(
        self,
        state,
        on_stream_end: Optional[StreamEndHandler] = None,
        video_enabled: bool = True,
    ) -> None:
        self._state = state
        self._on_stream_end = on_stream_end
        self._video_enabled = video_enabled
        self._call: Optional[PyTgCalls] = None
        self._started = False
        self._lock = asyncio.Lock()

    @property
    def call(self) -> Optional[PyTgCalls]:
        return self._call

    @property
    def ping(self) -> Optional[float]:
        call = self._call
        if not self._started or call is None:
            return None
        try:
            return call.ping
        except Exception:
            return None

    async def start(self) -> None:
        async with self._lock:
            if self._started:
                return
            client = getattr(self._state, 'client', None)
            if client is None:
                raise RuntimeError('assistant is not connected')
            call = PyTgCalls(client)
            self._register(call)
            await call.start()
            self._call = call
            self._started = True
            await self._leave_stale(call)

    async def _leave_stale(self, call: PyTgCalls) -> None:
        try:
            active = await call.calls
        except Exception as exc:
            logger.warning('call list error: %s', type(exc).__name__)
            return
        for chat_id in list(active):
            try:
                await call.leave_call(chat_id)
            except Exception as exc:
                logger.warning('stale leave error %s: %s', chat_id, type(exc).__name__)

    def _register(self, call: PyTgCalls) -> None:
        @call.on_update()
        async def _handler(_client, update):
            if self._on_stream_end is None:
                return
            if isinstance(update, StreamEnded) and update.stream_type == StreamEnded.Type.AUDIO:
                await self._on_stream_end(update.chat_id)

    async def play(self, chat_id: int, file_path: str, is_video: bool = False) -> None:
        await self.start()
        stream = self._build_stream(file_path, is_video)
        await self._call.play(chat_id, stream, GroupCallConfig(auto_start=False))

    async def play_at(
        self, chat_id: int, file_path: str, is_video: bool = False, seek_seconds: int = 0
    ) -> None:
        await self.start()
        stream = self._build_stream(file_path, is_video, seek_seconds)
        await self._call.play(chat_id, stream, GroupCallConfig(auto_start=False))

    def _build_stream(
        self, file_path: str, is_video: bool, seek_seconds: int = 0
    ) -> MediaStream:
        ffmpeg_parameters = f'-ss {int(seek_seconds)}' if int(seek_seconds) > 1 else None
        if is_video and self._video_enabled:
            return MediaStream(
                file_path,
                audio_parameters=AudioQuality.HIGH,
                video_parameters=VideoQuality.HD_720p,
                ffmpeg_parameters=ffmpeg_parameters,
            )
        return MediaStream(
            file_path,
            audio_parameters=AudioQuality.HIGH,
            video_parameters=VideoQuality.HD_720p,
            video_flags=MediaStream.Flags.IGNORE,
            audio_flags=MediaStream.Flags.REQUIRED,
            ffmpeg_parameters=ffmpeg_parameters,
        )

    async def stop(self, chat_id: int) -> None:
        return None

    async def leave(self, chat_id: int) -> None:
        if not self._started or self._call is None:
            return
        try:
            await self._call.leave_call(chat_id)
        except (NoActiveGroupCall, NotInCallError):
            pass

    async def pause(self, chat_id: int) -> bool:
        await self.start()
        try:
            return await self._call.pause(chat_id)
        except NotInCallError:
            return False

    async def resume(self, chat_id: int) -> bool:
        await self.start()
        try:
            return await self._call.resume(chat_id)
        except NotInCallError:
            return False

    async def close(self) -> None:
        async with self._lock:
            call = self._call
            self._call = None
            self._started = False
            if call is None:
                return
            try:
                active = await call.calls
            except Exception as exc:
                logger.warning('call list error: %s', type(exc).__name__)
                active = {}
            for chat_id in list(active):
                try:
                    await call.leave_call(chat_id)
                except Exception as exc:
                    logger.warning('leave error %s: %s', chat_id, type(exc).__name__)


async def on_stream_end(chat_id: int) -> None:
    from ..context import ctx

    controller = ctx.controller
    if controller is not None:
        await controller.advance(chat_id)


def make_backend_factory(video_enabled: bool):
    backends = {}

    def factory(state):
        backend = backends.get(state.slot)
        if backend is None:
            backend = PyTgCallsBackend(
                state,
                on_stream_end=on_stream_end,
                video_enabled=video_enabled,
            )
            backends[state.slot] = backend
        return backend

    return factory


class Player:
    def __init__(
        self,
        pool,
        queue: Queue,
        backend_factory: Callable[[object], PlaybackBackend],
        resolver: Optional[Resolver] = None,
        temp_root: Optional[Path] = None,
        database=None,
        youtube=None,
        duration_limit: int = 0,
        on_track_start=None,
    ) -> None:
        self._pool = pool
        self._queue = queue
        self._backend_factory = backend_factory
        self._resolver = resolver
        self._database = database
        self._youtube = youtube
        self._duration_limit = max(0, int(duration_limit or 0))
        self._on_track_start = on_track_start
        self._temp_root = Path(temp_root) if temp_root else Path('downloads')
        self._current: dict[int, MediaItem] = {}
        self._paused: set[int] = set()
        self._positions: dict[int, list] = {}
        self._backends: dict[int, PlaybackBackend] = {}
        self._owned: dict[int, set] = {}
        self._locks: dict[int, asyncio.Lock] = {}
        self._loop: dict[int, int] = {}
        self._autoplay: set[int] = set()
        self._last: dict[int, MediaItem] = {}
        self._recent: dict[int, dict] = {}
        self._warned: dict[int, tuple] = {}
        self._closed = False

    def _log_once(self, chat_id: int, reason: str) -> bool:
        now = time.monotonic()
        last_reason, last_time = self._warned.get(chat_id, ('', 0.0))
        if last_reason == reason and now - last_time < 300:
            return False
        self._warned[chat_id] = (reason, now)
        return True

    def _lock(self, chat_id: int) -> asyncio.Lock:
        lock = self._locks.get(chat_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[chat_id] = lock
        return lock

    def _backend(self, state) -> PlaybackBackend:
        backend = self._backends.get(state.slot)
        if backend is None:
            backend = self._backend_factory(state)
            self._backends[state.slot] = backend
        return backend

    async def current(self, chat_id: int) -> Optional[MediaItem]:
        return self._current.get(chat_id)

    def is_paused(self, chat_id: int) -> bool:
        return chat_id in self._paused

    def position(self, chat_id: int) -> int:
        entry = self._positions.get(chat_id)
        if not entry or self._current.get(chat_id) is None:
            return 0
        offset, stamp = entry
        if stamp is None:
            return int(offset)
        return int(offset + (time.monotonic() - stamp))

    def active_chats(self) -> list:
        return sorted(self._current.keys())

    def voice_ping(self) -> Optional[float]:
        for backend in self._backends.values():
            try:
                ping = backend.ping
            except Exception:
                continue
            if ping is not None:
                return ping
        return None

    async def participants(self, chat_id: int) -> Optional[int]:
        backend = self._current_backend(chat_id)
        if backend is None:
            return None
        call = getattr(backend, 'call', None)
        if call is None:
            return None
        get_participants = getattr(call, 'get_participants', None)
        if get_participants is None:
            return None
        try:
            people = await get_participants(chat_id)
        except Exception:
            return None
        if people is None:
            return None
        try:
            return len(people)
        except TypeError:
            return None

    async def _stored_slot(self, chat_id: int) -> Optional[int]:
        database = self._database
        if database is None:
            return None
        try:
            slots = self._pool.slots()
        except Exception:
            return None
        try:
            return await database.assistant_slot(chat_id, slots)
        except Exception as exc:
            logger.warning('assistant lookup failed for %s: %s', chat_id, type(exc).__name__)
            return None

    async def _store_slot(self, chat_id: int, slot: int) -> None:
        database = self._database
        if database is None:
            return
        try:
            await database.set_assistant_slot(chat_id, slot)
        except Exception as exc:
            logger.warning('assistant store failed for %s: %s', chat_id, type(exc).__name__)

    async def _claim(self, chat_id: int):
        return await self._pool.claim_specific(chat_id, await self._stored_slot(chat_id))

    def temp_dir(self, chat_id: int) -> Path:
        return self._temp_root / str(chat_id)

    def own(self, chat_id: int, item: MediaItem) -> None:
        path = getattr(item, 'file_path', None)
        if path and self._is_owned_path(str(path)):
            self._owned.setdefault(chat_id, set()).add(str(path))

    async def enqueue(self, chat_id: int, item: MediaItem) -> AddResult:
        return await self._queue.add(chat_id, item)

    async def start(self, chat_id: int) -> bool:
        async with self._lock(chat_id):
            if self._current.get(chat_id) is not None:
                return False
            state = await self._claim(chat_id)
            if state is None:
                return False
            try:
                played = await self._advance_locked(chat_id, state)
            except NoActiveGroupCall:
                await self._pool.release(chat_id)
                raise
            if not played:
                await self._pool.release(chat_id)
            return played

    def loop_count(self, chat_id: int) -> int:
        return self._loop.get(chat_id, 0)

    def set_loop(self, chat_id: int, count: int) -> int:
        try:
            count = int(count)
        except (TypeError, ValueError):
            count = 0
        count = max(0, min(10, count))
        if count:
            self._loop[chat_id] = count
        else:
            self._loop.pop(chat_id, None)
        return count

    def autoplay_enabled(self, chat_id: int) -> bool:
        return chat_id in self._autoplay

    def set_autoplay(self, chat_id: int, enabled: bool) -> bool:
        if enabled:
            self._autoplay.add(chat_id)
        else:
            self._autoplay.discard(chat_id)
            self._recent.pop(chat_id, None)
        return enabled

    async def _consume_loop(self, chat_id: int) -> bool:
        remaining = self._loop.get(chat_id, 0)
        if remaining <= 0:
            return False
        remaining -= 1
        if remaining:
            self._loop[chat_id] = remaining
        else:
            self._loop.pop(chat_id, None)
        return True

    async def _next_autoplay(self, chat_id: int) -> Optional[MediaItem]:
        if chat_id not in self._autoplay:
            return None
        youtube = self._youtube
        if youtube is None:
            return None
        last = self._last.get(chat_id)
        if not isinstance(last, Track) or not last.video_id:
            return None
        recent = self._recent.setdefault(chat_id, {})
        recent.setdefault(last.video_id, normalize_title(last.title))
        seen_ids = set(recent)
        seen_titles = {title for title in recent.values() if title}
        candidates: list = []
        try:
            candidates = await youtube.related(last.video_id, limit=10)
        except Exception as exc:
            logger.warning('autoplay related failed for %s: %s', chat_id, type(exc).__name__)
            candidates = []
        picked = self._pick_autoplay(candidates, seen_ids, seen_titles)
        if picked is None:
            try:
                candidates = await youtube.search(last.title, limit=10)
            except Exception as exc:
                logger.warning('autoplay search failed for %s: %s', chat_id, type(exc).__name__)
                return None
            picked = self._pick_autoplay(candidates, seen_ids, seen_titles)
        if picked is None:
            return None
        picked.requested_by = 'autoplay'
        recent[picked.video_id] = normalize_title(getattr(picked, 'title', ''))
        while len(recent) > 30:
            recent.pop(next(iter(recent)))
        return picked

    def _pick_autoplay(self, candidates, seen_ids, seen_titles) -> Optional[MediaItem]:
        for track in candidates or []:
            video_id = getattr(track, 'video_id', '') or ''
            if not video_id or video_id in seen_ids:
                continue
            normalized = normalize_title(getattr(track, 'title', ''))
            if normalized and normalized in seen_titles:
                continue
            if self._duration_limit and (getattr(track, 'duration_seconds', 0) or 0) > self._duration_limit:
                continue
            return track
        return None

    async def advance(self, chat_id: int) -> bool:
        async with self._lock(chat_id):
            current = self._current.get(chat_id)
            if current is None:
                return False
            if await self._consume_loop(chat_id):
                state = self._state_for(chat_id)
                if state is None:
                    await self._cleanup_current(chat_id)
                    self._paused.discard(chat_id)
                    return False
                backend = self._backend(state)
                file_path = getattr(current, 'file_path', '') or ''
                try:
                    await backend.play_at(
                        chat_id,
                        str(file_path),
                        bool(getattr(current, 'is_video', False)),
                        0,
                    )
                except Exception as exc:
                    logger.warning('replay failed for %s: %s', chat_id, type(exc).__name__)
                    await self._cleanup_current(chat_id)
                    self._paused.discard(chat_id)
                    await self._pool.release(chat_id)
                    return False
                self._positions[chat_id] = [0.0, time.monotonic()]
                self._paused.discard(chat_id)
                return True
            await self._cleanup_current(chat_id)
            self._paused.discard(chat_id)
            state = self._state_for(chat_id) or await self._claim(chat_id)
            if state is None:
                return False
            try:
                played = await self._advance_locked(chat_id, state)
            except NoActiveGroupCall:
                await self._pool.release(chat_id)
                return False
            if not played:
                await self._safe_leave(self._current_backend(chat_id), chat_id)
                await self._pool.release(chat_id)
            return played

    async def skip(self, chat_id: int) -> bool:
        async with self._lock(chat_id):
            if self._current.get(chat_id) is None:
                return False
            backend = self._current_backend(chat_id)
            if backend is not None:
                await self._safe_stop(backend, chat_id)
            await self._cleanup_current(chat_id)
            self._paused.discard(chat_id)
            state = self._state_for(chat_id)
            if state is None:
                return False
            try:
                played = await self._advance_locked(chat_id, state)
            except NoActiveGroupCall:
                await self._pool.release(chat_id)
                return False
            if not played:
                await self._safe_leave(self._current_backend(chat_id), chat_id)
                await self._pool.release(chat_id)
            return played

    async def stop(self, chat_id: int) -> bool:
        async with self._lock(chat_id):
            backend = self._current_backend(chat_id)
            if backend is not None:
                await self._safe_stop(backend, chat_id)
                await self._safe_leave(backend, chat_id)
            await self._cleanup_current(chat_id)
            await self._discard_queued(chat_id)
            await self._queue.clear(chat_id)
            await self._pool.release(chat_id)
            self._paused.discard(chat_id)
            self._loop.pop(chat_id, None)
            self._autoplay.discard(chat_id)
            self._last.pop(chat_id, None)
            self._recent.pop(chat_id, None)
            return True

    async def pause(self, chat_id: int) -> bool:
        backend = self._current_backend(chat_id)
        if backend is None:
            return False
        paused = await backend.pause(chat_id)
        if paused:
            self._paused.add(chat_id)
            self._positions[chat_id] = [float(self.position(chat_id)), None]
        return paused

    async def resume(self, chat_id: int) -> bool:
        backend = self._current_backend(chat_id)
        if backend is None:
            return False
        resumed = await backend.resume(chat_id)
        if resumed:
            self._paused.discard(chat_id)
            self._positions[chat_id] = [float(self.position(chat_id)), time.monotonic()]
        return resumed

    async def seek(self, chat_id: int, seconds: int) -> bool:
        async with self._lock(chat_id):
            item = self._current.get(chat_id)
            if item is None:
                return False
            backend = self._current_backend(chat_id)
            if backend is None:
                return False
            file_path = getattr(item, 'file_path', '') or ''
            if not file_path or not Path(file_path).exists():
                return False
            try:
                await backend.play_at(
                    chat_id,
                    str(file_path),
                    bool(getattr(item, 'is_video', False)),
                    int(seconds),
                )
            except Exception as exc:
                logger.warning('seek error %s: %s', chat_id, type(exc).__name__)
                return False
            self._positions[chat_id] = [float(max(0, int(seconds))), time.monotonic()]
            return True

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for chat_id in list(self._current):
            try:
                await self.stop(chat_id)
            except Exception as exc:
                logger.warning('close stop error %s: %s', chat_id, type(exc).__name__)
        for backend in list(self._backends.values()):
            try:
                await backend.close()
            except Exception as exc:
                logger.warning('backend close error: %s', type(exc).__name__)
        self._cleanup_temp_root()
        self._current.clear()
        self._paused.clear()
        self._positions.clear()
        self._backends.clear()
        self._owned.clear()
        self._loop.clear()
        self._autoplay.clear()
        self._last.clear()
        self._recent.clear()
        self._warned.clear()

    def _cleanup_temp_root(self) -> None:
        if not self._temp_root.exists():
            return
        for path in sorted(self._temp_root.rglob('*'), reverse=True):
            if path.is_dir():
                try:
                    path.rmdir()
                except OSError:
                    pass
        try:
            self._temp_root.rmdir()
        except OSError:
            pass

    async def _advance_locked(self, chat_id: int, state) -> bool:
        backend = self._backend(state)
        while True:
            item = await self._queue.pop_next(chat_id)
            if item is None:
                item = await self._next_autoplay(chat_id)
                if item is None:
                    return False
            try:
                path = await self._ensure_file(chat_id, item)
                await backend.play(chat_id, str(path), bool(getattr(item, 'is_video', False)))
            except NoActiveGroupCall:
                await self._discard_file(chat_id, item)
                raise
            except Exception as exc:
                if self._log_once(chat_id, type(exc).__name__):
                    logger.warning('playback failed for %s: %s', chat_id, type(exc).__name__)
                await self._discard_file(chat_id, item)
                continue
            self._current[chat_id] = item
            self._last[chat_id] = item
            self._paused.discard(chat_id)
            self._positions[chat_id] = [0.0, time.monotonic()]
            await self._store_slot(chat_id, state.slot)
            callback = self._on_track_start
            if callback is not None:
                try:
                    await callback(chat_id, item)
                except Exception as exc:
                    logger.warning('track start hook failed for %s: %s', chat_id, type(exc).__name__)
            return True

    async def _ensure_file(self, chat_id: int, item: MediaItem) -> Path:
        existing = getattr(item, 'file_path', None)
        if existing and Path(existing).exists():
            return Path(existing)
        if self._resolver is None:
            raise DownloadError('no resolver configured')
        directory = self._temp_root / str(chat_id)
        path = Path(await self._resolver(chat_id, item, directory))
        if not path.exists():
            raise DownloadError('resolver produced no file')
        item.file_path = str(path)
        try:
            inside_chat_dir = path.resolve().relative_to(
                (self._temp_root / str(chat_id)).resolve()
            )
        except (ValueError, OSError):
            inside_chat_dir = None
        if inside_chat_dir is not None:
            self._owned.setdefault(chat_id, set()).add(str(path))
        return path

    async def _cleanup_current(self, chat_id: int) -> None:
        item = self._current.pop(chat_id, None)
        self._positions.pop(chat_id, None)
        if item is not None:
            await self._discard_file(chat_id, item)

    async def _discard_queued(self, chat_id: int) -> None:
        for item in await self._queue.items(chat_id):
            await self._discard_file(chat_id, item)

    async def _discard_file(self, chat_id: int, item: MediaItem) -> None:
        path = getattr(item, 'file_path', None)
        if not path:
            return
        owned = self._owned.get(chat_id)
        if not owned or path not in owned:
            return
        owned.discard(path)
        if self._is_owned_path(path):
            try:
                Path(path).unlink()
            except OSError:
                pass
        item.file_path = None

    def _is_owned_path(self, path: str) -> bool:
        try:
            Path(path).resolve().relative_to(self._temp_root.resolve())
            return True
        except ValueError:
            return False

    def _current_backend(self, chat_id: int):
        slot = self._pool.claimed_slot(chat_id)
        if slot is None:
            return None
        return self._backends.get(slot)

    def _state_for(self, chat_id: int):
        slot = self._pool.claimed_slot(chat_id)
        if slot is None:
            return None
        return self._pool.get(slot)

    async def _safe_stop(self, backend, chat_id: int) -> None:
        try:
            await backend.stop(chat_id)
        except Exception as exc:
            logger.warning('stop error %s: %s', chat_id, type(exc).__name__)

    async def _safe_leave(self, backend, chat_id: int) -> None:
        if backend is None:
            return
        try:
            await backend.leave(chat_id)
        except Exception as exc:
            logger.warning('leave error %s: %s', chat_id, type(exc).__name__)
