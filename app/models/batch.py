from pydantic import BaseModel


class YouTubeSettings(BaseModel):
    title_template: str = "{folder_name} - Bolum {part_number}"
    description: str = ""
    tags: list[str] = []
    privacy: str = "private"  # private, unlisted, public
    category_id: str = "22"  # People & Blogs


class AISettings(BaseModel):
    """Optional AI-assisted metadata generation via local Ollama."""
    enabled: bool = False
    model: str | None = None
    language: str = "tr"  # tr | en
    append_default_description: bool = True


class ProSettings(BaseModel):
    """Professional-edit pipeline (scene detection + beat sync + music)."""
    enabled: bool = False
    style: str = "auto"  # auto | vlog | cinematic | highlight | calm
    music_mode: str = "auto"  # none | auto | specific
    music_path: str | None = None  # used when music_mode == "specific"
    music_volume: float | None = None  # overrides profile default
    original_audio_volume: float | None = None  # overrides profile default


class BatchRequest(BaseModel):
    folder_path: str
    num_videos: int = 5
    target_duration: float = 300.0
    clip_duration: float = 5.0
    photo_duration: float = 4.0
    transition: str = "fade"
    transition_duration: float = 0.5
    shuffle: bool = False
    upload_to_youtube: bool = True
    youtube_settings: YouTubeSettings = YouTubeSettings()
    ai_settings: AISettings = AISettings()
    pro_settings: ProSettings = ProSettings()


class ScanRequest(BaseModel):
    folder_path: str
