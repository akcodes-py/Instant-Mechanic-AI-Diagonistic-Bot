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

    # Hardening controls (security layer, all deterministic and local).
    API_RATE_LIMIT_PER_MIN: int = 10
    MAX_VISION_IMAGE_MB: float = 5.0
    MAX_GUARD_HISTORY_MESSAGES: int = 6
    MAX_GUARD_CONTEXT_CHARS: int = 1200
    MAX_GUARD_CONTEXT_TOKENS: int = 600
    MAX_LLM_TOKENS: int = 400

    # Optional JSON-lines sink for structured security events (empty = stdout).
    SECURITY_AUDIT_LOG: str = ""

    # ML model paths (empty = unavailable, deterministic fallback)
    VISION_MODEL_PATH: str = ""
    VISION_CONF: float = 0.25
    VISION_IMGSZ: int = 960
    NLP_MODEL_PATH: str = ""
    ENABLE_ML_INFERENCE: bool = False

    # H3 dispatch platform (ADR-001). All optional: empty/unreachable values keep
    # the deterministic chat -> diagnosis -> booking flow working unchanged.
    H3_PRESENCE_RESOLUTION: int = 8
    H3_ZONE_RESOLUTION: int = 7
    DISPATCH_MAX_RING: int = 3
    OFFER_TTL_SECONDS: int = 15
    REDPANDA_BROKERS: str = "localhost:9092"
    REDIS_URL: str = "redis://localhost:6379/0"
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DB: str = "instant_mechanic"
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "instant-mechanic-media"
    MINIO_SECURE: bool = False
    DISPATCH_SERVICE_URL: str = "http://localhost:8080"
    ENABLE_MONGO: bool = False
    MONGO_TIMEOUT_MS: int = 500
    ETA_MODEL_PATH: str = ""

    @property
    def cors_origins(self) -> list[str]:
        raw = self.CORS_ORIGINS or self.CORS_ALLOWED_ORIGINS
        return [origin.strip() for origin in raw.split(",") if origin.strip()]


settings = Settings()
