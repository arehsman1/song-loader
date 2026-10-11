"""
SQLite persistence for user settings, jobs, and track status.
Uses aiosqlite for async access. Schema is versioned.
"""

from __future__ import annotations

import json
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

import aiosqlite

from config import config

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

_CREATE_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    settings_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    owner_id INTEGER NOT NULL,
    job_type TEXT NOT NULL,          -- playlist | track | selection | zip
    title TEXT,
    source_url TEXT,
    status TEXT NOT NULL,            -- pending | running | completed | partial | failed | cancelled
    total_tracks INTEGER NOT NULL DEFAULT 0,
    successful INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    skipped INTEGER NOT NULL DEFAULT 0,
    delivery_mode TEXT NOT NULL DEFAULT 'individual',
    settings_snapshot TEXT,
    error_summary TEXT,
    created_at REAL NOT NULL,
    started_at REAL,
    completed_at REAL,
    FOREIGN KEY (owner_id) REFERENCES users(telegram_id)
);

CREATE INDEX IF NOT EXISTS idx_jobs_owner ON jobs(owner_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at DESC);

CREATE TABLE IF NOT EXISTS job_tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    track_index INTEGER NOT NULL,    -- 0-based playlist order
    spotify_id TEXT,
    title TEXT,
    artists TEXT,
    status TEXT NOT NULL,            -- pending | downloading | converting | uploading | success | failed | skipped | cancelled
    error_category TEXT,
    error_message TEXT,
    output_path TEXT,
    file_size INTEGER,
    retry_count INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE,
    UNIQUE(job_id, track_index)
);

CREATE INDEX IF NOT EXISTS idx_job_tracks_job ON job_tracks(job_id);

