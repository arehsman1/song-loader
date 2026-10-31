"""Audio provider interface tests – no real downloads."""

import pytest
from pathlib import Path

from services.audio_sources import UnavailableProvider, audio_registry
from utils.errors import AudioSourceUnavailable

pytestmark = pytest.mark.asyncio


async def test_unavailable_provider(tmp_path):
    p = UnavailableProvider()
    assert await p.can_provide("id", "title", "artist") is False
    with pytest.raises(AudioSourceUnavailable):
        await p.obtain("id", "title", "artist", tmp_path)


async def test_registry_has_public_providers():
    names = [p.name for p in audio_registry.providers]
    assert names == ["spotdl", "yt-dlp"]


async def test_registry_fails_forward_when_binaries_missing(tmp_path):
    """Without spotdl/yt-dlp on PATH, obtain should still raise AudioSourceUnavailable."""
    with pytest.raises(AudioSourceUnavailable) as exc:
        await audio_registry.obtain("id", "Song", "Artist", tmp_path)
    msg = str(exc.value.message).lower()
    assert "no provider" in msg or "spotdl" in msg or "yt-dlp" in msg or "not applicable" in msg
