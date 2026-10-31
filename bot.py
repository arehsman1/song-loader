"""
Main entry point for the Spotify Public Playlist Telegram bot.
Default mode: long polling (no public HTTPS required).
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import config
from database import get_db
from handlers import setup_routers
from services.storage import storage

# Logging setup
LOG_DIR = config.logs_dir
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=getattr(logging, config.log_level, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / "bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("bot")


async def on_startup(bot: Bot) -> None:
    db = await get_db()
    logger.info("Database ready at %s", config.database_path)
    storage.cleanup_stale()
    me = await bot.get_me()
    logger.info("Bot started as @%s (id=%s)", me.username, me.id)
    ok, msg = config.validate_ffmpeg()
    if ok:
        logger.info(msg)
    else:
        logger.warning(msg)


async def on_shutdown(bot: Bot) -> None:
    logger.info("Shutting down…")
    db = await get_db()
    await db.close()
    await bot.session.close()


async def main() -> None:
    bot = Bot(
        token=config.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(setup_routers())
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # Graceful shutdown on SIGINT/SIGTERM
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _signal_handler() -> None:
        logger.info("Received stop signal")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            # Windows
            signal.signal(sig, lambda s, f: _signal_handler())

    logger.info("Starting long polling…")
    try:
        await dp.start_polling(bot, handle_signals=False)
    finally:
        await on_shutdown(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
