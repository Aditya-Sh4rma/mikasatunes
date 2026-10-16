# Copyright (c) 2026 Aditya-Sh4rma
# Licensed under the MIT License.
# This file is part of MikasaMusic


import hashlib
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import urlparse

from ..exceptions import DownloadError, UnsupportedMedia
from ..tools.models import Media
from .youtube import is_youtube, safe_stem

DIRECT_MEDIA_EXTENSIONS = {
    '.aac', '.flac', '.m4a', '.m4v', '.mkv', '.mov', '.mp3', '.mp4',
    '.ogg', '.opus', '.wav', '.webm',
}

Downloader = Callable[[str, Path], Awaitable[Path]]


def is_direct_url(url: Optional[str]) -> bool:
    if not url:
        return False
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return False
    if parsed.scheme not in ('http', 'https'):
        return False
    if not parsed.hostname:
        return False
    if parsed.username or parsed.password:
        return False
    return not is_youtube(url)


def extension_of(url: str) -> str:
    return Path(urlparse(url).path).suffix.lower()


def is_supported_url(url: Optional[str]) -> bool:
    if not url:
        return False
    if is_youtube(url):
        return True
    if not is_direct_url(url):
        return False
    return extension_of(url) in DIRECT_MEDIA_EXTENSIONS


def _url_id(url: str) -> str:
    return hashlib.sha1(url.encode('utf-8')).hexdigest()[:16]


def _telegram_media(message: Any):
    for attr, is_video in (('audio', False), ('voice', False), ('video', True)):
        item = getattr(message, attr, None)
        if item is not None:
            return item, is_video
    document = getattr(message, 'document', None)
    if document is not None:
        mime = (getattr(document, 'mime_type', '') or '').lower()
        if mime.startswith('audio/'):
            return document, False
        if mime.startswith('video/'):
            return document, True
    return None, False


class Telegram:
    def __init__(
        self,
        downloader: Optional[Downloader] = None,
    ) -> None:
        self._downloader = downloader

    async def from_message(self, message: Any, client: Any, directory: Path) -> Media:
        item, is_video = _telegram_media(message)
        if item is None:
            raise UnsupportedMedia('message has no supported audio or video')
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        file_id = getattr(item, 'file_id', None) or getattr(item, 'file_unique_id', '')
        if not file_id:
            raise UnsupportedMedia('media has no file identifier')
        title = getattr(item, 'title', None) or getattr(item, 'file_name', None) or 'media'
        extension = Path(getattr(item, 'file_name', '') or '').suffix
        if not extension:
            extension = '.mp4' if is_video else '.mp3'
        destination = directory / (safe_stem(str(title), _url_id(str(file_id))) + extension)
        try:
            downloaded = await client.download_media(message, file_name=str(destination))
        except Exception as exc:
            raise DownloadError(f'telegram download failed: {type(exc).__name__}') from exc
        path = Path(downloaded or destination)
        if not path.exists():
            raise DownloadError('telegram download produced no file')
        duration = int(getattr(item, 'duration', 0) or 0)
        return Media(
            file_id=str(file_id),
            title=str(title),
            duration_seconds=duration,
            file_path=str(path),
            requested_by=_requester(message),
            is_video=is_video,
            message_id=int(getattr(message, 'id', 0) or 0),
        )

    async def from_url(
        self,
        url: str,
        directory: Path,
        *,
        title: Optional[str] = None,
        is_video: bool = False,
    ) -> Media:
        if not is_supported_url(url):
            raise UnsupportedMedia('unsupported media url')
        if self._downloader is None:
            raise DownloadError('no direct url downloader configured')
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        extension = extension_of(url) or ('.mp4' if is_video else '.mp3')
        identifier = _url_id(url)
        stem = safe_stem(title or Path(urlparse(url).path).stem or 'media', identifier)
        destination = directory / (stem + extension)
        try:
            path = await self._downloader(url, destination)
        except Exception as exc:
            raise DownloadError(f'url download failed: {type(exc).__name__}') from exc
        path = Path(path)
        if not path.exists():
            raise DownloadError('url download produced no file')
        return Media(
            file_id=identifier,
            title=str(title or path.stem),
            duration_seconds=0,
            file_path=str(path),
            url=url,
            is_video=is_video,
        )


def _requester(message: Any) -> str:
    user = getattr(message, 'from_user', None)
    if user is None:
        return ''
    return str(getattr(user, 'id', '') or '')
