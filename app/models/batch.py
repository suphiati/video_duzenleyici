from pydantic import BaseModel


class YouTubeSettings(BaseModel):
    title_template: str = "{folder_name} - Bolum {part_number}"
    description: str = ""
    tags: list[str] = []
    privacy: str = "private"  # private, unlisted, public
    category_id: str = "22"  # People & Blogs


class AISettings(BaseModel):
    """Optional AI-assisted metadata generation.

    provider: auto | ollama | claude | openai. "auto" prefers a local Ollama
    server, then falls back to Claude (ANTHROPIC_API_KEY) or OpenAI
    (OPENAI_API_KEY) when a key is configured.
    """
    enabled: bool = False
    provider: str = "auto"
    model: str | None = None
    language: str = "tr"  # tr | en
    append_default_description: bool = True


class CardSettings(BaseModel):
    """Auto intro/outro title cards wrapped around each batch video.

    No "subscribe" call-to-action is generated; blank text fields fall back to
    the video title (intro) and a neutral closing line (outro).
    """
    intro: bool = True
    outro: bool = True
    intro_text: str = ""   # blank -> video title
    outro_text: str = ""   # blank -> "Izlediginiz icin tesekkurler"
    duration: float = 2.5


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
    auto_thumbnail: bool = True
    youtube_settings: YouTubeSettings = YouTubeSettings()
    ai_settings: AISettings = AISettings()
    pro_settings: ProSettings = ProSettings()
    cards: CardSettings = CardSettings()


class ScanRequest(BaseModel):
    folder_path: str
