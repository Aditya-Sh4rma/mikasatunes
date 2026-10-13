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
