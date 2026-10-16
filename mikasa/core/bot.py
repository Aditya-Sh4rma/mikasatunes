# Copyright (c) 2026 Aditya-Sh4rma
# Licensed under the MIT License.
# This file is part of MikasaMusic


import pyrogram

from ..logging_config import get_logger
from config import Config


class MusicBot(pyrogram.Client):
    def __init__(self, settings: Config) -> None:
        super().__init__(
            name="mikasa_bot",
            api_id=settings.api_id,
            api_hash=settings.api_hash,
            bot_token=settings.bot_token,
            parse_mode=pyrogram.enums.ParseMode.HTML,
            link_preview_options=pyrogram.types.LinkPreviewOptions(is_disabled=True),
            max_concurrent_transmissions=4,
        )
        self.settings = settings
        self.log = get_logger("mikasa.bot")

    async def boot(self) -> None:
        await self.start()
        me = self.me
        self.log.info("bot online as %s", me.username or me.id)
        await self._announce()

    async def _announce(self) -> None:
        try:
            await self.send_message(self.settings.log_chat_id, "MikasaMusic bot started")
        except Exception as exc:
            self.log.warning("log chat unreachable: %s", type(exc).__name__)

    async def exit(self) -> None:
        try:
            await self.stop()
        except Exception as exc:
            self.log.warning("bot stop error: %s", type(exc).__name__)
