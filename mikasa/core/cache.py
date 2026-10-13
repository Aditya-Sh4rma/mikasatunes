import time
from pathlib import Path

from ..logging_config import get_logger

logger = get_logger("mikasa.core.cache")


def prune_cache(cache_dir="cache", max_age_days=30, max_files=500) -> dict:
    directory = Path(cache_dir)
    report = {"removed": 0, "kept": 0}
    if not directory.is_dir():
        return report
    now = time.time()
    cutoff = now - max_age_days * 86400
    survivors = []
    for path in sorted(directory.iterdir()):
        try:
            if not path.is_file():
                continue
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime >= cutoff:
            survivors.append((mtime, path))
        else:
            try:
                path.unlink()
                report["removed"] += 1
            except OSError as exc:
                logger.warning("cache prune failed for %s: %s", path.name, type(exc).__name__)
    survivors.sort(key=lambda entry: entry[0])
    while len(survivors) > max_files:
        _, oldest = survivors.pop(0)
        try:
            oldest.unlink()
            report["removed"] += 1
        except OSError as exc:
            logger.warning("cache prune failed for %s: %s", oldest.name, type(exc).__name__)
            break
    report["kept"] = len(survivors)
    return report
