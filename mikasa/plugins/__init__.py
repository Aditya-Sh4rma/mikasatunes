# Copyright (c) 2026 Aditya-Sh4rma
# Licensed under the MIT License.
# This file is part of MikasaMusic


import importlib
from pathlib import Path


def _list_plugins():
    directory = Path(__file__).parent
    return sorted(
        file.stem
        for file in directory.glob("*.py")
        if file.is_file() and file.name not in ("__init__.py", "common.py")
    )


all_plugins = frozenset(sorted(_list_plugins()))


def load_plugins(app) -> list:
    loaded = []
    for name in sorted(all_plugins):
        module = importlib.import_module(f"{__name__}.{name}")
        register = getattr(module, "register", None)
        if register is not None:
            register(app)
        loaded.append(name)
    return loaded
