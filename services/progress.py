"""
Progress reporting helpers. Avoid flooding Telegram with edits.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter

logger = logging.getLogger(__name__)


class ProgressReporter:
    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        *,
        min_interval_seconds: float = 3.0,
    ) -> None:
        self.bot = bot
        self.chat_id = chat_id
        self.min_interval = min_interval_seconds
        self._last_edit = 0.0
        self._message_id: Optional[int] = None
        self._last_text: str = ""

    async def start(self, text: str) -> None:
        try:
            msg = await self.bot.send_message(self.chat_id, text)
            self._message_id = msg.message_id
            self._last_text = text
            self._last_edit = time.time()
        except TelegramAPIError as e:
            logger.warning("Could not send initial progress message: %s", e)

    async def update(
        self,
        *,
        job_id: str,
        playlist_name: str,
        current: int,
        total: int,
        successful: int,
        failed: int,
        skipped: int,
        current_title: str = "",
        phase: str = "Processing",
        force: bool = False,
    ) -> None:
        pct = int((current / total) * 100) if total else 0
        text = (
            f"🎧 <b>Spotify Playlist Job</b>\n"
            f"ID: <code>{job_id[:8]}…</code>\n"
            f"Playlist: {playlist_name}\n"
            f"Status: {phase}\n"
            f"Progress: {current} / {total} tracks ({pct}%)\n"
            f"✅ Successful: {successful}\n"
            f"❌ Failed: {failed}\n"
            f"⏭ Skipped: {skipped}\n"
        )
        if current_title:
            text += f"Current: {current_title[:80]}\n"

        now = time.time()
        if not force and (now - self._last_edit) < self.min_interval and text == self._last_text:
            return
        if text == self._last_text and not force:
            return

        self._last_text = text
        self._last_edit = now

        if self._message_id is None:
            await self.start(text)
            return

        try:
            await self.bot.edit_message_text(
                chat_id=self.chat_id,
                message_id=self._message_id,
                text=text,
                parse_mode="HTML",
            )
        except TelegramRetryAfter as e:
            logger.info("Progress edit rate-limited, sleeping %s", e.retry_after)
            await asyncio_sleep(e.retry_after)
        except TelegramAPIError as e:
            # Message not modified or other non-fatal
            if "message is not modified" not in str(e).lower():
                logger.debug("Progress edit failed: %s", e)

    async def finish(self, summary: str) -> None:
        await self.update_force_text(summary)

    async def update_force_text(self, text: str) -> None:
        self._last_text = text
        if self._message_id is None:
            await self.start(text)
            return
        try:
            await self.bot.edit_message_text(
                chat_id=self.chat_id,
                message_id=self._message_id,
                text=text,
                parse_mode="HTML",
            )
        except TelegramAPIError as e:
            logger.debug("Final progress edit failed: %s", e)
            try:
                await self.bot.send_message(self.chat_id, text, parse_mode="HTML")
            except Exception:
                pass


async def asyncio_sleep(seconds: float) -> None:
    import asyncio
    await asyncio.sleep(seconds)
