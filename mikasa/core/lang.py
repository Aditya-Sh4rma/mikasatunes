import json
from pathlib import Path

DEFAULT_LANGUAGE = "en"
LOCALES_DIR = Path(__file__).resolve().parent.parent / "locales"


class Language:
    def __init__(self, locales_dir: Path = None, default: str = DEFAULT_LANGUAGE) -> None:
        self._dir = Path(locales_dir) if locales_dir else LOCALES_DIR
        self._default = default
        self._cache: dict[str, dict] = {}

    def available(self) -> list[str]:
        return sorted(path.stem for path in self._dir.glob("*.json"))

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
