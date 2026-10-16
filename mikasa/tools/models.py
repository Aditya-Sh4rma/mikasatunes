# Copyright (c) 2026 Aditya-Sh4rma
# Licensed under the MIT License.
# This file is part of MikasaMusic


from dataclasses import asdict, dataclass
from typing import Optional, Union


@dataclass
class Track:
    video_id: str
    title: str
    duration_seconds: int
    url: str
    thumbnail: str = ""
    channel: str = ""
    requested_by: str = ""
    is_video: bool = False
    file_path: Optional[str] = None
    message_id: int = 0

    @property
    def id(self) -> str:
        return self.video_id

    @property
    def has_file(self) -> bool:
        return bool(self.file_path)


@dataclass
class Media:
    file_id: str
    title: str
    duration_seconds: int
    file_path: str
    url: str = ""
    requested_by: str = ""
    is_video: bool = False
    message_id: int = 0

    @property
    def id(self) -> str:
        return self.file_id

    @property
    def has_file(self) -> bool:
        return bool(self.file_path)


MediaItem = Union[Track, Media]


@dataclass
class ChatSettings:
    language: str = "en"
    assistant: int = 0

    def to_document(self) -> dict:
        return asdict(self)

    @classmethod
    def from_document(cls, document: dict) -> "ChatSettings":
        return cls(
            language=str(document.get("language", "en")),
            assistant=int(document.get("assistant", 0)),
        )
