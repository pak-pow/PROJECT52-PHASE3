"""Application settings and configuration environments for PulseStream."""

import os
from pathlib import Path
from typing import Dict, Set


class Config:
    """Base application configuration."""

    # Base filesystem paths
    APP_DIR: Path = Path(__file__).resolve().parent.parent
    BACKEND_DIR: Path = APP_DIR.parent
    PROJECT_DIR: Path = BACKEND_DIR.parent
    FRONTEND_DIR: Path = PROJECT_DIR / "frontend"
    DATA_DIR: Path = BACKEND_DIR / "data"
    MEDIA_DIR: Path = BACKEND_DIR / "media"
    RAW_MEDIA_DIR: Path = MEDIA_DIR / "raw"
    HLS_MEDIA_DIR: Path = MEDIA_DIR / "hls"
    THUMBNAILS_DIR: Path = MEDIA_DIR / "thumbnails"

    # Database
    DB_PATH: Path = DATA_DIR / "pulsestream.db"
    SCHEMA_PATH: Path = DATA_DIR / "schema.sql"

    # Streaming and Upload Limits
    MAX_CONTENT_LENGTH: int = 500 * 1024 * 1024  # 500 MB
    CHUNK_SIZE_BYTES: int = 1024 * 1024  # 1 MB chunk for range streaming
    ALLOWED_EXTENSIONS: Set[str] = {"mp4", "webm", "mov", "mkv"}
    HLS_SEGMENT_DURATION_SECONDS: int = 4

    # ABR Rendition profiles (resolution -> width, height, bitrate_kbps)
    RENDITIONS: Dict[str, Dict[str, int]] = {
        "1080p": {"width": 1920, "height": 1080, "bitrate_kbps": 4500},
        "720p": {"width": 1280, "height": 720, "bitrate_kbps": 2500},
        "480p": {"width": 854, "height": 480, "bitrate_kbps": 1000},
        "360p": {"width": 640, "height": 360, "bitrate_kbps": 600},
    }

    # Transcoding settings
    TRANSCODER_THREADS: int = 2
    TESTING: bool = False
    DEBUG: bool = False


class DevelopmentConfig(Config):
    """Development configuration."""

    DEBUG: bool = True


class TestingConfig(Config):
    """Testing configuration using temporary or in-memory targets."""

    TESTING: bool = True
    DEBUG: bool = True
    DB_PATH: Path = Path(":memory:")


def get_config(env_name: str | None = None) -> Config:
    """Retrieve configuration class matching environment name."""
    env = env_name or os.getenv("FLASK_ENV", "development").lower()
    if env == "testing":
        return TestingConfig()
    return DevelopmentConfig()
