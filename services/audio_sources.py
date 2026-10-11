"""
Authorized audio source architecture.

This module deliberately separates Spotify *metadata* from *audio acquisition*.
No implementation here downloads or rips protected Spotify streams, circumvents
DRM, or uses unauthorized cookies/sessions.

A concrete provider is supplied only when a legitimate, documented source whose
terms permit the intended use is available. For general commercial Spotify
catalogue tracks there is no such free public source.

The default provider therefore reports every track as unavailable and explains
why. Additional providers (user-owned files, public-domain archives, licensed
APIs, etc.) can be plugged in without changing Telegram handlers.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from utils.errors import AudioSourceUnavailable

logger = logging.getLogger(__name__)


@dataclass
class AudioResult:
    """Result of a successful authorized acquisition."""
    local_path: Path
    source_name: str
    original_format: str
    bitrate_kbps: Optional[int] = None
    is_exact_match: bool = True
    notes: Optional[str] = None


class AudioProvider(ABC):
    """Interface that every audio source must implement."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    async def can_provide(self, spotify_id: str, title: str, artists: str) -> bool:
        """Return True if this provider believes it can supply an authorized copy."""
        ...

    @abstractmethod
    async def obtain(
        self,
        spotify_id: str,
        title: str,
        artists: str,
        dest_dir: Path,
        *,
        preferred_bitrate: str = "320k",
    ) -> AudioResult:
        """
        Obtain a permitted local audio file.
        Must raise AudioSourceUnavailable if no authorized source exists.
        Must never return a substitute recording without explicit prior confirmation.
        """
        ...


class UnavailableProvider(AudioProvider):
    """
    Default provider: always reports that no authorized downloadable source exists.
    This is intentional and correct for the general Spotify catalogue.
    """

    @property
    def name(self) -> str:
        return "unavailable"

    async def can_provide(self, spotify_id: str, title: str, artists: str) -> bool:
        return False

    async def obtain(
        self,
        spotify_id: str,
        title: str,
        artists: str,
        dest_dir: Path,
        *,
        preferred_bitrate: str = "320k",
    ) -> AudioResult:
        raise AudioSourceUnavailable(
            "No authorized audio source is configured for this track. "
            "Public playlist metadata does not grant permission to download "
            "copyrighted audio. Spotify streams are protected and cannot be "
            "ripped by this bot. "
            "If you own the rights or have a licensed source, a custom provider "
            "can be added in services/audio_sources.py."
        )


class AudioSourceRegistry:
    """Ordered list of providers. First provider that can_provide is tried."""

    def __init__(self) -> None:
        self._providers: List[AudioProvider] = [UnavailableProvider()]

    def register(self, provider: AudioProvider, *, prepend: bool = False) -> None:
        if prepend:
            self._providers.insert(0, provider)
        else:
            self._providers.append(provider)

    async def obtain(
        self,
        spotify_id: str,
        title: str,
        artists: str,
        dest_dir: Path,
        *,
        preferred_bitrate: str = "320k",
    ) -> AudioResult:
        last_error: Optional[Exception] = None
        for provider in self._providers:
            try:
                if await provider.can_provide(spotify_id, title, artists):
                    return await provider.obtain(
                        spotify_id, title, artists, dest_dir,
                        preferred_bitrate=preferred_bitrate,
                    )
            except AudioSourceUnavailable as e:
                last_error = e
                continue
            except Exception as e:
                logger.exception("Provider %s failed unexpectedly", provider.name)
                last_error = e
                continue

        if last_error and isinstance(last_error, AudioSourceUnavailable):
            raise last_error
        raise AudioSourceUnavailable(
            "No authorized audio provider could supply this track. "
            "The bot does not download protected Spotify audio."
        )


# Global registry used by the download manager
audio_registry = AudioSourceRegistry()
