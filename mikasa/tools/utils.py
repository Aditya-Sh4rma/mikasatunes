import re
import unicodedata


def format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_size(num_bytes: int) -> str:
    size = float(max(0, int(num_bytes)))
    units = ("B", "KB", "MB", "GB", "TB")
    index = 0
    while size >= 1024 and index < len(units) - 1:
        size /= 1024
        index += 1
    if index == 0:
        return f"{int(size)} B"
    return f"{size:.1f} {units[index]}"


def format_eta(seconds: int) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"


def progress_bar(current: int, total: int, width: int = 12) -> str:
    if total <= 0:
        return "-" * width
    ratio = max(0.0, min(1.0, current / total))
    filled = int(width * ratio)
    return "#" * filled + "-" * (width - filled)


def progress_text(played_seconds: int, total_seconds: int) -> str:
    try:
        total = int(total_seconds)
    except (TypeError, ValueError):
        return ""
    if total <= 0:
        return ""
    try:
        played = max(0, int(played_seconds))
    except (TypeError, ValueError):
        played = 0
    pos = min(int((min(played, total) / total) * 10), 9)
    bar = "—" * pos + "◉" + "—" * (10 - pos - 1)
    return f"{format_duration(played)} {bar} {format_duration(total)}"


def format_uptime(seconds: int) -> str:
    seconds = max(0, int(seconds))
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)
    if days:
        return f"{days} days, {hours}:{minutes:02d}:{secs:02d}"
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def parse_duration(value) -> int:
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


_NOISE_WORDS = frozenset({
    'official', 'video', 'audio', 'lyric', 'lyrics', 'song', 'songs',
    'hd', 'hq', '4k', '8d', 'mv', 'visualizer', 'cover',
})


def normalize_title(title: str) -> str:
    text = (title or '').lower()
    text = re.sub(r'\([^)]*\)', ' ', text)
    text = re.sub(r'\[[^\]]*\]', ' ', text)
    words = []
    current: list = []

    def flush() -> None:
        word = ''.join(current).strip('_')
        del current[:]
        if not word or word in _NOISE_WORDS:
            return
        if not any(ch.isalnum() for ch in word):
            return
        words.append(word)

    for ch in text:
        if ch.isalnum() or ch == '_' or unicodedata.category(ch).startswith('M'):
            current.append(ch)
        elif current:
            flush()
    if current:
        flush()
    return ' '.join(words)
