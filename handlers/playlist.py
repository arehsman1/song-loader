"""Playlist URL handling and preview."""

from __future__ import annotations

import logging
from typing import Dict

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from keyboards import main_menu_keyboard, playlist_preview_keyboard
from services.playlist_reader import playlist_reader
from states import PlaylistStates
from utils.errors import SpotifyMetadataError
from utils.validation import is_valid_spotify_playlist_url

logger = logging.getLogger(__name__)
router = Router(name="playlist")

# In-memory cache of recently fetched playlists keyed by short token -> full meta
# (keeps callback_data short)
_playlist_cache: Dict[str, object] = {}


def _token(playlist_id: str) -> str:
    return playlist_id[:16]


@router.message(F.text == "🎵 Download Playlist")
@router.message(F.text == "📦 Download as ZIP")
async def ask_playlist_url(message: Message, state: FSMContext) -> None:
    mode = "zip" if message.text and "ZIP" in message.text else "individual"
    await state.set_state(PlaylistStates.waiting_for_url)
    await state.update_data(delivery_mode=mode)
    await message.answer(
        "Send a <b>public</b> Spotify playlist URL.\n\n"
        "Example:\n<code>https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M</code>\n\n"
        "Only public playlists can be read. Private playlists and DRM-protected streams "
        "are not supported.",
        parse_mode="HTML",
    )


@router.message(PlaylistStates.waiting_for_url)
async def receive_playlist_url(message: Message, state: FSMContext) -> None:
    url = (message.text or "").strip()
    if not is_valid_spotify_playlist_url(url):
        await message.answer(
            "That does not look like a valid Spotify playlist URL.\n"
            "Please send a link that contains <code>open.spotify.com/playlist/…</code>.",
            parse_mode="HTML",
        )
        return

    await message.answer("Fetching playlist metadata…")
    try:
        meta = playlist_reader.get_playlist(url)
    except SpotifyMetadataError as e:
        await message.answer(f"❌ {e.message}")
        await state.clear()
        return
    except Exception as e:
        logger.exception("Unexpected metadata error")
        await message.answer(f"❌ Could not read playlist: {e}")
        await state.clear()
        return

    token = _token(meta.spotify_id)
    _playlist_cache[token] = meta
    data = await state.get_data()
    delivery = data.get("delivery_mode", "individual")
    await state.update_data(
        playlist_token=token,
        delivery_mode=delivery,
        playlist_id=meta.spotify_id,
    )
    await state.set_state(PlaylistStates.confirming)

    owner = f" by {meta.owner}" if meta.owner else ""
    preview = (
        f"📋 <b>{meta.name}</b>{owner}\n"
        f"Tracks: {meta.total_tracks}\n"
    )
    if meta.description:
        preview += f"\n{meta.description[:200]}\n"
    preview += (
        "\n⚠️ Audio is delivered <b>only</b> from authorized sources. "
        "Most commercial tracks will be marked unavailable because this bot "
        "does not rip Spotify streams.\n\n"
        "Choose an action:"
    )
    await message.answer(
        preview,
        reply_markup=playlist_preview_keyboard(meta.spotify_id),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("pl:all:"))
async def cb_download_all(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    token = callback.data.split(":")[-1]
    meta = _playlist_cache.get(token)
    if not meta:
        await callback.message.answer("Playlist data expired. Please send the URL again.")
        await state.clear()
        return

    from services.download_manager import get_download_manager
    from database import get_db

    data = await state.get_data()
    delivery = data.get("delivery_mode", "individual")
    db = await get_db()
    settings = await db.get_user_settings(callback.from_user.id)

    try:
        mgr = get_download_manager(callback.bot)
        job_id = await mgr.start_playlist_job(
            user_id=callback.from_user.id,
            chat_id=callback.message.chat.id,
            playlist=meta,
            delivery_mode=delivery if delivery == "zip" else settings.get("delivery_mode", "individual"),
            settings=settings,
        )
        await callback.message.answer(
            f"Job <code>{job_id[:8]}…</code> started.\n"
            "You will receive progress updates. Use ❌ Cancel Job to stop it.",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )
    except Exception as e:
        await callback.message.answer(f"Could not start job: {e}")
    await state.clear()


@router.callback_query(F.data.startswith("pl:zip:"))
async def cb_download_zip(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(delivery_mode="zip")
    # Re-use the all handler logic by changing mode
    await cb_download_all(callback, state)


@router.callback_query(F.data.startswith("pl:sel:"))
async def cb_select_tracks(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    token = callback.data.split(":")[-1]
    meta = _playlist_cache.get(token)
    if not meta:
        await callback.message.answer("Playlist data expired. Please send the URL again.")
        await state.clear()
        return
    # Hand off to selection handler
    from handlers.track_selection import begin_selection
    await begin_selection(callback, state, meta, token)


@router.callback_query(F.data == "pl:cancel")
async def cb_cancel_preview(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer("Cancelled")
    await state.clear()
    await callback.message.answer("Cancelled.", reply_markup=main_menu_keyboard())
