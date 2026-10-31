"""
Audio provider chain for song-loader.

Fallback order (public sources only — no Spotify stream ripping):
    1. SpotdlProvider  — Spotify metadata + matching public audio (via spotdl)
    2. YtDlpProvider   — direct yt-dlp search + download, tagged with Spotify metadata

The registry tries each provider in order and fails forward on
AudioSourceUnavailable. If all fail, the track is marked skipped by
DownloadManager.

This module does NOT:
  - decrypt or rip protected Spotify streams
  - use private cookies / session tokens (e.g. SPOTIFY_SP_DC)
  - circumvent DRM
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from utils.errors import AudioSourceUnavailable
from utils.filenames import sanitize_filename

logger = logging.getLogger(__name__)


# ────────────────────────────  base types  ────────────────────────────

@dataclass
class AudioResult:
    """Result of a successful acquisition from a public source."""
    local_path: Path
    source_name: str
    original_format: str = "mp3"
    bitrate_kbps: Optional[int] = 320
    is_exact_match: bool = False
    notes: Optional[str] = None


class AudioProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def can_provide(
        self, spotify_id: str, title: str, artists: str
    ) -> bool: ...

    @abstractmethod
    async def obtain(
        self,
        spotify_id: str,
        title: str,
        artists: str,
        dest_dir: Path,
        *,
        preferred_bitrate: str = "320k",
    ) -> AudioResult: ...


class AudioSourceRegistry:
    def __init__(self) -> None:
        self._providers: List[AudioProvider] = []

    def register(self, provider: AudioProvider, *, prepend: bool = False) -> None:
        if prepend:
            self._providers.insert(0, provider)
        else:
            self._providers.append(provider)

    @property
    def providers(self) -> List[AudioProvider]:
        return list(self._providers)

    async def obtain(
        self,
        spotify_id: str,
        title: str,
        artists: str,
        dest_dir: Path,
        *,
        preferred_bitrate: str = "320k",
    ) -> AudioResult:
        if not self._providers:
            raise AudioSourceUnavailable("No audio providers registered.")
        failures: List[str] = []
        for provider in self._providers:
            try:
                if not await provider.can_provide(spotify_id, title, artists):
                    failures.append(f"{provider.name}: not applicable")
                    continue
            except Exception as exc:
                failures.append(f"{provider.name}: can_provide error: {exc}")
                continue
            try:
                result = await provider.obtain(
                    spotify_id,
                    title,
                    artists,
                    dest_dir,
                    preferred_bitrate=preferred_bitrate,
                )
                logger.info(
                    "Provider %s succeeded for '%s' → %s",
                    provider.name, title, result.local_path.name,
                )
                return result
            except AudioSourceUnavailable as exc:
                failures.append(f"{provider.name}: {exc}")
                continue
            except Exception as exc:
                failures.append(f"{provider.name}: unexpected error: {exc}")
                logger.exception("Provider %s unexpected failure", provider.name)
                continue
        joined = " | ".join(failures) if failures else "no attempts made"
        raise AudioSourceUnavailable(
            f"No provider could obtain audio for '{title}'. Attempts: {joined}"
        )


class UnavailableProvider(AudioProvider):
    """Kept for compatibility / tests; not registered in the default chain."""

    @property
    def name(self) -> str:
        return "unavailable"

    async def can_provide(self, spotify_id: str, title: str, artists: str) -> bool:
        return False

    async def obtain(self, *args, **kwargs) -> AudioResult:
        raise AudioSourceUnavailable(
            "UnavailableProvider never provides audio. Use a real provider."
        )


# ────────────────────────────  shared helpers  ────────────────────────────

def _newest_file(dest_dir: Path, stem_hint: str) -> Optional[Path]:
    """Find the file a downloader just produced, robust to name mangling."""
    candidates = sorted(
        (p for p in dest_dir.iterdir() if p.is_file() and not p.name.startswith(".")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return None
    hint = stem_hint.lower()
    for p in candidates:
        if hint in p.name.lower():
            return p
    return candidates[0]


async def _run(cmd: List[str], timeout: float = 240.0) -> tuple[int, bytes, bytes]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        try:
            await proc.wait()
        except Exception:
            pass
        raise AudioSourceUnavailable(f"timeout after {timeout}s: {' '.join(cmd[:3])}")
    return proc.returncode, out, err


# ────────────────────────────  1. SpotdlProvider  ────────────────────────────

class SpotdlProvider(AudioProvider):
    """Spotify metadata + matching public audio source via spotdl."""

    @property
    def name(self) -> str:
        return "spotdl"

    async def can_provide(self, spotify_id: str, title: str, artists: str) -> bool:
        return shutil.which("spotdl") is not None

    async def obtain(
        self,
        spotify_id: str,
        title: str,
        artists: str,
        dest_dir: Path,
        *,
        preferred_bitrate: str = "320k",
    ) -> AudioResult:
        spotdl = shutil.which("spotdl")
        if not spotdl:
            raise AudioSourceUnavailable(
                "spotdl not installed. Run: pip install spotdl"
            )

        dest_dir.mkdir(parents=True, exist_ok=True)
        safe_artist = sanitize_filename(artists.split(",")[0].strip() or "Unknown Artist")
        safe_title = sanitize_filename(title or "Unknown Title")
        stem = f"{safe_artist} - {safe_title}"
        output_template = str(dest_dir / f"{stem}.{{output-ext}}")
        bitrate = preferred_bitrate if preferred_bitrate.endswith("k") else f"{preferred_bitrate}k"

        cmd = [
            spotdl,
            "download",
            f"https://open.spotify.com/track/{spotify_id}",
            "--output", output_template,
            "--format", "mp3",
            "--bitrate", bitrate,
            "--overwrite", "skip",
            "--print-errors",
        ]
        rc, _, err = await _run(cmd, timeout=240)
        if rc != 0:
            raise AudioSourceUnavailable(
                f"spotdl exit {rc}: {err.decode(errors='replace')[:300]}"
            )

        local_path = _newest_file(dest_dir, safe_title)
        if not local_path or not local_path.is_file():
            raise AudioSourceUnavailable("spotdl produced no file.")
        ext = local_path.suffix.lstrip(".").lower() or "mp3"
        try:
            kbps = int(bitrate.rstrip("k") or 320)
        except ValueError:
            kbps = 320
        return AudioResult(
            local_path=local_path,
            source_name="spotdl",
            original_format=ext,
            bitrate_kbps=kbps,
            is_exact_match=False,
            notes="Audio from matching public source; metadata from Spotify.",
        )


# ────────────────────────────  2. YtDlpProvider  ────────────────────────────

class YtDlpProvider(AudioProvider):
    """
    Last-resort: search YouTube via yt-dlp, download audio, tag with Spotify
    metadata via mutagen. Independent of Spotify audio streams entirely.
    """

    @property
    def name(self) -> str:
        return "yt-dlp"

    async def can_provide(self, spotify_id: str, title: str, artists: str) -> bool:
        return shutil.which("yt-dlp") is not None

    async def obtain(
        self,
        spotify_id: str,
        title: str,
        artists: str,
        dest_dir: Path,
        *,
        preferred_bitrate: str = "320k",
    ) -> AudioResult:
        ytdlp = shutil.which("yt-dlp")
        if not ytdlp:
            raise AudioSourceUnavailable(
                "yt-dlp not installed. Run: pip install yt-dlp"
            )

        dest_dir.mkdir(parents=True, exist_ok=True)
        safe_artist = sanitize_filename(artists.split(",")[0].strip() or "Unknown Artist")
        safe_title = sanitize_filename(title or "Unknown Title")
        stem = f"{safe_artist} - {safe_title}"
        output_template = str(dest_dir / f"{stem}.%(ext)s")

        query = f"ytsearch1:{artists} - {title} audio"
        cmd = [
            ytdlp,
            query,
            "-x",
            "--audio-format", "mp3",
            "--audio-quality", "0",
            "-o", output_template,
            "--no-playlist",
            "--no-warnings",
            "--print", "after_move:filepath",
        ]
        rc, out, err = await _run(cmd, timeout=240)
        if rc != 0:
            raise AudioSourceUnavailable(
                f"yt-dlp exit {rc}: {err.decode(errors='replace')[:300]}"
            )

        printed = out.decode(errors="replace").strip().splitlines()
        local_path: Optional[Path] = None
        for line in reversed(printed):
            cand = Path(line.strip())
            if cand.is_file():
                local_path = cand
                break
        if not local_path:
            local_path = _newest_file(dest_dir, safe_title)
        if not local_path or not local_path.is_file():
            raise AudioSourceUnavailable("yt-dlp produced no file.")

        # Best-effort metadata tagging (won't fail the download)
        try:
            from mutagen.easyid3 import EasyID3
            from mutagen.id3 import ID3
            if local_path.suffix.lower() == ".mp3":
                try:
                    tags = EasyID3(str(local_path))
                except Exception:
                    ID3().save(str(local_path))
                    tags = EasyID3(str(local_path))
                tags["title"] = title
                tags["artist"] = artists
                tags.save()
        except Exception:
            pass

        ext = local_path.suffix.lstrip(".").lower() or "mp3"
        return AudioResult(
            local_path=local_path,
            source_name="yt-dlp",
            original_format=ext,
            bitrate_kbps=192,
            is_exact_match=False,
            notes="Audio from YouTube search; metadata written from Spotify track info.",
        )


# ────────────────────────────  default chain  ────────────────────────────

def build_default_registry() -> AudioSourceRegistry:
    """
    Order: higher-quality / better-matched public source first.
    Each provider fails forward on AudioSourceUnavailable.
    """
    reg = AudioSourceRegistry()
    reg.register(SpotdlProvider())   # 1. public source + Spotify metadata
    reg.register(YtDlpProvider())    # 2. direct yt-dlp pull
    return reg


audio_registry = build_default_registry()