CREATE TABLE IF NOT EXISTS selections (
    user_id INTEGER NOT NULL,
    playlist_id TEXT NOT NULL,
    selected_indices_json TEXT NOT NULL DEFAULT '[]',
    updated_at REAL NOT NULL,
    PRIMARY KEY (user_id, playlist_id)
);
"""


class Database:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or config.database_path
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(str(self.path), timeout=30.0)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._conn.execute("PRAGMA journal_mode = WAL")
        await self._init_schema()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[aiosqlite.Connection]:
        assert self._conn is not None
        await self._conn.execute("BEGIN")
        try:
            yield self._conn
            await self._conn.commit()
        except Exception:
            await self._conn.rollback()
            raise

    async def _init_schema(self) -> None:
        assert self._conn is not None
        await self._conn.executescript(_CREATE_SQL)
        cur = await self._conn.execute("SELECT version FROM schema_version LIMIT 1")
        row = await cur.fetchone()
        if row is None:
            await self._conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,)
            )
            await self._conn.commit()
        else:
            # Future migrations would go here
            pass

    # ----- Users & settings -----

    async def ensure_user(self, telegram_id: int) -> None:
        now = time.time()
        await self._conn.execute(
            """
            INSERT INTO users (telegram_id, settings_json, created_at, updated_at)
            VALUES (?, '{}', ?, ?)
            ON CONFLICT(telegram_id) DO NOTHING
            """,
            (telegram_id, now, now),
        )
        await self._conn.commit()

    async def get_user_settings(self, telegram_id: int) -> Dict[str, Any]:
        await self.ensure_user(telegram_id)
        cur = await self._conn.execute(
            "SELECT settings_json FROM users WHERE telegram_id = ?", (telegram_id,)
        )
        row = await cur.fetchone()
        if not row:
            return self._default_settings()
        try:
            data = json.loads(row["settings_json"] or "{}")
        except json.JSONDecodeError:
            data = {}
        defaults = self._default_settings()
        defaults.update(data)
        return defaults

    async def set_user_settings(self, telegram_id: int, settings: Dict[str, Any]) -> None:
        await self.ensure_user(telegram_id)
        now = time.time()
        await self._conn.execute(
            "UPDATE users SET settings_json = ?, updated_at = ? WHERE telegram_id = ?",
            (json.dumps(settings), now, telegram_id),
        )
        await self._conn.commit()

    def _default_settings(self) -> Dict[str, Any]:
        return {
            "audio_bitrate": config.default_audio_bitrate,
            "delivery_mode": config.default_delivery_mode,
            "zip_enabled": False,
            "max_tracks_per_job": config.max_tracks_per_job,
        }

    # ----- Jobs -----

    async def create_job(
        self,
        job_id: str,
        owner_id: int,
        job_type: str,
        title: Optional[str],
        source_url: Optional[str],
        total_tracks: int,
        delivery_mode: str,
        settings_snapshot: Optional[Dict] = None,
    ) -> None:
        await self.ensure_user(owner_id)
        now = time.time()
        await self._conn.execute(
            """
            INSERT INTO jobs (
                id, owner_id, job_type, title, source_url, status,
                total_tracks, delivery_mode, settings_snapshot, created_at
            ) VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)
            """,
            (
                job_id,
                owner_id,
                job_type,
                title,
                source_url,
                total_tracks,
                delivery_mode,
                json.dumps(settings_snapshot or {}),
                now,
            ),
        )
        await self._conn.commit()

    async def add_job_tracks(
        self,
        job_id: str,
        tracks: List[Dict[str, Any]],
    ) -> None:
        """tracks: list of {track_index, spotify_id, title, artists}"""
        rows = [
            (
                job_id,
                t["track_index"],
                t.get("spotify_id"),
                t.get("title"),
                t.get("artists"),
                "pending",
            )
            for t in tracks
        ]
        await self._conn.executemany(
            """
            INSERT INTO job_tracks (job_id, track_index, spotify_id, title, artists, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        await self._conn.commit()

    async def update_job_status(
        self,
        job_id: str,
        status: str,
        *,
        successful: Optional[int] = None,
        failed: Optional[int] = None,
        skipped: Optional[int] = None,
        error_summary: Optional[str] = None,
        started: bool = False,
        completed: bool = False,
    ) -> None:
        now = time.time()
        fields = ["status = ?"]
        params: List[Any] = [status]
        if successful is not None:
            fields.append("successful = ?")
            params.append(successful)
        if failed is not None:
            fields.append("failed = ?")
            params.append(failed)
        if skipped is not None:
            fields.append("skipped = ?")
            params.append(skipped)
        if error_summary is not None:
            fields.append("error_summary = ?")
            params.append(error_summary)
        if started:
            fields.append("started_at = ?")
            params.append(now)
        if completed:
            fields.append("completed_at = ?")
            params.append(now)
        params.append(job_id)
        await self._conn.execute(
            f"UPDATE jobs SET {', '.join(fields)} WHERE id = ?", params
        )
        await self._conn.commit()

    async def update_track_status(
        self,
        job_id: str,
        track_index: int,
        status: str,
        *,
        error_category: Optional[str] = None,
        error_message: Optional[str] = None,
        output_path: Optional[str] = None,
        file_size: Optional[int] = None,
        increment_retry: bool = False,
    ) -> None:
        fields = ["status = ?"]
        params: List[Any] = [status]
        if error_category is not None:
            fields.append("error_category = ?")
            params.append(error_category)
        if error_message is not None:
            fields.append("error_message = ?")
            params.append(error_message)
        if output_path is not None:
            fields.append("output_path = ?")
            params.append(output_path)
        if file_size is not None:
            fields.append("file_size = ?")
            params.append(file_size)
        if increment_retry:
            fields.append("retry_count = retry_count + 1")
        params.extend([job_id, track_index])
        await self._conn.execute(
            f"UPDATE job_tracks SET {', '.join(fields)} WHERE job_id = ? AND track_index = ?",
            params,
        )
        await self._conn.commit()

    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        cur = await self._conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

    async def get_user_jobs(
        self, owner_id: int, limit: int = 20
    ) -> List[Dict[str, Any]]:
        cur = await self._conn.execute(
            """
            SELECT * FROM jobs
            WHERE owner_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (owner_id, limit),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def get_active_jobs(self, owner_id: int) -> List[Dict[str, Any]]:
        cur = await self._conn.execute(
            """
            SELECT * FROM jobs
            WHERE owner_id = ? AND status IN ('pending', 'running')
            ORDER BY created_at DESC
            """,
            (owner_id,),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def get_job_tracks(self, job_id: str) -> List[Dict[str, Any]]:
        cur = await self._conn.execute(
            """
            SELECT * FROM job_tracks
            WHERE job_id = ?
            ORDER BY track_index ASC
            """,
            (job_id,),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def get_failed_tracks(self, job_id: str) -> List[Dict[str, Any]]:
        cur = await self._conn.execute(
            """
            SELECT * FROM job_tracks
            WHERE job_id = ? AND status IN ('failed', 'skipped')
            ORDER BY track_index ASC
            """,
            (job_id,),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def count_user_active_jobs(self, owner_id: int) -> int:
        cur = await self._conn.execute(
            """
            SELECT COUNT(*) AS c FROM jobs
            WHERE owner_id = ? AND status IN ('pending', 'running')
            """,
            (owner_id,),
        )
        row = await cur.fetchone()
        return int(row["c"]) if row else 0

    async def count_global_active_jobs(self) -> int:
        cur = await self._conn.execute(
            "SELECT COUNT(*) AS c FROM jobs WHERE status IN ('pending', 'running')"
        )
        row = await cur.fetchone()
        return int(row["c"]) if row else 0

    # ----- Selections (server-side track selection state) -----

    async def get_selection(self, user_id: int, playlist_id: str) -> List[int]:
        cur = await self._conn.execute(
            "SELECT selected_indices_json FROM selections WHERE user_id = ? AND playlist_id = ?",
            (user_id, playlist_id),
        )
        row = await cur.fetchone()
        if not row:
            return []
        try:
            return list(json.loads(row["selected_indices_json"] or "[]"))
        except json.JSONDecodeError:
            return []

    async def set_selection(
        self, user_id: int, playlist_id: str, indices: List[int]
    ) -> None:
        now = time.time()
        await self._conn.execute(
            """
            INSERT INTO selections (user_id, playlist_id, selected_indices_json, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, playlist_id) DO UPDATE SET
                selected_indices_json = excluded.selected_indices_json,
                updated_at = excluded.updated_at
            """,
            (user_id, playlist_id, json.dumps(sorted(set(indices))), now),
        )
        await self._conn.commit()

    async def clear_selection(self, user_id: int, playlist_id: str) -> None:
        await self._conn.execute(
            "DELETE FROM selections WHERE user_id = ? AND playlist_id = ?",
            (user_id, playlist_id),
        )
        await self._conn.commit()


# Module-level helper
_db: Optional[Database] = None


async def get_db() -> Database:
    global _db
    if _db is None:
        _db = Database()
        await _db.connect()
    return _db
