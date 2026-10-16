class AppContext:
    def __init__(self) -> None:
        self.settings = None
        self.bot = None
        self.assistants = None
        self.database = None
        self.language = None
        self.queue = None
        self.search = None
        self.downloader = None
        self.controller = None
        self.thumbs = None
        self.started_at = None
        self.metrics = None
        self.admins = {}
        self.tasks = []

    def ready(self) -> bool:
        return self.bot is not None and self.database is not None


ctx = AppContext()
