"""
Public Spotify playlist / track metadata retrieval.

Uses the official Spotify Web API via spotipy (Client Credentials flow)
when SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET are configured.
This only obtains publicly available metadata; it never obtains protected audio streams.

If credentials are missing, a clear error is raised. No scraping of private data
or use of user cookies/passwords is performed.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from config import config
from utils.errors import SpotifyMetadataError
from utils.validation import (
    SpotifyResourceType,
    extract_spotify_id,
    is_valid_spotify_playlist_url,
    is_valid_spotify_track_url,
)

logger = logging.getLogger(__name__)

# Simple in-memory cache: key -> (expires_at, data)
_cache: Dict[str, Tuple[float, Any]] = {}


@dataclass
class TrackMeta:
    spotify_id: str
    name: str
    artists: str
    duration_ms: Optional[int] = None
    is_playable: bool = True
    is_local: bool = False
    explicit: bool = False
    album_name: Optional[str] = None
    preview_url: Optional[str] = None  # 30s preview only; not full track


@dataclass
class PlaylistMeta:
    spotify_id: str
    name: str
    owner: Optional[str]
    description: Optional[str]
    total_tracks: int
    tracks: List[TrackMeta] = field(default_factory=list)
    is_public: bool = True
    collaborative: bool = False
    external_url: Optional[str] = None


class PlaylistReader:
    """Retrieve public playlist and track metadata."""

    def __init__(self) -> None:
        self._sp = None
        self._init_client()

    def _init_client(self) -> None:
        if not config.spotify_client_id or not config.spotify_client_secret:
            logger.warning(
                "SPOTIPY_CLIENT_ID / SPOTIPY_CLIENT_SECRET not set. "
                "Playlist metadata will be unavailable until credentials are provided."
            )
            self._sp = None
            return
        try:
            import spotipy
            from spotipy.oauth2 import SpotifyClientCredentials

            auth = SpotifyClientCredentials(
                client_id=config.spotify_client_id,
                client_secret=config.spotify_client_secret,
            )
            self._sp = spotipy.Spotify(
                auth_manager=auth,
                requests_timeout=15,
                retries=2,
            )
            logger.info("Spotify client credentials flow initialized.")
        except Exception as e:
            logger.error("Failed to initialize Spotify client: %s", e)
            self._sp = None

    def is_available(self) -> bool:
        return self._sp is not None

    def _cache_get(self, key: str) -> Optional[Any]:
        entry = _cache.get(key)
        if not entry:
            return None
        expires, data = entry
        if time.time() > expires:
            _cache.pop(key, None)
            return None
        return data

    def _cache_set(self, key: str, data: Any) -> None:
        _cache[key] = (time.time() + config.metadata_cache_ttl_seconds, data)

    def validate_and_extract(self, url: str) -> Tuple[SpotifyResourceType, str]:
        rtype, rid = extract_spotify_id(url)
        if rtype is None or rid is None or rtype == SpotifyResourceType.UNKNOWN:
            raise SpotifyMetadataError(
                "Invalid or unsupported Spotify URL. "
                "Please send a public playlist or track link from open.spotify.com."
            )
        if rtype == SpotifyResourceType.ALBUM:
            raise SpotifyMetadataError(
                "Album links are not supported yet. Please send a playlist or single track URL."
            )
        return rtype, rid

    def get_playlist(self, url_or_id: str) -> PlaylistMeta:
        """
        Fetch full public playlist metadata including ordered tracks.
        Raises SpotifyMetadataError on failure.
        """
        if not self.is_available():
            raise SpotifyMetadataError(
                "Spotify metadata service is not configured. "
                "Set SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET in the environment "
                "(create a free app at https://developer.spotify.com/dashboard)."
            )

        if is_valid_spotify_playlist_url(url_or_id):
            _, playlist_id = extract_spotify_id(url_or_id)
        else:
            playlist_id = url_or_id.strip()

        if not playlist_id or len(playlist_id) != 22:
            raise SpotifyMetadataError("Could not extract a valid playlist ID.")

        cache_key = f"pl:{playlist_id}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        try:
            pl = self._sp.playlist(playlist_id, market=None)
        except Exception as e:
            logger.exception("Spotify playlist request failed for %s", playlist_id)
            msg = str(e).lower()
            if "404" in msg or "not found" in msg:
                raise SpotifyMetadataError(
                    "Playlist not found or is private. Only public playlists can be read."
                ) from e
            if "429" in msg or "rate" in msg:
                raise SpotifyMetadataError(
                    "Spotify rate limit reached. Please try again in a few minutes."
                ) from e
            raise SpotifyMetadataError(
                f"Could not retrieve playlist metadata: {e}"
            ) from e

        if not pl:
            raise SpotifyMetadataError("Empty response from Spotify for this playlist.")

        tracks: List[TrackMeta] = []
        items = pl.get("tracks", {})
        # Paginate
        while True:
            for item in items.get("items") or []:
                track = item.get("track") if item else None
                if not track or track.get("is_local"):
                    # Keep a placeholder so order is preserved; mark unavailable
                    tracks.append(
                        TrackMeta(
                            spotify_id=track.get("id") or f"local-{len(tracks)}",
                            name=(track or {}).get("name") or "Local / unavailable track",
                            artists="Unknown",
                            is_playable=False,
                            is_local=True,
                        )
                    )
                    continue
                artists = ", ".join(
                    a.get("name", "") for a in (track.get("artists") or []) if a
                )
                tracks.append(
                    TrackMeta(
                        spotify_id=track.get("id") or "",
                        name=track.get("name") or "Unknown title",
                        artists=artists or "Unknown artist",
                        duration_ms=track.get("duration_ms"),
                        is_playable=bool(track.get("is_playable", True)),
                        is_local=False,
                        explicit=bool(track.get("explicit")),
                        album_name=(track.get("album") or {}).get("name"),
                        preview_url=track.get("preview_url"),
                    )
                )

            next_url = items.get("next")
            if not next_url:
                break
            try:
                items = self._sp.next(items)
            except Exception as e:
                logger.warning("Pagination stopped early: %s", e)
                break

        owner = None
        if pl.get("owner"):
            owner = pl["owner"].get("display_name") or pl["owner"].get("id")

        meta = PlaylistMeta(
            spotify_id=playlist_id,
            name=pl.get("name") or "Untitled playlist",
            owner=owner,
            description=pl.get("description"),
            total_tracks=len(tracks),
            tracks=tracks,
            is_public=bool(pl.get("public", True)),
            collaborative=bool(pl.get("collaborative")),
            external_url=(pl.get("external_urls") or {}).get("spotify"),
        )
        self._cache_set(cache_key, meta)
        return meta

    def get_track(self, url_or_id: str) -> TrackMeta:
        if not self.is_available():
            raise SpotifyMetadataError(
                "Spotify metadata service is not configured. "
                "Set SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET."
            )

        if is_valid_spotify_track_url(url_or_id):
            _, track_id = extract_spotify_id(url_or_id)
        else:
            track_id = url_or_id.strip()

        if not track_id or len(track_id) != 22:
            raise SpotifyMetadataError("Could not extract a valid track ID.")

        cache_key = f"tr:{track_id}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        try:
            tr = self._sp.track(track_id)
        except Exception as e:
            logger.exception("Spotify track request failed for %s", track_id)
            raise SpotifyMetadataError(f"Could not retrieve track metadata: {e}") from e

        artists = ", ".join(
            a.get("name", "") for a in (tr.get("artists") or []) if a
        )
        meta = TrackMeta(
            spotify_id=tr.get("id") or track_id,
            name=tr.get("name") or "Unknown title",
            artists=artists or "Unknown artist",
            duration_ms=tr.get("duration_ms"),
            is_playable=bool(tr.get("is_playable", True)),
            is_local=False,
            explicit=bool(tr.get("explicit")),
            album_name=(tr.get("album") or {}).get("name"),
            preview_url=tr.get("preview_url"),
        )
        self._cache_set(cache_key, meta)
        return meta


# Singleton
playlist_reader = PlaylistReader()
