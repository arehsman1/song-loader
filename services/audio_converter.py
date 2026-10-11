"""
FFmpeg-based conversion for permitted source files only.
Never claims that upsampling improves quality.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path
from typing import Optional, Tuple

from config import config
from utils.errors import ConversionError
from utils.filenames import sanitize_filename, unique_path

logger = logging.getLogger(__name__)


def _find_executable(name: str, configured: Optional[str]) -> Optional[str]:
    if configured:
        p = Path(configured)
        if p.is_file():
            return str(p)
    return shutil.which(name)


class AudioConverter:
    def __init__(self) -> None:
        self.ffmpeg = _find_executable("ffmpeg", config.ffmpeg_path)
        self.ffprobe = _find_executable("ffprobe", config.ffprobe_path)

    def is_available(self) -> bool:
        return bool(self.ffmpeg and self.ffprobe)

    async def probe(self, path: Path) -> dict:
        if not self.ffprobe:
            raise ConversionError("FFprobe is not available.")
        cmd = [
            self.ffprobe,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(path),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise ConversionError(f"ffprobe failed: {stderr.decode(errors='replace')[:300]}")
        import json
        return json.loads(stdout.decode())

    async def convert_to_mp3(
        self,
        source: Path,
        dest_dir: Path,
        *,
        bitrate: str = "320k",
        preferred_name: Optional[str] = None,
    ) -> Path:
        """
        Convert source to MP3 at the requested bitrate if the source is not already
        a suitable MP3. Does not upsample in the sense of inventing quality;
        FFmpeg will re-encode. Caller must ensure conversion is permitted.
        """
        if not self.ffmpeg:
            raise ConversionError(
                "FFmpeg is not installed or not found on PATH. "
                "Install FFmpeg to enable format conversion."
            )
        if not source.is_file():
            raise ConversionError(f"Source file does not exist: {source}")

        name = preferred_name or source.stem
        safe = sanitize_filename(f"{name}.mp3")
        out = unique_path(dest_dir, safe)

        # Simple re-encode; avoid unnecessary work if already mp3 at target (best-effort)
        cmd = [
            self.ffmpeg,
            "-y",
            "-i", str(source),
            "-vn",
            "-codec:a", "libmp3lame",
            "-b:a", bitrate,
            "-map_metadata", "0",
            str(out),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0 or not out.is_file():
            err = stderr.decode(errors="replace")[:400]
            raise ConversionError(f"FFmpeg conversion failed: {err}")
        return out

    async def inspect_size_and_format(self, path: Path) -> Tuple[int, str]:
        size = path.stat().st_size
        fmt = path.suffix.lower().lstrip(".") or "unknown"
        return size, fmt


converter = AudioConverter()
