""" /start and main menu entry points. """

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from keyboards import main_menu_keyboard

router = Router(name="start")


@router.message(CommandStart())
@router.message(Command("menu"))
async def cmd_start(message: Message) -> None:
    await message.answer(
        "👋 <b>Spotify Public Playlist Bot</b>\n\n"
        "Send a <b>public</b> Spotify playlist link or use the menu below.\n\n"
        "⚠️ <i>Important:</i> Reading playlist metadata does <b>not</b> give permission "
        "to download copyrighted audio. This bot only delivers files from "
        "explicitly authorized audio sources. Protected Spotify streams are never ripped.",
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )


@router.message(F.text == "🎵 Download Playlist")
async def menu_download_playlist(message: Message) -> None:
    from states import PlaylistStates
    from aiogram.fsm.context import FSMContext

    # Handled more completely in playlist.py; this is a quick entry
    await message.answer(
        "Please send a public Spotify playlist URL.\n"
        "Example: https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M",
    )
    # State is set in the dedicated handler when the text is received
