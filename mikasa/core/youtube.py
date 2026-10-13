import asyncio
import functools
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import parse_qs, urlparse

from ..exceptions import DownloadError
from ..tools.models import Track
from ..logging_config import get_logger

logger = get_logger('mikasa.core.youtube')


def _is_video_id(value: str) -> bool:
    return len(value) == 11 and all(ch.isalnum() or ch in '_-' for ch in value)


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


def is_youtube(value: Optional[str]) -> bool:
    return parse_video_id(value) is not None


def parse_duration(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return max(0, int(value))
    text = str(value).strip()
    if not text or not text[0].isdigit():
        return 0
    parts = text.split(':')
    if not all(part.isdigit() for part in parts):
        return 0
    seconds = 0
    for part in parts:
        seconds = seconds * 60 + int(part)
    return seconds


def safe_stem(title: str, video_id: str) -> str:
    allowed = []
    for ch in (title or ''):
        if ch.isalnum() or ch in ' ._-':
            allowed.append(ch)
        elif ch.isspace():
            allowed.append(' ')
    cleaned = ' '.join(''.join(allowed).split())
    cleaned = cleaned[:80].strip(' .')
    if not cleaned:
        cleaned = video_id
    return f'{cleaned} [{video_id}]'


class YouTube:
    def __init__(
        self,
        search_factory: Optional[Callable[[str, int], Any]] = None,
        downloader: Optional[Callable[..., Path]] = None,
        cookies_file: Optional[str] = None,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
        api_downloader: Optional[Callable[..., Any]] = None,
        shruti_url: Optional[str] = None,
        shruti_key: Optional[str] = None,
    ) -> None:
        self._search_factory = search_factory
        self._downloader = downloader
        self._cookies_file = cookies_file
        self._api_url = (api_url or '').strip().rstrip('/')
        self._api_key = api_key or ''
        self._shruti_url = (shruti_url or '').strip().rstrip('/')
        self._shruti_key = shruti_key or ''
        if api_downloader is not None:
            self._api_downloader = api_downloader
        else:
            apis = []
            if self._api_url:
                apis.append((self._api_url, self._api_key))
            if self._shruti_url:
                apis.append((self._shruti_url, self._shruti_key))
            if apis:
                self._api_downloader = functools.partial(chained_api_download, apis)
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

    async def download(
        self,
        track: Track,
        directory: Path,
        *,
        audio_only: bool = True,
        limit_bytes: Optional[int] = None,
    ) -> Path:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        url = track.url or f'https://www.youtube.com/watch?v={track.video_id}'
        output_template = str(directory / (safe_stem(track.title, track.video_id) + '.%(ext)s'))
        if self._api_downloader is not None and track.video_id:
            api_path = await self._try_api(track, directory, audio_only, limit_bytes)
            if api_path is not None:
                return api_path
        if self._downloader is not None:
            downloader = self._downloader
        else:
            downloader = functools.partial(self._default_downloader, cookies_file=self._cookies_file)
        try:
            path = await asyncio.to_thread(downloader, url, output_template, audio_only, limit_bytes)
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
        self,
        track: Track,
        directory: Path,
        audio_only: bool,
        limit_bytes: Optional[int] = None,
    ) -> Optional[Path]:
        media_type = 'video' if (not audio_only and bool(getattr(track, 'is_video', False))) else 'audio'
        extension = '.mp4' if media_type == 'video' else '.mp3'
        destination = Path(directory) / (safe_stem(track.title, track.video_id) + extension)
        try:
            result = await self._api_downloader(track.video_id, media_type, destination)
        except Exception as exc:
            logger.warning('api download failed: %s', type(exc).__name__)
            return None
        if result is None:
            return None
        result = Path(result)
        if not result.exists() or not _within(result, Path(directory)):
            logger.warning('api download produced no file')
            return None
        size = result.stat().st_size
        if size <= 0:
            logger.warning('api download produced no file')
            try:
                result.unlink()
            except OSError:
                pass
            return None
        if limit_bytes and size > limit_bytes:
            logger.warning('api download exceeds size limit')
            try:
                result.unlink()
            except OSError:
                pass
            return None
        return result

    @staticmethod
    def _default_search_factory(query: str, limit: int) -> Any:
        from py_yt import VideosSearch
        return VideosSearch(query, limit=limit)

    @staticmethod
    def _default_downloader(url, output_template, audio_only, limit_bytes, cookies_file=None):
        import yt_dlp
        options = {
            'outtmpl': output_template,
            'quiet': True,
            'no_warnings': True,
            'noprogress': True,
            'noplaylist': True,
        }
        if audio_only:
            options['format'] = 'bestaudio/best'
        if limit_bytes:
            options['max_filesize'] = int(limit_bytes)
        if cookies_file:
            options['cookiefile'] = cookies_file
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
            return Path(ydl.prepare_filename(info))

    @staticmethod
    def _to_track(component: Any) -> Optional[Track]:
        if not isinstance(component, dict) or component.get('type') != 'video':
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
    def __init__(self, youtube, intake, max_bytes: Optional[int] = None) -> None:
        self._youtube = youtube
        self._intake = intake
        self._max_bytes = max_bytes

    async def __call__(self, chat_id: int, item, directory: Path) -> Path:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        if isinstance(item, Track):
            return await self._youtube.download(
                item,
                directory,
                audio_only=not item.is_video,
                limit_bytes=self._max_bytes,
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


async def devil_api_download(
    api_url: str,
    api_key: str,
    video_id: str,
    media_type: str,
    destination,
    timeout_sec: Optional[int] = None,
    session_factory: Optional[Callable[[], Any]] = None,
    limit_bytes: Optional[int] = None,
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
                    logger.warning('devil api failed: HTTP %s', resp.status)
                    return None
                headers = getattr(resp, 'headers', None) or {}
                content_type = headers.get('Content-Type', '') if hasattr(headers, 'get') else ''
                if content_type.startswith('application/json'):
                    logger.warning('devil api returned non-media response')
                    return None
                if limit_bytes:
                    declared = headers.get('Content-Length', '') if hasattr(headers, 'get') else ''
                    if declared and str(declared).isdigit() and int(declared) > limit_bytes:
                        logger.warning('devil api file exceeds size limit')
                        return None
                total = 0
                with open(destination, 'wb') as handle:
                    async for chunk in resp.content.iter_chunked(131072):
                        if not chunk:
                            continue
                        total += len(chunk)
                        if limit_bytes and total > limit_bytes:
                            logger.warning('devil api file exceeds size limit')
                            handle.close()
                            _remove_partial(destination)
                            return None
                        handle.write(chunk)
    except Exception as exc:
        logger.warning('devil api failed: %s', type(exc).__name__)
        _remove_partial(destination)
        return None
    if destination.exists() and destination.stat().st_size > 0:
        return destination
    _remove_partial(destination)
    return None


async def chained_api_download(
    apis,
    video_id: str,
    media_type: str,
    destination,
    session_factory: Optional[Callable[[], Any]] = None,
    limit_bytes: Optional[int] = None,
) -> Optional[Path]:
    for api_url, api_key in apis:
        result = await devil_api_download(
            api_url,
            api_key,
            video_id,
            media_type,
            destination,
            session_factory=session_factory,
            limit_bytes=limit_bytes,
        )
        if result is not None:
            return result
    return None
