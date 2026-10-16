# Copyright (c) 2026 Aditya-Sh4rma
# Licensed under the MIT License.
# This file is part of MikasaMusic


import logging
from logging.handlers import RotatingFileHandler

NOISY_LOGGERS = ("httpx", "ntgcalls", "pymongo", "pyrogram", "pytgcalls", "aiohttp")


def setup_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if root.handlers:
        return

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    file_handler = RotatingFileHandler("log.txt", maxBytes=8 * 1024 * 1024, backupCount=5)
    file_handler.setFormatter(formatter)

    root.setLevel(level)
    root.addHandler(stream)
    root.addHandler(file_handler)

    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.ERROR)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
