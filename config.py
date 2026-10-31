"""
Application configuration loaded from environment variables.
Portable across Windows, Linux, and Docker.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load .env from project root if present (does not override existing env)
_PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(_PROJECT_ROOT / ".env")


def _get_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _get_int(name: str, default: int) -> int:
    val = os.getenv(name)
    if val is None or val.strip() == "":
        return default
    try:
        return int(val)
    except ValueError:
        raise ValueError(f"Environment variable {name} must be an integer, got: {val!r}")


def _get_float(name: str, default: float) -> float:
    val = os.getenv(name)
    if val is None or val.strip() == "":
        return default
    try:
        return float(val)
    except ValueError:
        raise ValueError(f"Environment variable {name} must be a number, got: {val!r}")


class Config:
    """Central configuration object. Validated at startup."""

    def __init__(self) -> None:
        self.telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not self.telegram_bot_token:
            raise RuntimeError(
                "TELEGRAM_BOT_TOKEN is required. "
                "Create a bot with @BotFather and set the token in .env or environment."
            )

        # Data directories – resolve relative to project root for portability
        data_dir_raw = os.getenv("DATA_DIR", "./data").strip()
        self.data_dir: Path = Path(data_dir_raw)
        if not self.data_dir.is_absolute():
            self.data_dir = (_PROJECT_ROOT / self.data_dir).resolve()

        db_path_raw = os.getenv("DATABASE_PATH", "").strip()
        if db_path_raw:
            self.database_path: Path = Path(db_path_raw)
            if not self.database_path.is_absolute():
                self.database_path = (_PROJECT_ROOT / self.database_path).resolve()
        else:
            self.database_path = self.data_dir / "bot.db"

        temp_dir_raw = os.getenv("TEMP_DIR", "").strip()
        if temp_dir_raw:
            self.temp_dir: Path = Path(temp_dir_raw)
            if not self.temp_dir.is_absolute():
                self.temp_dir = (_PROJECT_ROOT / self.temp_dir).resolve()
        else:
            self.temp_dir = self.data_dir / "tmp"

        self.downloads_dir: Path = self.data_dir / "downloads"
        self.logs_dir: Path = self.data_dir / "logs"

        # Limits
        self.max_file_size_mib: int = _get_int("MAX_FILE_SIZE_MIB", 45)
        self.max_file_size_bytes: int = self.max_file_size_mib * 1024 * 1024

        self.default_audio_bitrate: str = os.getenv("DEFAULT_AUDIO_BITRATE", "320k").strip()
        self.default_delivery_mode: str = os.getenv("DEFAULT_DELIVERY_MODE", "individual").strip().lower()
        if self.default_delivery_mode not in ("individual", "zip"):
            self.default_delivery_mode = "individual"

        self.max_tracks_per_job: int = _get_int("MAX_TRACKS_PER_JOB", 100)
        self.max_concurrent_jobs_per_user: int = _get_int("MAX_CONCURRENT_JOBS_PER_USER", 1)
        self.max_global_concurrent_jobs: int = _get_int("MAX_GLOBAL_CONCURRENT_JOBS", 3)

        self.download_timeout_seconds: int = _get_int("DOWNLOAD_TIMEOUT_SECONDS", 120)
        self.metadata_cache_ttl_seconds: int = _get_int("METADATA_CACHE_TTL_SECONDS", 3600)
        self.temp_file_retention_hours: int = _get_int("TEMP_FILE_RETENTION_HOURS", 24)

        self.log_level: str = os.getenv("LOG_LEVEL", "INFO").strip().upper()

        # Optional FFmpeg paths
        self.ffmpeg_path: Optional[str] = os.getenv("FFMPEG_PATH", "").strip() or None
        self.ffprobe_path: Optional[str] = os.getenv("FFPROBE_PATH", "").strip() or None

        # Optional Spotify credentials (for public metadata via Client Credentials)
        self.spotify_client_id: Optional[str] = os.getenv("SPOTIPY_CLIENT_ID", "").strip() or None
        self.spotify_client_secret: Optional[str] = os.getenv("SPOTIPY_CLIENT_SECRET", "").strip() or None

        # Webhook (optional; long polling is default)
        self.webhook_host: Optional[str] = os.getenv("WEBHOOK_HOST", "").strip() or None
        self.webhook_path: str = os.getenv("WEBHOOK_PATH", "/webhook").strip()
        self.webhook_port: int = _get_int("WEBHOOK_PORT", 8443)

        # Ensure directories exist
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        for d in (self.data_dir, self.temp_dir, self.downloads_dir, self.logs_dir):
            d.mkdir(parents=True, exist_ok=True)

    def validate_ffmpeg(self) -> tuple[bool, str]:
        """Check that ffmpeg/ffprobe are available. Returns (ok, message)."""
        import shutil

        ffmpeg = self.ffmpeg_path or shutil.which("ffmpeg")
        ffprobe = self.ffprobe_path or shutil.which("ffprobe")
        if not ffmpeg:
            return False, (
                "FFmpeg not found. Install FFmpeg and ensure it is on PATH, "
                "or set FFMPEG_PATH in the environment."
            )
        if not ffprobe:
            return False, (
                "FFprobe not found. Install FFmpeg (includes ffprobe) and ensure it is on PATH, "
                "or set FFPROBE_PATH in the environment."
            )
        return True, f"FFmpeg: {ffmpeg}, FFprobe: {ffprobe}"


# Singleton used by the rest of the application
try:
    config = Config()
except RuntimeError as e:
    print(f"Configuration error: {e}", file=sys.stderr)
    raise
