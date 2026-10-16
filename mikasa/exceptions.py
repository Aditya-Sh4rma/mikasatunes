# Copyright (c) 2026 Aditya-Sh4rma
# Licensed under the MIT License.
# This file is part of MikasaMusic


class MikasaError(Exception):
    pass


class ConfigurationError(MikasaError):
    pass


class SessionError(MikasaError):
    pass


class DownloadError(MikasaError):
    pass


class StreamError(MikasaError):
    pass


class AccessDenied(MikasaError):
    pass


class UnsupportedMedia(MikasaError):
    pass


class QueueFull(MikasaError):
    pass
