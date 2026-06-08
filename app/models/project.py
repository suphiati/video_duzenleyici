from pydantic import BaseModel, Field
from datetime import datetime
import uuid


class Clip(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    media_path: str
    in_point: float = 0.0
    out_point: float = -1.0  # -1 means end of file
    order: int = 0
    # Per-clip colour correction (applied at export via ffmpeg eq=)
    brightness: float = 0.0   # -1.0 .. 1.0  (0 = unchanged)
    contrast: float = 1.0     #  0.0 .. 2.0  (1 = unchanged)
    saturation: float = 1.0   #  0.0 .. 3.0  (1 = unchanged)
    # Per-clip transforms (applied at export)
    hflip: bool = False       # mirror horizontally
    speed: float = 1.0        # 0.5 .. 2.0  (1 = normal; >1 faster)


class AudioTrack(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    media_path: str
    start_time: float = 0.0
    volume: float = 1.0
    fade_in: float = 0.0
    fade_out: float = 0.0


class SubtitleEntry(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    start_time: float = 0.0
    end_time: float = 5.0
    text: str = ""
    font_size: int = 48
    color: str = "#FFFFFF"
    position: str = "bottom"  # top, center, bottom


class ExportSettings(BaseModel):
    resolution: str = "1920x1080"
    video_bitrate: str = "10M"
    audio_bitrate: str = "384k"
    format: str = "mp4"


class Project(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = "Yeni Proje"
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    clips: list[Clip] = []
    audio_tracks: list[AudioTrack] = []
    subtitles: list[SubtitleEntry] = []
    export_settings: ExportSettings = Field(default_factory=ExportSettings)
