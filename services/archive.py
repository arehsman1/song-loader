"""
ZIP archive creation for permitted audio files only.
Respects configured maximum part size.
"""

from __future__ import annotations

import logging
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config import config
from utils.filenames import sanitize_filename, unique_path

logger = logging.getLogger(__name__)


class ArchiveBuilder:
    def __init__(self, max_bytes: Optional[int] = None) -> None:
        self.max_bytes = max_bytes or config.max_file_size_bytes

    def build_parts(
        self,
        files: List[Tuple[Path, str]],
        dest_dir: Path,
        base_name: str = "playlist",
    ) -> Tuple[List[Path], Dict[str, List[str]]]:
        """
        Package files into one or more ZIP parts, each under max_bytes.
        files: list of (absolute_path, archive_internal_name)
        Returns (list of zip paths, manifest dict with included/skipped).
        """
        dest_dir.mkdir(parents=True, exist_ok=True)
        safe_base = sanitize_filename(base_name) or "playlist"
        parts: List[Path] = []
        included: List[str] = []
        skipped: List[str] = []
        current_files: List[Tuple[Path, str]] = []
        current_size = 0  # approximate uncompressed; zip overhead is small
        part_num = 1

        def flush() -> None:
            nonlocal current_files, current_size, part_num
            if not current_files:
                return
            name = f"{safe_base}_part{part_num:02d}.zip" if part_num > 1 or True else f"{safe_base}.zip"
            # Always use part numbering for clarity when multiple possible
            if len(files) == len(current_files) and part_num == 1:
                name = f"{safe_base}.zip"
            else:
                name = f"{safe_base}_part{part_num:02d}.zip"
            out = unique_path(dest_dir, name)
            try:
                with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                    for src, arcname in current_files:
                        zf.write(src, arcname=arcname)
                final_size = out.stat().st_size
                if final_size > self.max_bytes:
                    # Should be rare if we tracked sizes; remove and mark skipped
                    logger.warning("ZIP %s exceeded limit after creation (%s bytes)", out, final_size)
                    out.unlink(missing_ok=True)
                    for _, arc in current_files:
                        skipped.append(arc)
                else:
                    parts.append(out)
                    for _, arc in current_files:
                        included.append(arc)
            except Exception as e:
                logger.exception("ZIP creation failed")
                for _, arc in current_files:
                    skipped.append(arc)
                if out.exists():
                    out.unlink(missing_ok=True)
            current_files = []
            current_size = 0
            part_num += 1

        for src, arcname in files:
            if not src.is_file():
                skipped.append(arcname)
                continue
            size = src.stat().st_size
            if size > self.max_bytes:
                # Single file cannot fit in any archive of the allowed size
                skipped.append(arcname)
                logger.info("File %s (%s bytes) exceeds archive limit, skipped", arcname, size)
                continue
            if current_size + size > self.max_bytes and current_files:
                flush()
            current_files.append((src, arcname))
            current_size += size

        flush()
        manifest = {"included": included, "skipped": skipped}
        return parts, manifest
