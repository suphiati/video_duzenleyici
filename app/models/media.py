from pydantic import BaseModel


class MediaInfo(BaseModel):
    path: str
    filename: str
    duration: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    video_codec: str = ""
    audio_codec: str = ""
    file_size: int = 0
    media_type: str = ""  # video, image, audio


class BrowseRequest(BaseModel):
    path: str


class ImportRequest(BaseModel):
    paths: list[str]
