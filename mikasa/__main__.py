import asyncio
import sys

from pyrogram import idle

from .boot import boot, shutdown
from .exceptions import MikasaError
from .logging_config import get_logger, setup_logging


async def run() -> int:
    log = get_logger("mikasa")
    try:
        state = await boot()
    except (MikasaError, RuntimeError) as exc:
        log.error("startup failed: %s", exc)
        return 2
    try:
        await idle()
    finally:
        await shutdown(log, state)
        log.info("shutdown complete")
    return 0


def main() -> int:
    setup_logging()
    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
