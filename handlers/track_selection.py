"""Paginated track selection."""

from __future__ import annotations

import logging
from typing import Set

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from database import get_db
from keyboards import main_menu_keyboard, selection_keyboard
from services.playlist_reader import PlaylistMeta
from states import SelectionStates

logger = logging.getLogger(__name__)
router = Router(name="track_selection")

# token -> PlaylistMeta (shared with playlist handler cache where possible)
_selection_playlists: dict = {}


async def begin_selection(
    callback: CallbackQuery,
    state: FSMContext,
    meta: PlaylistMeta,
    token: str,
) -> None:
    _selection_playlists[token] = meta
    db = await get_db()
    selected = set(await db.get_selection(callback.from_user.id, meta.spotify_id))
    await state.set_state(SelectionStates.browsing)
    await state.update_data(
        playlist_token=token,
        playlist_id=meta.spotify_id,
        page=0,
    )
    kb = selection_keyboard(meta.tracks, selected, page=0, playlist_token=token)
    await callback.message.answer(
        f"Select tracks from <b>{meta.name}</b>\n"
        f"({len(selected)} currently selected)\n"
        "Tap a track to toggle. Use Confirm when ready.",
        reply_markup=kb,
        parse_mode="HTML",
    )


@router.message(F.text == "🎼 Select Tracks")
async def menu_select_tracks(message, state: FSMContext) -> None:
    await message.answer(
        "First send a public Spotify playlist URL (use 🎵 Download Playlist), "
        "then choose “Select Tracks” on the preview, or paste a playlist URL now."
    )
    await state.set_state(SelectionStates.browsing)
    # User can still paste URL; for simplicity we reuse playlist flow
    from handlers.playlist import ask_playlist_url
    await ask_playlist_url(message, state)


@router.callback_query(F.data.startswith("sel:t:"))
async def cb_toggle_track(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    parts = callback.data.split(":")
    # sel:t:token:index
    if len(parts) < 4:
        return
    token, idx_s = parts[2], parts[3]
    try:
        idx = int(idx_s)
    except ValueError:
        return
    meta = _selection_playlists.get(token)
    if not meta:
        await callback.message.answer("Session expired. Please start again.")
        return

    db = await get_db()
    selected: Set[int] = set(await db.get_selection(callback.from_user.id, meta.spotify_id))
    if idx in selected:
        selected.discard(idx)
    else:
        selected.add(idx)
    await db.set_selection(callback.from_user.id, meta.spotify_id, list(selected))

    data = await state.get_data()
    page = int(data.get("page", 0))
    kb = selection_keyboard(meta.tracks, selected, page=page, playlist_token=token)
    try:
        await callback.message.edit_reply_markup(reply_markup=kb)
    except Exception:
        pass


@router.callback_query(F.data.startswith("sel:p:"))
async def cb_page(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    parts = callback.data.split(":")
    if len(parts) < 4:
        return
    token, page_s = parts[2], parts[3]
    try:
        page = int(page_s)
    except ValueError:
        return
    meta = _selection_playlists.get(token)
    if not meta:
        return
    await state.update_data(page=page)
    db = await get_db()
    selected = set(await db.get_selection(callback.from_user.id, meta.spotify_id))
    kb = selection_keyboard(meta.tracks, selected, page=page, playlist_token=token)
    try:
        await callback.message.edit_reply_markup(reply_markup=kb)
    except Exception:
        pass


@router.callback_query(F.data.startswith("sel:allp:"))
async def cb_select_page(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    parts = callback.data.split(":")
    if len(parts) < 4:
        return
    token, page_s = parts[2], parts[3]
    try:
        page = int(page_s)
    except ValueError:
        return
    meta = _selection_playlists.get(token)
    if not meta:
        return
    page_size = 8
    start = page * page_size
    end = min(start + page_size, len(meta.tracks))
    db = await get_db()
    selected = set(await db.get_selection(callback.from_user.id, meta.spotify_id))
    for i in range(start, end):
        selected.add(i)
    await db.set_selection(callback.from_user.id, meta.spotify_id, list(selected))
    kb = selection_keyboard(meta.tracks, selected, page=page, playlist_token=token)
    try:
        await callback.message.edit_reply_markup(reply_markup=kb)
    except Exception:
        pass


@router.callback_query(F.data.startswith("sel:clear:"))
async def cb_clear(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer("Cleared")
    token = callback.data.split(":")[-1]
    meta = _selection_playlists.get(token)
    if not meta:
        return
    db = await get_db()
    await db.clear_selection(callback.from_user.id, meta.spotify_id)
    data = await state.get_data()
    page = int(data.get("page", 0))
    kb = selection_keyboard(meta.tracks, set(), page=page, playlist_token=token)
    try:
        await callback.message.edit_reply_markup(reply_markup=kb)
    except Exception:
        pass


@router.callback_query(F.data.startswith("sel:ok:"))
async def cb_confirm_selection(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    token = callback.data.split(":")[-1]
    meta = _selection_playlists.get(token)
    if not meta:
        await callback.message.answer("Session expired.")
        await state.clear()
        return
    db = await get_db()
    selected = await db.get_selection(callback.from_user.id, meta.spotify_id)
    if not selected:
        await callback.message.answer("No tracks selected.")
        return

    from services.download_manager import get_download_manager
    settings = await db.get_user_settings(callback.from_user.id)
    data = await state.get_data()
    delivery = data.get("delivery_mode", settings.get("delivery_mode", "individual"))

    try:
        mgr = get_download_manager(callback.bot)
        job_id = await mgr.start_playlist_job(
            user_id=callback.from_user.id,
            chat_id=callback.message.chat.id,
            playlist=meta,
            selected_indices=sorted(selected),
            delivery_mode=delivery,
            settings=settings,
        )
        await callback.message.answer(
            f"Job <code>{job_id[:8]}…</code> started with {len(selected)} track(s).",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )
    except Exception as e:
        await callback.message.answer(f"Could not start job: {e}")
    await state.clear()


@router.callback_query(F.data == "sel:cancel")
async def cb_cancel_selection(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer("Cancelled")
    await state.clear()
    await callback.message.answer("Selection cancelled.", reply_markup=main_menu_keyboard())


@router.callback_query(F.data == "sel:noop")
async def cb_noop(callback: CallbackQuery) -> None:
    await callback.answer()
