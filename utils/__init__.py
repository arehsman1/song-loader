"""Utility helpers."""

from .validation import (
    is_valid_spotify_playlist_url,
    is_valid_spotify_track_url,
    extract_spotify_id,
    SpotifyResourceType,
)
from .filenames import sanitize_filename, unique_path
from .errors import (
    BotError,
    ConfigError,
    SpotifyMetadataError,
    AudioSourceUnavailable,
    FileTooLargeError,
    JobCancelledError,
    UnauthorizedActionError,
)

__all__ = [
    "is_valid_spotify_playlist_url",
    "is_valid_spotify_track_url",
    "extract_spotify_id",
    "SpotifyResourceType",
    "sanitize_filename",
    "unique_path",
    "BotError",
    "ConfigError",
    "SpotifyMetadataError",
    "AudioSourceUnavailable",
    "FileTooLargeError",
    "JobCancelledError",
    "UnauthorizedActionError",
]
