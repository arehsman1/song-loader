"""
Temporary and persistent file storage manager.
All paths are under the configured DATA_DIR to prevent accidental deletion outside the app.
"""

from __future__ import annotations

import logging
import shutil
import time
import uuid
from pathlib import Path
from typing import Optional

from config import config

logger = logging.getLogger(__name__)


class StorageManager:
    def __init__(self) -> None:
        self.root = config.data_dir
        self.temp_root = config.temp_dir
        self.downloads_root = config.downloads_dir
        self.root.mkdir(parents=True, exist_ok=True)
        self.temp_root.mkdir(parents=True, exist_ok=True)
        self.downloads_root.mkdir(parents=True, exist_ok=True)

    def job_dir(self, job_id: str) -> Path:
        """Unique working directory for a job. Safe path construction."""
        # job_id is expected to be a UUID; still sanitize
        safe_id = "".join(c for c in job_id if c.isalnum() or c in "-_")[:64]
        path = self.temp_root / f"job_{safe_id}"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def create_job_workspace(self, job_id: str) -> Path:
        d = self.job_dir(job_id)
        (d / "raw").mkdir(exist_ok=True)
        (d / "converted").mkdir(exist_ok=True)
        (d / "archives").mkdir(exist_ok=True)
        return d

    def cleanup_job(self, job_id: str, *, keep_outputs: bool = False) -> None:
        d = self.job_dir(job_id)
        if not d.exists():
            return
        try:
            if keep_outputs:
                # Remove only intermediate dirs
                for sub in ("raw", "converted"):
                    p = d / sub
                    if p.exists():
                        shutil.rmtree(p, ignore_errors=True)
            else:
                shutil.rmtree(d, ignore_errors=True)
            logger.info("Cleaned workspace for job %s", job_id)
        except Exception as e:
            logger.warning("Failed to clean job %s: %s", job_id, e)

    def cleanup_stale(self, max_age_hours: Optional[float] = None) -> int:
        """Remove temporary job directories older than retention period."""
        max_age = max_age_hours if max_age_hours is not None else config.temp_file_retention_hours
        cutoff = time.time() - (max_age * 3600)
        removed = 0
        if not self.temp_root.exists():
            return 0
        for child in self.temp_root.iterdir():
            if not child.is_dir() or not child.name.startswith("job_"):
                continue
            try:
                mtime = child.stat().st_mtime
                if mtime < cutoff:
                    shutil.rmtree(child, ignore_errors=True)
                    removed += 1
            except Exception as e:
                logger.warning("Stale cleanup error for %s: %s", child, e)
        return removed

    def safe_path_under(self, base: Path, *parts: str) -> Path:
        """Join parts under base and ensure the result stays inside base (no traversal)."""
        base = base.resolve()
        candidate = base.joinpath(*parts).resolve()
        if not str(candidate).startswith(str(base)):
            raise ValueError("Path traversal detected")
        return candidate


storage = StorageManager()
