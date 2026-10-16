from dataclasses import dataclass
from os import getenv

from dotenv import load_dotenv

from mikasa.exceptions import ConfigurationError

load_dotenv()

MAX_ASSISTANTS = 5


def _flag(name: str, default: bool = False) -> bool:
    return getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _session_value(index: int) -> str:
    names = [f"SESSION_{index}", f"SESSION{index}"]
    if index == 1:
        names.append("SESSION")
    for name in names:
        value = getenv(name)
        if value and value.strip():
            return value.strip()
    return ""


@dataclass(frozen=True)
class SessionSlot:
    slot: int
    value: str

    @property
    def label(self) -> str:
        return f"assistant-{self.slot}"


class Config:
    def __init__(self) -> None:
        self.api_id = _int("API_ID", 0)
        self.api_hash = getenv("API_HASH", "")
        self.bot_token = getenv("BOT_TOKEN", "")
        self.mongo_url = getenv("MONGO_URL", "")
        self.log_chat_id = _int("LOGGER_ID", 0)
        self.owner_id = _int("OWNER_ID", 0)
        self.owner_username = (getenv("OWNER_USERNAME") or "").lstrip("@")
        self.support_chat = getenv("SUPPORT_CHAT", "https://t.me/")
        self.support_channel = getenv("SUPPORT_CHANNEL", "https://t.me/")
        self.default_language = getenv("LANG_CODE", "en")
        self.duration_limit = _int("DURATION_LIMIT", 60) * 60
        self.queue_limit = _int("QUEUE_LIMIT", 20)
        self.playlist_limit = _int("PLAYLIST_LIMIT", 20)
        self.auto_leave = _flag("AUTO_LEAVE", False)
        self.auto_end = _flag("AUTO_END", False)
        self.thumbnails = _flag("THUMB_GEN", True)
        self.video_enabled = _flag("VIDEO_PLAY", True)
        self.cookies_file = getenv("COOKIES_FILE") or None
        self.devil_api_url = (getenv("DEVIL_API_URL") or "").strip().rstrip("/")
        self.devil_api_key = getenv("DEVIL_API_KEY") or ""
        self.shruti_api_url = (
            getenv("SHRUTI_API_URL") or "https://api.shrutibots.site"
        ).strip().rstrip("/")
        self.shruti_api_key = getenv("SHRUTI_API_KEY") or ""
        self.default_thumb = getenv("DEFAULT_THUMB", "")
        self.ping_image = getenv("PING_IMG", "")
        self.start_image = getenv("START_IMG", "")
        self.sessions = self._load_sessions()

    def _load_sessions(self) -> list[SessionSlot]:
        slots = []
        for index in range(1, MAX_ASSISTANTS + 1):
            value = _session_value(index)
            if value:
                slots.append(SessionSlot(index, value))
        return slots

    def session_slots(self) -> list[int]:
        return [slot.slot for slot in self.sessions]

    @property
    def session_count(self) -> int:
        return len(self.sessions)

    def missing(self) -> list[str]:
        required = {
            "API_ID": self.api_id,
            "API_HASH": self.api_hash,
            "BOT_TOKEN": self.bot_token,
            "MONGO_URL": self.mongo_url,
            "LOGGER_ID": self.log_chat_id,
            "OWNER_ID": self.owner_id,
        }
        return [name for name, value in required.items() if not value]

    def validate(self) -> None:
        missing = self.missing()
        if missing:
            raise ConfigurationError("Missing required settings: " + ", ".join(missing))
        if not self.sessions:
            raise ConfigurationError("Configure at least one assistant session (SESSION_1).")
