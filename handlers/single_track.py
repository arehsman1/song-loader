"""Single track download flow."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from keyboards import main_menu_keyboard, track_confirm_keyboard
from services.playlist_reader import playlist_reader
from states import SingleTrackStates
from utils.errors import SpotifyMetadataError
from utils.validation import is_valid_spotify_track_url

logger = logging.getLogger(__name__)
router = Router(name="single_track")

_track_cache: dict = {}


@router.message(F.text == "🎶 Download Single Song")
async def ask_track_url(message: Message, state: FSMContext) -> None:
    await state.set_state(SingleTrackStates.waiting_for_url)
    await message.answer(
        "Send a Spotify track URL.\n\n"
        "Example:\n<code>https://open.spotify.com/track/3n3Ppam7vgaVa1iaRUc9Lp</code>\n\n"
        "Note: Audio is only provided from authorized sources. "
        "Most commercial tracks will be unavailable.",
        parse_mode="HTML",
    )


@router.message(SingleTrackStates.waiting_for_url)
async def receive_track_url(message: Message, state: FSMContext) -> None:
    url = (message.text or "").strip()
    if not is_valid_spotify_track_url(url):
        await message.answer(
            "That does not look like a valid Spotify track URL.",
        )
        return

    await message.answer("Looking up track…")
    try:
        meta = playlist_reader.get_track(url)
    except SpotifyMetadataError as e:
        await message.answer(f"❌ {e.message}")
        await state.clear()
        return

    token = meta.spotify_id[:16]
    _track_cache[token] = meta
    await state.update_data(track_token=token)
    await state.set_state(SingleTrackStates.confirming)

    await message.answer(
        f"🎵 <b>{meta.name}</b>\n"
        f"Artist: {meta.artists}\n"
        f"{'Album: ' + meta.album_name if meta.album_name else ''}\n\n"
        "⚠️ This bot does not download protected Spotify audio. "
        "Only authorized sources can supply a file.\n\n"
        "Confirm to attempt acquisition:",
        reply_markup=track_confirm_keyboard(meta.spotify_id),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("tr:ok:"))
async def cb_confirm_track(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    token = callback.data.split(":")[-1]
    meta = _track_cache.get(token)
    if not meta:
        await callback.message.answer("Track data expired. Please send the URL again.")
        await state.clear()
        return

    # Build a minimal one-track playlist-like object
    from services.playlist_reader import PlaylistMeta, TrackMeta
    from services.download_manager import get_download_manager
    from database import get_db

    pl = PlaylistMeta(
        spotify_id=meta.spotify_id,
        name=meta.name,
        owner=None,
        description=None,
        total_tracks=1,
        tracks=[meta],
        external_url=None,
    )
    db = await get_db()
    settings = await db.get_user_settings(callback.from_user.id)

    try:
        mgr = get_download_manager(callback.bot)
        job_id = await mgr.start_playlist_job(
            user_id=callback.from_user.id,
            chat_id=callback.message.chat.id,
            playlist=pl,
            delivery_mode="individual",
            settings=settings,
        )
        await callback.message.answer(
            f"Job <code>{job_id[:8]}…</code> started for “{meta.name}”.",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )
    except Exception as e:
        await callback.message.answer(f"Could not start job: {e}")
    await state.clear()


@router.callback_query(F.data == "tr:cancel")
async def cb_cancel_track(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer("Cancelled")
    await state.clear()
    await callback.message.answer("Cancelled.", reply_markup=main_menu_keyboard())
