"""Typed application settings (replaces Django's settings.py)."""
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Load the repo-root .env; a local .env in the working directory wins.
        env_file=(REPO_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    DEBUG: bool = Field(
        default=True,
        validation_alias=AliasChoices("DEBUG", "DJANGO_DEBUG"),
    )
    DATABASE_URL: str = "sqlite+aiosqlite:///./db.sqlite3"
    MEDIA_ROOT: Path = Path("./media")

    # CORS_ORIGINS is the new name; CORS_ALLOWED_ORIGINS is kept for existing .env files.
    CORS_ORIGINS: str | None = None
    CORS_ALLOWED_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"
    CORS_ALLOW_ALL: bool = False

    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    GROQ_TIMEOUT_S: float = 20.0

    MAX_IMAGE_MB: float = 10.0
    MAX_AUDIO_MB: float = 15.0
    MAX_VIDEO_MB: float = 50.0
    CHAT_RATELIMIT_PER_MIN: int = 30

    # ML model paths (empty = unavailable, deterministic fallback)
    VISION_MODEL_PATH: str = ""
    VISION_CONF: float = 0.25
    VISION_IMGSZ: int = 960
    NLP_MODEL_PATH: str = ""
    ENABLE_ML_INFERENCE: bool = False

    @property
    def cors_origins(self) -> list[str]:
        raw = self.CORS_ORIGINS or self.CORS_ALLOWED_ORIGINS
        return [origin.strip() for origin in raw.split(",") if origin.strip()]


settings = Settings()
