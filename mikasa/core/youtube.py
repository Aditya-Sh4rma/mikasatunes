import asyncio
import functools
import inspect
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import parse_qs, urlparse

from ..exceptions import DownloadError
from ..logging_config import get_logger
from ..tools.models import Track
from ..tools.utils import parse_duration, safe_stem

logger = get_logger('mikasa.core.youtube')


class _YdlLogger:
    def __init__(self) -> None:
        self.last = ''

    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        if not self.last:
            self.last = str(msg).strip().splitlines()[0]


def parse_video_id(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    candidate = value.strip()
    if _is_video_id(candidate):
        return candidate
    lowered = candidate.lower()
    if 'youtube.com' not in lowered and 'youtu.be' not in lowered:
        return None
    parsed = urlparse(candidate if '://' in candidate else 'https://' + candidate)
    host = parsed.netloc.lower()
    if host.startswith('www.'):
        host = host[4:]
    if host.startswith('m.'):
        host = host[2:]
    if host.startswith('music.'):
        host = host[6:]
    if host == 'youtu.be':
        vid = parsed.path.lstrip('/').split('/')[0]
        return vid if _is_video_id(vid) else None
    if not host.endswith('youtube.com'):
        return None
    if parsed.path == '/watch':
        vid = (parse_qs(parsed.query).get('v') or [''])[0]
        return vid if _is_video_id(vid) else None
    parts = [part for part in parsed.path.split('/') if part]
    if len(parts) >= 2 and parts[0] in ('embed', 'v', 'live', 'shorts'):
        return parts[1] if _is_video_id(parts[1]) else None
    return None


def parse_playlist_id(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    candidate = value.strip()
    if '://' not in candidate:
        candidate = 'https://' + candidate
    try:
        parsed = urlparse(candidate)
    except ValueError:
        return None
    if parsed.scheme not in ('http', 'https'):
        return None
    host = parsed.netloc.lower()
    if host.startswith('www.'):
        host = host[4:]
    if host.startswith('m.'):
        host = host[2:]
    if host.startswith('music.'):
        host = host[6:]
    if not host.endswith('youtube.com'):
        return None
    if parsed.path not in ('/playlist', '/watch'):
        return None
    candidates = parse_qs(parsed.query).get('list') or []
    for raw in candidates:
        cleaned = (raw or '').strip()
        if 2 <= len(cleaned) <= 64 and all(
            ch.isalnum() or ch in '_-' for ch in cleaned
        ):
            return cleaned
    return None


def is_playlist_url(value: Optional[str]) -> bool:
    return parse_playlist_id(value) is not None


def _is_video_id(value: str) -> bool:
    return len(value) == 11 and all(ch.isalnum() or ch in '_-' for ch in value)


def is_youtube(value: Optional[str]) -> bool:
    return parse_video_id(value) is not None


class YouTube:
    def __init__(
        self,
        search_factory: Optional[Callable[[str, int], Any]] = None,
        downloader: Optional[Callable[..., Path]] = None,
        cookies_file: Optional[str] = None,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
        api_downloader: Optional[Callable[..., Any]] = None,
        cache_dir: str = 'downloads',
        playlist_factory: Optional[Callable[[str], Any]] = None,
        related_factory: Optional[Callable[[str, int], Any]] = None,
    ) -> None:
        self._search_factory = search_factory
        self._playlist_factory = playlist_factory
        self._related_factory = related_factory
        self._downloader = downloader
        self._cookies_file = cookies_file
        self._api_url = (api_url or '').strip().rstrip('/')
        self._api_key = api_key or ''
        self._cache_dir = Path(cache_dir)
        if api_downloader is not None:
            self._api_downloader = api_downloader
        elif self._api_url:
            self._api_downloader = functools.partial(api_download, self._api_url, self._api_key)
        else:
            self._api_downloader = None

    async def search(self, query: str, limit: int = 5) -> list[Track]:
        query = (query or '').strip()
        if not query:
            raise ValueError('search query is empty')
        if limit < 1:
            return []
        factory = self._search_factory or self._default_search_factory
        try:
            searcher = factory(query, limit)
            result = await searcher.next()
        except Exception as exc:
            raise DownloadError(f'search failed: {type(exc).__name__}') from exc
        components = result.get('result', []) if isinstance(result, dict) else []
        tracks: list[Track] = []
        for component in components:
            track = self._to_track(component)
            if track is not None:
                tracks.append(track)
            if len(tracks) >= limit:
                break
        return tracks

    async def playlist(self, url: str, limit: int = 20) -> list[Track]:
        url = (url or '').strip()
        if not url or limit < 1:
            return []
        factory = self._playlist_factory or self._default_playlist_factory
        try:
            result = factory(url)
            if inspect.isawaitable(result):
                result = await result
        except Exception as exc:
            raise DownloadError(f'playlist failed: {type(exc).__name__}') from exc
        videos = result.get('videos', []) if isinstance(result, dict) else []
        tracks: list[Track] = []
        for video in videos:
            track = self._video_to_track(video) if isinstance(video, dict) else None
            if track is not None:
                tracks.append(track)
            if len(tracks) >= limit:
                break
        return tracks

    async def related(self, video_id: str, limit: int = 10) -> list[Track]:
        video_id = (video_id or '').strip()
        if not video_id or limit < 1:
            return []
        factory = self._related_factory or self._default_related_factory
        try:
            result = factory(video_id, limit)
            if inspect.isawaitable(result):
                result = await result
        except Exception:
            return []
        components = result.get('result', []) if isinstance(result, dict) else []
        tracks: list[Track] = []
        for component in components:
            track = self._to_track(component)
            if track is not None:
                tracks.append(track)
            if len(tracks) >= limit:
                break
        return tracks

    def _cached_path(self, track: Track, audio_only: bool) -> Optional[Path]:
        if not track.video_id:
            return None
        video = not audio_only and bool(getattr(track, 'is_video', False))
        extension = '.mp4' if video else '.mp3'
        return self._cache_dir / f'{track.video_id}{extension}'

    @staticmethod
    def _usable(path: Optional[Path]) -> bool:
        return bool(path) and path.exists() and path.stat().st_size > 0

    async def download(
        self,
        track: Track,
        directory: Path,
        *,
        audio_only: bool = True,
    ) -> Path:
        cached = self._cached_path(track, audio_only)
        if self._usable(cached):
            return cached
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        if self._api_downloader is not None and track.video_id:
            api_path = await self._try_api(track, audio_only, cached)
            if api_path is not None:
                return api_path
        url = track.url or f'https://www.youtube.com/watch?v={track.video_id}'
        output_template = str(directory / (safe_stem(track.title, track.video_id) + '.%(ext)s'))
        if self._downloader is not None:
            call = (self._downloader, url, output_template, audio_only)
        else:
            call = (self._default_downloader, url, output_template, audio_only, self._cookies_file)
        try:
            path = await asyncio.to_thread(*call)
        except DownloadError:
            raise
        except Exception as exc:
            raise DownloadError(f'download failed: {type(exc).__name__}') from exc
        path = Path(path)
        if not path.exists():
            raise DownloadError('downloaded file is missing')
        if not _within(path, directory):
            raise DownloadError('downloaded file escaped the target directory')
        return path

    async def _try_api(
        self, track: Track, audio_only: bool, destination: Path
    ) -> Optional[Path]:
        media_type = 'video' if (not audio_only and bool(getattr(track, 'is_video', False))) else 'audio'
        try:
            result = await self._api_downloader(track.video_id, media_type, destination)
        except Exception as exc:
            logger.warning('api download failed: %s', type(exc).__name__)
            return None
        if result is None:
            return None
        result = Path(result)
        if not result.exists() or not _within(result, self._cache_dir):
            logger.warning('api download produced no file')
            return None
        if result.stat().st_size <= 0:
            logger.warning('api download produced no file')
            try:
                result.unlink()
            except OSError:
                pass
            return None
        return result

    @staticmethod
    async def _default_related_factory(video_id: str, limit: int) -> Any:
        from py_yt import Recommendations
        return await Recommendations.get_related(
            f'https://www.youtube.com/watch?v={video_id}',
            limit=limit,
        )

    @staticmethod
    def _default_search_factory(query: str, limit: int) -> Any:
        from py_yt import VideosSearch
        return VideosSearch(query, limit=limit)

    @staticmethod
    def _default_playlist_factory(url: str) -> Any:
        from py_yt import Playlist
        return Playlist.get(url)

    @staticmethod
    def _default_downloader(url, output_template, audio_only, cookies_file=None):
        import yt_dlp
        output = _YdlLogger()
        options = {
            'outtmpl': output_template,
            'quiet': True,
            'no_warnings': True,
            'noprogress': True,
            'noplaylist': True,
            'logger': output,
        }
        if audio_only:
            options['format'] = 'bestaudio/best'
        if cookies_file:
            options['cookiefile'] = cookies_file
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=True)
                return Path(ydl.prepare_filename(info))
        except Exception as exc:
            reason = output.last or type(exc).__name__
            raise DownloadError(reason[:160]) from exc

    @staticmethod
    def _to_track(component: Any) -> Optional[Track]:
        if not isinstance(component, dict) or component.get('type') != 'video':
            return None
        return YouTube._video_to_track(component)

    @staticmethod
    def _video_to_track(component: Any) -> Optional[Track]:
        if not isinstance(component, dict):
            return None
        video_id = component.get('id')
        if not video_id:
            return None
        thumbnails = component.get('thumbnails') or []
        thumbnail = ''
        if thumbnails and isinstance(thumbnails[-1], dict):
            thumbnail = thumbnails[-1].get('url', '')
        channel = component.get('channel') or {}
        name = channel.get('name', '') if isinstance(channel, dict) else ''
        return Track(
            video_id=str(video_id),
            title=str(component.get('title') or video_id),
            duration_seconds=parse_duration(component.get('duration')),
            url=f'https://www.youtube.com/watch?v={video_id}',
            thumbnail=thumbnail,
            channel=str(name),
        )


class MediaResolver:
    def __init__(self, youtube, intake) -> None:
        self._youtube = youtube
        self._intake = intake

    async def __call__(self, chat_id: int, item, directory: Path) -> Path:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        if isinstance(item, Track):
            return await self._youtube.download(
                item,
                directory,
                audio_only=not item.is_video,
            )
        existing = getattr(item, 'file_path', None)
        if existing and Path(existing).exists():
            return Path(existing)
        url = getattr(item, 'url', '')
        if url:
            media = await self._intake.from_url(
                url,
                directory,
                title=getattr(item, 'title', None),
                is_video=bool(getattr(item, 'is_video', False)),
            )
            return Path(media.file_path)
        raise DownloadError('cannot resolve media item')


def _within(path: Path, directory: Path) -> bool:
    try:
        path.resolve().relative_to(directory.resolve())
    except ValueError:
        return False
    return True


def _remove_partial(path: Path) -> None:
    try:
        Path(path).unlink()
    except OSError:
        pass


async def api_download(
    api_url: str,
    api_key: str,
    video_id: str,
    media_type: str,
    destination,
    timeout_sec: Optional[int] = None,
    session_factory: Optional[Callable[[], Any]] = None,
) -> Optional[Path]:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if timeout_sec is None:
        timeout_sec = 600 if media_type == 'video' else 300
    if session_factory is None:
        import aiohttp
        session_factory = aiohttp.ClientSession
    else:
        import aiohttp
    timeout = aiohttp.ClientTimeout(total=timeout_sec)
    url = api_url.rstrip('/') + '/download'
    params = {'url': video_id, 'type': media_type, 'api_key': api_key or ''}
    try:
        async with session_factory() as session:
            async with session.get(url, params=params, timeout=timeout) as resp:
                if resp.status != 200:
                    logger.warning('api failed: HTTP %s', resp.status)
                    return None
                headers = getattr(resp, 'headers', None) or {}
                content_type = headers.get('Content-Type', '') if hasattr(headers, 'get') else ''
                if content_type.startswith('application/json'):
                    logger.warning('api returned non-media response')
                    return None
                with open(destination, 'wb') as handle:
                    async for chunk in resp.content.iter_chunked(131072):
                        if chunk:
                            handle.write(chunk)
    except Exception as exc:
        logger.warning('api failed: %s', type(exc).__name__)
        _remove_partial(destination)
        return None
    if destination.exists() and destination.stat().st_size > 0:
        return destination
    _remove_partial(destination)
    return None
