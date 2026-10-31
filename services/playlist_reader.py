"""
Public Spotify playlist / track metadata retrieval.

Uses the official Spotify Web API via spotipy (Client Credentials flow)
when SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET are configured.
This only obtains publicly available metadata; it never obtains protected audio streams.

IMPORTANT (Spotify Web API policy as of 2025–2026):
  Playlist *contents* (the list of tracks) are only returned when the
  authorized Spotify account owns or collaborates on that playlist.
  App-only (Client Credentials) tokens therefore receive playlist name,
  owner, description, and sometimes a total count, but the items/tracks
  array is omitted or empty for arbitrary public playlists.

  This is not a bug in the bot. See:
  https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide

If credentials are missing, a clear error is raised. No scraping of private
data or use of user cookies/passwords is performed.
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
    # True when Spotify returned metadata but withheld the track list
    tracks_withheld: bool = False


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

    # ------------------------------------------------------------------
    # Helpers that understand both pre-2026 and post-2026 response shapes
    # ------------------------------------------------------------------

    @staticmethod
    def _get_paging_object(pl: dict) -> Tuple[dict, str]:
        """
        Return (paging_dict, style) where style is 'tracks' (old) or 'items' (new).
        Spotify renamed tracks → items in the 2026 migration.
        """
        if "items" in pl and isinstance(pl["items"], dict):
            return pl["items"], "items"
        if "tracks" in pl and isinstance(pl["tracks"], dict):
            return pl["tracks"], "tracks"
        # Some responses put a bare total at top level with no paging object
        return {}, "none"

    @staticmethod
    def _extract_track_from_item(item: dict, style: str) -> Optional[dict]:
        """
        From a single playlist item, pull the track/episode object.
        Old style: item['track']
        New style: item['item']  (and type may be track/episode)
        """
        if not item or not isinstance(item, dict):
            return None
        if style == "items":
            # New shape: item.item (the actual track/episode)
            obj = item.get("item") or item.get("track")
        else:
            obj = item.get("track") or item.get("item")
        return obj if isinstance(obj, dict) else None

    def _parse_track_object(self, track: dict, index: int) -> TrackMeta:
        if not track:
            return TrackMeta(
                spotify_id=f"unknown-{index}",
                name="Unavailable track",
                artists="Unknown",
                is_playable=False,
                is_local=True,
            )
        if track.get("is_local") or track.get("type") == "local":
            return TrackMeta(
                spotify_id=track.get("id") or f"local-{index}",
                name=track.get("name") or "Local / unavailable track",
                artists="Unknown",
                is_playable=False,
                is_local=True,
            )
        artists = ", ".join(
            a.get("name", "") for a in (track.get("artists") or []) if a
        )
        return TrackMeta(
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

    def _collect_tracks_from_paging(
        self, paging: dict, style: str
    ) -> List[TrackMeta]:
        """Walk a paging object (and its next pages) and build TrackMeta list."""
        tracks: List[TrackMeta] = []
        items = paging
        while True:
            for raw in items.get("items") or []:
                track_obj = self._extract_track_from_item(raw, style)
                tracks.append(self._parse_track_object(track_obj, len(tracks)))

            next_url = items.get("next")
            if not next_url:
                break
            try:
                items = self._sp.next(items)
            except Exception as e:
                logger.warning("Pagination stopped early: %s", e)
                break
        return tracks

    def _try_playlist_items_endpoint(self, playlist_id: str) -> List[TrackMeta]:
        """
        Fallback: call the dedicated /playlists/{id}/items (or legacy /tracks)
        endpoint. With Client Credentials this usually still returns empty for
        playlists the app does not own, but we try both for completeness.
        """
        tracks: List[TrackMeta] = []
        try:
            # spotipy exposes playlist_items (newer) and playlist_tracks (older)
            if hasattr(self._sp, "playlist_items"):
                results = self._sp.playlist_items(
                    playlist_id, limit=100, additional_types="track"
                )
                style = "items"
            else:
                results = self._sp.playlist_tracks(playlist_id, limit=100)
                style = "tracks"

            while results:
                for raw in results.get("items") or []:
                    track_obj = self._extract_track_from_item(raw, style)
                    tracks.append(self._parse_track_object(track_obj, len(tracks)))
                if results.get("next"):
                    results = self._sp.next(results)
                else:
                    break
        except Exception as e:
            logger.info(
                "Dedicated playlist items endpoint failed for %s (expected with "
                "client-credentials for non-owned playlists): %s",
                playlist_id,
                e,
            )
        return tracks

    def get_playlist(self, url_or_id: str) -> PlaylistMeta:
        """
        Fetch public playlist metadata including ordered tracks when Spotify
        returns them.

        Raises SpotifyMetadataError with a clear message when the track list
        is withheld by Spotify's access policy.
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

        # --- Parse tracks using both response shapes ---
        paging, style = self._get_paging_object(pl)
        reported_total = 0
        if paging:
            reported_total = int(paging.get("total") or 0)
        # Some responses put total only at the top-level playlist object
        if reported_total == 0:
            reported_total = int(
                (pl.get("tracks") or {}).get("total")
                or (pl.get("items") or {}).get("total")
                or 0
            )

        tracks = self._collect_tracks_from_paging(paging, style) if paging else []

        # If the main playlist response gave us no items, try the dedicated endpoint
        if not tracks:
            tracks = self._try_playlist_items_endpoint(playlist_id)

        # Detect "Spotify withheld the list" vs truly empty playlist
        tracks_withheld = False
        if not tracks and reported_total > 0:
            tracks_withheld = True
        elif not tracks and "items" not in pl and "tracks" not in pl:
            # Completely missing paging object – common with client-credentials
            tracks_withheld = True
        elif not tracks and paging and not (paging.get("items")):
            # total may be 0 or absent, but items key present and empty while
            # we know many public playlists are non-empty → treat as withheld
            # when using client credentials (no user context)
            tracks_withheld = True

        if tracks_withheld:
            owner_name = None
            if pl.get("owner"):
                owner_name = pl["owner"].get("display_name") or pl["owner"].get("id")
            raise SpotifyMetadataError(
                "Spotify returned the playlist details but not its track list.\n\n"
                "This is an <b>access restriction</b>, not an empty playlist.\n"
                "Since late 2025 / 2026 Spotify only returns playlist contents when "
                "the authorized Spotify account <b>owns or collaborates on</b> that playlist.\n\n"
                "This bot currently uses <b>app-only</b> (Client Credentials) Spotify access, "
                "so it can see the name and owner of public playlists but not the songs inside them.\n\n"
                f"Playlist: <b>{pl.get('name') or 'Unknown'}</b>\n"
                f"Owner: {owner_name or '—'}\n"
                f"Reported track count (when available): {reported_total or 'unknown'}\n\n"
                "<b>What you can do:</b>\n"
                "• Use a playlist that the Spotify account linked to this bot’s "
                "Client ID owns or collaborates on.\n"
                "• Or send individual track links instead of a full playlist.\n"
                "• Full per-user Spotify login (so each Telegram user authorizes their own account) "
                "is a larger change and still only unlocks playlists that user owns/collaborates on."
            )

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
            tracks_withheld=False,
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
