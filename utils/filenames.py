"""Safe filename sanitization and unique path helpers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional


# Characters that are unsafe on Windows / common filesystems
_UNSAFE_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WHITESPACE_RE = re.compile(r"\s+")


def sanitize_filename(name: str, max_length: int = 180, replacement: str = "_") -> str:
    """
    Produce a filesystem-safe filename while preserving as much of the original
    as possible. Does not add track numbers. Does not interpret the name as a command.
    """
    if not name or not isinstance(name, str):
        return "unnamed"

    # Normalize whitespace
    name = _WHITESPACE_RE.sub(" ", name.strip())
    # Remove/replace unsafe characters
    name = _UNSAFE_RE.sub(replacement, name)
    # Avoid leading/trailing dots and spaces (Windows)
    name = name.strip(". ")
    if not name:
        name = "unnamed"

    # Truncate while trying to keep extension
    if len(name) > max_length:
        if "." in name:
            stem, ext = name.rsplit(".", 1)
            keep = max_length - len(ext) - 1
            if keep > 0:
                name = f"{stem[:keep]}.{ext}"
            else:
                name = name[:max_length]
        else:
            name = name[:max_length]

    return name


def unique_path(directory: Path, filename: str) -> Path:
    """
    Return a Path inside directory that does not yet exist.
    If filename exists, append _1, _2, ... before the extension.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    candidate = directory / filename
    if not candidate.exists():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    counter = 1
    while True:
        new_name = f"{stem}_{counter}{suffix}"
        candidate = directory / new_name
        if not candidate.exists():
            return candidate
        counter += 1
        if counter > 10_000:
            raise RuntimeError(f"Could not find unique name for {filename} in {directory}")
