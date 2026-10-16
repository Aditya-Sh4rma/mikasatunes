import asyncio
import re
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from ..logging_config import get_logger

logger = get_logger('mikasa.tools.thumbs')

Image.MAX_IMAGE_PIXELS = 25000000

_VIDEO_ID_RE = re.compile(r'^[A-Za-z0-9_-]{1,64}$')

CARD_SIZE = (1280, 720)
COVER_SIZE = (914, 514)
COVER_POS = (183, 30)
COVER_RADIUS = 18

BOLD_FONTS = (
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
)
REGULAR_FONTS = (
    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
)

Fetcher = Callable[[str], Awaitable[bytes]]


def _load_font(candidates, size: int):
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


async def _default_fetcher(url: str) -> bytes:
    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                raise RuntimeError(f'thumbnail fetch failed: HTTP {resp.status}')
            return await resp.read()


class Thumbnail:
    def __init__(
        self,
        cache_dir='cache',
        fetcher: Optional[Fetcher] = None,
        bold_font: Any = None,
        regular_font: Any = None,
    ) -> None:
        self._cache = Path(cache_dir)
        self._fetcher = fetcher or _default_fetcher
        self._bold = bold_font or _load_font(BOLD_FONTS, 34)
        self._regular = regular_font or _load_font(REGULAR_FONTS, 28)

    async def generate(self, track, channel: str = '', duration: str = '') -> Optional[str]:
        video_id = getattr(track, 'video_id', '') or ''
        thumb_url = getattr(track, 'thumbnail', '') or ''
        if not video_id or not thumb_url or not _VIDEO_ID_RE.match(video_id):
            return None
        self._cache.mkdir(parents=True, exist_ok=True)
        output = self._cache / f'{video_id}.png'
        if output.exists() and output.stat().st_size > 0:
            return str(output)
        temp = self._cache / f'temp_{video_id}.jpg'
        try:
            data = await self._fetcher(thumb_url)
            temp.write_bytes(data)
            title = str(getattr(track, 'title', '') or video_id)
            await asyncio.to_thread(self._render, temp, output, title, channel, duration)
        except Exception as exc:
            logger.warning('thumbnail failed: %s', type(exc).__name__)
            for path in (temp, output):
                try:
                    path.unlink()
                except OSError:
                    pass
            return None
        try:
            temp.unlink()
        except OSError:
            pass
        return str(output)

    def _render(self, temp: Path, output: Path, title: str, channel: str, duration: str) -> None:
        base = Image.open(temp).convert('RGBA')
        background = ImageOps.fit(base, CARD_SIZE, method=Image.LANCZOS)
        background = background.filter(ImageFilter.GaussianBlur(25))
        background = ImageEnhance.Brightness(background).enhance(0.4)
        cover = ImageOps.fit(base, COVER_SIZE, method=Image.LANCZOS)
        mask = Image.new('L', COVER_SIZE, 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            (0, 0, COVER_SIZE[0], COVER_SIZE[1]),
            radius=COVER_RADIUS,
            fill=255,
        )
        cover.putalpha(mask)
        background.paste(cover, COVER_POS, cover)
        draw = ImageDraw.Draw(background)
        white = (255, 255, 255)
        draw.text((50, 566), channel[:30], font=self._regular, fill=white)
        draw.text((50, 602), title[:55], font=self._bold, fill=white)
        draw.text((50, 648), f'0:00 / {duration}', font=self._regular, fill=white)
        background.convert('RGB').save(output, 'PNG')
