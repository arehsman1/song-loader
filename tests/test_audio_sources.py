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


async def test_registry_defaults_to_unavailable(tmp_path):
    with pytest.raises(AudioSourceUnavailable) as exc:
        await audio_registry.obtain("id", "Song", "Artist", tmp_path)
    assert "authorized" in str(exc.value.message).lower() or "source" in str(exc.value.message).lower()
