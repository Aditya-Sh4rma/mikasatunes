import shutil
from pathlib import Path

from ..logging_config import get_logger

logger = get_logger("mikasa.core.dir")


def ensure_dirs(*names: str) -> list:
    targets = list(names) or ["cache", "downloads"]
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg must be installed and accessible in the system PATH.")
    if not shutil.which("deno"):
        logger.warning("deno not found in PATH; some downloads may fail")
    ready = []
    for name in targets:
        Path(name).mkdir(parents=True, exist_ok=True)
        ready.append(name)
    logger.info("working directories ready: %s", ",".join(ready))
    return ready
