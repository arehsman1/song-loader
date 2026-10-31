"""URL and input validation helpers."""

from __future__ import annotations

import re
from enum import Enum
from typing import Optional, Tuple
from urllib.parse import urlparse


class SpotifyResourceType(str, Enum):
    PLAYLIST = "playlist"
    TRACK = "track"
    ALBUM = "album"
    UNKNOWN = "unknown"


# Official Spotify URL patterns (open.spotify.com and spotify: URI)
_SPOTIFY_HOSTS = {"open.spotify.com", "play.spotify.com", "spotify.com"}
_PLAYLIST_RE = re.compile(
    r"(?:https?://(?:open|play)\.spotify\.com/(?:intl-[a-z]{2}/)?playlist/|spotify:playlist:)"
    r"([a-zA-Z0-9]{22})",
    re.IGNORECASE,
)
_TRACK_RE = re.compile(
    r"(?:https?://(?:open|play)\.spotify\.com/(?:intl-[a-z]{2}/)?track/|spotify:track:)"
    r"([a-zA-Z0-9]{22})",
    re.IGNORECASE,
)
_ALBUM_RE = re.compile(
    r"(?:https?://(?:open|play)\.spotify\.com/(?:intl-[a-z]{2}/)?album/|spotify:album:)"
    r"([a-zA-Z0-9]{22})",
    re.IGNORECASE,
)


def _normalize_url(url: str) -> str:
    return url.strip()


def is_valid_spotify_playlist_url(url: str) -> bool:
    """Return True if the string looks like a public Spotify playlist URL or URI."""
    if not url or not isinstance(url, str):
        return False
    url = _normalize_url(url)
    if _PLAYLIST_RE.search(url):
        return True
    # Extra host check for safety
    try:
        parsed = urlparse(url if "://" in url else f"https://{url}")
        if parsed.hostname and parsed.hostname.lower() in _SPOTIFY_HOSTS:
            return "playlist/" in parsed.path.lower()
    except Exception:
        pass
    return False


def is_valid_spotify_track_url(url: str) -> bool:
    """Return True if the string looks like a Spotify track URL or URI."""
    if not url or not isinstance(url, str):
        return False
    return bool(_TRACK_RE.search(_normalize_url(url)))


def extract_spotify_id(url: str) -> Tuple[Optional[SpotifyResourceType], Optional[str]]:
    """
    Extract resource type and 22-character ID from a Spotify URL/URI.
    Returns (type, id) or (UNKNOWN, None) / (None, None) on failure.
    """
    if not url or not isinstance(url, str):
        return None, None
    url = _normalize_url(url)

    m = _PLAYLIST_RE.search(url)
    if m:
        return SpotifyResourceType.PLAYLIST, m.group(1)

    m = _TRACK_RE.search(url)
    if m:
        return SpotifyResourceType.TRACK, m.group(1)

    m = _ALBUM_RE.search(url)
    if m:
        return SpotifyResourceType.ALBUM, m.group(1)

    return SpotifyResourceType.UNKNOWN, None


def is_safe_callback_data(data: str, max_len: int = 64) -> bool:
    """Basic sanity check for Telegram callback_data."""
    if not data or len(data) > max_len:
        return False
    # Allow only printable ASCII without control chars
    return all(32 <= ord(c) < 127 for c in data)
