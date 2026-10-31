"""
Sequential download / processing manager.
Respects per-user and global concurrency limits, cancellation, and playlist order.
Audio is obtained only through the authorized audio_sources registry.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from aiogram import Bot
from aiogram.types import FSInputFile

from config import config
from database import get_db
from services.archive import ArchiveBuilder
from services.audio_converter import converter
from services.audio_sources import audio_registry
from services.playlist_reader import PlaylistMeta, TrackMeta, playlist_reader
from services.progress import ProgressReporter
from services.storage import storage
from utils.errors import (
    AudioSourceUnavailable,
    FileTooLargeError,
    JobCancelledError,
    SpotifyMetadataError,
)
from utils.filenames import sanitize_filename, unique_path

logger = logging.getLogger(__name__)

# In-memory cancellation set and active task tracking
_cancelled_jobs: Set[str] = set()
_running_tasks: Dict[str, asyncio.Task] = {}
_global_sem = asyncio.Semaphore(config.max_global_concurrent_jobs)
_user_sems: Dict[int, asyncio.Semaphore] = {}


def _user_sem(user_id: int) -> asyncio.Semaphore:
    if user_id not in _user_sems:
        _user_sems[user_id] = asyncio.Semaphore(config.max_concurrent_jobs_per_user)
    return _user_sems[user_id]


def request_cancel(job_id: str) -> None:
    _cancelled_jobs.add(job_id)
    task = _running_tasks.get(job_id)
    if task and not task.done():
        task.cancel()


def is_cancelled(job_id: str) -> bool:
    return job_id in _cancelled_jobs


class DownloadManager:
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def start_playlist_job(
        self,
        user_id: int,
        chat_id: int,
        playlist: PlaylistMeta,
        *,
        selected_indices: Optional[List[int]] = None,
        delivery_mode: str = "individual",
        settings: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create job record and launch background processing. Returns job_id."""
        db = await get_db()
        active = await db.count_user_active_jobs(user_id)
        if active >= config.max_concurrent_jobs_per_user:
            raise RuntimeError(
                f"You already have {active} active job(s). "
                "Cancel one or wait for it to finish."
            )
        global_active = await db.count_global_active_jobs()
        if global_active >= config.max_global_concurrent_jobs:
            raise RuntimeError(
                "The bot is currently at maximum capacity. Please try again shortly."
            )

        tracks = playlist.tracks
        if selected_indices is not None:
            tracks = [playlist.tracks[i] for i in selected_indices if 0 <= i < len(playlist.tracks)]

        if len(tracks) > config.max_tracks_per_job:
            raise RuntimeError(
                f"This selection has {len(tracks)} tracks; "
                f"the maximum per job is {config.max_tracks_per_job}."
            )

        job_id = str(uuid.uuid4())
        settings = settings or {}
        await db.create_job(
            job_id=job_id,
            owner_id=user_id,
            job_type="playlist" if selected_indices is None else "selection",
            title=playlist.name,
            source_url=playlist.external_url,
            total_tracks=len(tracks),
            delivery_mode=delivery_mode,
            settings_snapshot=settings,
        )
        track_rows = [
            {
                "track_index": i,
                "spotify_id": t.spotify_id,
                "title": t.name,
                "artists": t.artists,
            }
            for i, t in enumerate(tracks)
        ]
        await db.add_job_tracks(job_id, track_rows)

        workspace = storage.create_job_workspace(job_id)
        task = asyncio.create_task(
            self._run_job(
                job_id=job_id,
                user_id=user_id,
                chat_id=chat_id,
                tracks=tracks,
                playlist_name=playlist.name,
                delivery_mode=delivery_mode,
                settings=settings,
                workspace=workspace,
            )
        )
        _running_tasks[job_id] = task
        task.add_done_callback(lambda t: _running_tasks.pop(job_id, None))
        return job_id

    async def _run_job(
        self,
        job_id: str,
        user_id: int,
        chat_id: int,
        tracks: List[TrackMeta],
        playlist_name: str,
        delivery_mode: str,
        settings: Dict[str, Any],
        workspace: Path,
    ) -> None:
        db = await get_db()
        reporter = ProgressReporter(self.bot, chat_id)
        await reporter.start(
            f"🎧 Starting job <code>{job_id[:8]}…</code>\n"
            f"Playlist: {playlist_name}\n"
            f"Tracks: {len(tracks)}\n"
            f"Mode: {delivery_mode}"
        )
        await db.update_job_status(job_id, "running", started=True)

        successful = 0
        failed = 0
        skipped = 0
        collected_files: List[tuple[Path, str]] = []  # for ZIP mode
        bitrate = settings.get("audio_bitrate") or config.default_audio_bitrate

        async with _global_sem:
            async with _user_sem(user_id):
                for idx, track in enumerate(tracks):
                    if is_cancelled(job_id):
                        await db.update_track_status(job_id, idx, "cancelled")
                        break

                    await reporter.update(
                        job_id=job_id,
                        playlist_name=playlist_name,
                        current=idx + 1,
                        total=len(tracks),
                        successful=successful,
                        failed=failed,
                        skipped=skipped,
                        current_title=f"{track.name} – {track.artists}",
                        phase="Looking for authorized source",
                    )

                    try:
                        result = await audio_registry.obtain(
                            track.spotify_id,
                            track.name,
                            track.artists,
                            workspace / "raw",
                            preferred_bitrate=bitrate,
                        )
                        # Optional conversion
                        out_path = result.local_path
                        if out_path.suffix.lower() != ".mp3" and converter.is_available():
                            try:
                                out_path = await converter.convert_to_mp3(
                                    result.local_path,
                                    workspace / "converted",
                                    bitrate=bitrate,
                                    preferred_name=f"{track.artists} - {track.name}",
                                )
                            except Exception as conv_err:
                                logger.warning("Conversion skipped: %s", conv_err)

                        size = out_path.stat().st_size
                        if size > config.max_file_size_bytes:
                            await db.update_track_status(
                                job_id, idx, "skipped",
                                error_category="too_large",
                                error_message=f"File {size} bytes exceeds {config.max_file_size_mib} MiB limit",
                            )
                            skipped += 1
                            continue

                        safe_name = sanitize_filename(
                            f"{track.artists} - {track.name}{out_path.suffix}"
                        )
                        if delivery_mode == "individual":
                            await self._send_audio(
                                chat_id, out_path, safe_name, track.name, track.artists
                            )
                            await db.update_track_status(
                                job_id, idx, "success",
                                output_path=str(out_path),
                                file_size=size,
                            )
                            successful += 1
                        else:
                            collected_files.append((out_path, safe_name))
                            await db.update_track_status(
                                job_id, idx, "success",
                                output_path=str(out_path),
                                file_size=size,
                            )
                            successful += 1

                    except AudioSourceUnavailable as e:
                        await db.update_track_status(
                            job_id, idx, "skipped",
                            error_category="no_source",
                            error_message=str(e.message)[:500],
                        )
                        skipped += 1
                    except asyncio.CancelledError:
                        await db.update_track_status(job_id, idx, "cancelled")
                        raise
                    except Exception as e:
                        logger.exception("Track %s failed", track.spotify_id)
                        await db.update_track_status(
                            job_id, idx, "failed",
                            error_category="error",
                            error_message=str(e)[:500],
                        )
                        failed += 1

                    await reporter.update(
                        job_id=job_id,
                        playlist_name=playlist_name,
                        current=idx + 1,
                        total=len(tracks),
                        successful=successful,
                        failed=failed,
                        skipped=skipped,
                        current_title=track.name,
                        phase="Processing",
                    )

                # ZIP delivery
                if delivery_mode == "zip" and collected_files and not is_cancelled(job_id):
                    await reporter.update(
                        job_id=job_id,
                        playlist_name=playlist_name,
                        current=len(tracks),
                        total=len(tracks),
                        successful=successful,
                        failed=failed,
                        skipped=skipped,
                        phase="Creating ZIP archive(s)",
                        force=True,
                    )
                    builder = ArchiveBuilder()
                    parts, manifest = builder.build_parts(
                        collected_files,
                        workspace / "archives",
                        base_name=sanitize_filename(playlist_name) or "playlist",
                    )
                    for part in parts:
                        if part.stat().st_size > config.max_file_size_bytes:
                            logger.warning("Archive part still too large: %s", part)
                            continue
                        try:
                            await self.bot.send_document(
                                chat_id,
                                FSInputFile(part, filename=part.name),
                                caption=f"Archive part for {playlist_name}",
                            )
                        except Exception as e:
                            logger.exception("Failed to send ZIP part")
                            failed += 1

                final_status = "cancelled" if is_cancelled(job_id) else (
                    "completed" if failed == 0 and skipped == 0 else "partial"
                )
                await db.update_job_status(
                    job_id,
                    final_status,
                    successful=successful,
                    failed=failed,
                    skipped=skipped,
                    completed=True,
                    error_summary=(
                        "No authorized audio sources were available for any track. "
                        "This bot does not rip Spotify streams."
                        if successful == 0 and skipped > 0
                        else None
                    ),
                )

                summary = (
                    f"🏁 <b>Job finished</b>\n"
                    f"ID: <code>{job_id[:8]}…</code>\n"
                    f"Playlist: {playlist_name}\n"
                    f"Status: {final_status}\n"
                    f"✅ {successful}  ❌ {failed}  ⏭ {skipped}\n\n"
                )
                if successful == 0:
                    summary += (
                        "⚠️ <b>No audio files were delivered.</b>\n"
                        "Public Spotify playlist metadata does not grant download rights. "
                        "This bot never rips protected Spotify streams. "
                        "Only tracks from an explicitly authorized audio provider can be sent."
                    )
                await reporter.finish(summary)

        # Cleanup temp files (keep nothing by default)
        try:
            storage.cleanup_job(job_id, keep_outputs=False)
        except Exception:
            pass
        _cancelled_jobs.discard(job_id)

    async def _send_audio(
        self,
        chat_id: int,
        path: Path,
        filename: str,
        title: str,
        performer: str,
    ) -> None:
        size = path.stat().st_size
        if size > config.max_file_size_bytes:
            raise FileTooLargeError(
                f"File exceeds the {config.max_file_size_mib} MiB safety limit."
            )
        try:
            await self.bot.send_audio(
                chat_id,
                FSInputFile(path, filename=filename),
                title=title[:64],
                performer=performer[:64],
            )
        except Exception as e:
            logger.exception("Telegram send_audio failed")
            # Fallback to document
            await self.bot.send_document(
                chat_id,
                FSInputFile(path, filename=filename),
                caption=f"{performer} – {title}",
            )


# Factory used by handlers
def get_download_manager(bot: Bot) -> DownloadManager:
    return DownloadManager(bot)
