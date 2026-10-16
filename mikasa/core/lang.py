import json
from pathlib import Path

DEFAULT_LANGUAGE = "en"
LOCALES_DIR = Path(__file__).resolve().parent.parent.parent / "strings"

LANG_NAMES = {
    "en": "English",
    "bur": "မြန်မာ",
}


class Language:
    def __init__(self, locales_dir: Path = None, default: str = DEFAULT_LANGUAGE) -> None:
        self._dir = Path(locales_dir) if locales_dir else LOCALES_DIR
        self._default = default
        self._cache: dict[str, dict] = {}
        self._chat_cache: dict[int, str] = {}
        self._known: list[str] | None = None

    def available(self) -> list[str]:
        if self._known is None:
            self._known = sorted(path.stem for path in self._dir.glob("*.json"))
        return list(self._known)

    def available_names(self) -> dict[str, str]:
        return {
            code: LANG_NAMES.get(code, code)
            for code in self.available()
            if code in LANG_NAMES
        }

    def cached(self, chat_id: int) -> str:
        try:
            return self._chat_cache.get(int(chat_id), "")
        except (TypeError, ValueError):
            return ""

    def set_cached(self, chat_id: int, code: str) -> None:
        try:
            self._chat_cache[int(chat_id)] = (code or "").lower()
        except (TypeError, ValueError):
            pass

    async def for_chat(self, chat_id: int, database=None) -> str:
        try:
            key = int(chat_id)
        except (TypeError, ValueError):
            return ""
        known = self._chat_cache.get(key, "")
        if known:
            return known
        code = ""
        if database is not None:
            try:
                settings = await database.chat_settings(key)
                code = str(getattr(settings, "language", "") or "").lower()
            except Exception:
                code = ""
        if code not in self.available():
            code = ""
        if code:
            self._chat_cache[key] = code
        return code

    def strings(self, code: str = None) -> dict:
        code = (code or self._default).lower()
        if code not in self._cache:
            base = self._read(self._default)
            if code == self._default:
                self._cache[code] = base
            else:
                self._cache[code] = {**base, **self._read(code)}
        return self._cache[code]

    def text(self, code: str, key: str, **kwargs) -> str:
        template = self.strings(code).get(key, key)
        if not kwargs:
            return template
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError):
            return template

    def _read(self, code: str) -> dict:
        path = self._dir / f"{code}.json"
        if not path.exists():
            return {}
        try:
            with path.open(encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}
