"""User settings."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from database import get_db
from keyboards import (
    bitrate_keyboard,
    delivery_keyboard,
    main_menu_keyboard,
    settings_keyboard,
)

router = Router(name="settings")


@router.message(F.text == "⚙️ Settings")
async def show_settings(message: Message) -> None:
    db = await get_db()
    settings = await db.get_user_settings(message.from_user.id)
    text = (
        "⚙️ <b>Your settings</b>\n\n"
        f"• Audio bitrate target: <code>{settings.get('audio_bitrate', '320k')}</code>\n"
        f"• Delivery mode: <code>{settings.get('delivery_mode', 'individual')}</code>\n"
        f"• Max tracks per job: <code>{settings.get('max_tracks_per_job', 100)}</code>\n\n"
        "Note: Requesting 320 kbps does not improve a lower-quality source. "
        "Conversion is only performed when an authorized source provides a file "
        "and conversion is permitted."
    )
    await message.answer(text, reply_markup=settings_keyboard(settings), parse_mode="HTML")


@router.callback_query(F.data == "set:menu")
async def cb_settings_menu(callback: CallbackQuery) -> None:
    await callback.answer()
    db = await get_db()
    settings = await db.get_user_settings(callback.from_user.id)
    await callback.message.edit_text(
        "⚙️ Settings",
        reply_markup=settings_keyboard(settings),
    )


@router.callback_query(F.data == "set:bitrate")
async def cb_bitrate(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.edit_text(
        "Choose preferred bitrate (applied only when conversion is possible):",
        reply_markup=bitrate_keyboard(),
    )


@router.callback_query(F.data.startswith("set:br:"))
async def cb_set_bitrate(callback: CallbackQuery) -> None:
    await callback.answer()
    br = callback.data.split(":")[-1]
    db = await get_db()
    settings = await db.get_user_settings(callback.from_user.id)
    settings["audio_bitrate"] = br
    await db.set_user_settings(callback.from_user.id, settings)
    await callback.message.edit_text(
        f"Bitrate set to {br}.",
        reply_markup=settings_keyboard(settings),
    )


@router.callback_query(F.data == "set:delivery")
async def cb_delivery(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.edit_text(
        "Choose default delivery mode:",
        reply_markup=delivery_keyboard(),
    )


@router.callback_query(F.data.startswith("set:dm:"))
async def cb_set_delivery(callback: CallbackQuery) -> None:
    await callback.answer()
    mode = callback.data.split(":")[-1]
    db = await get_db()
    settings = await db.get_user_settings(callback.from_user.id)
    settings["delivery_mode"] = mode
    await db.set_user_settings(callback.from_user.id, settings)
    await callback.message.edit_text(
        f"Delivery mode set to {mode}.",
        reply_markup=settings_keyboard(settings),
    )


@router.callback_query(F.data == "set:reset")
async def cb_reset(callback: CallbackQuery) -> None:
    await callback.answer("Reset")
    db = await get_db()
    defaults = {
        "audio_bitrate": "320k",
        "delivery_mode": "individual",
        "zip_enabled": False,
        "max_tracks_per_job": 100,
    }
    await db.set_user_settings(callback.from_user.id, defaults)
    await callback.message.edit_text(
        "Settings reset to defaults.",
        reply_markup=settings_keyboard(defaults),
    )


@router.callback_query(F.data == "menu:main")
async def cb_back_main(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer("Main menu", reply_markup=main_menu_keyboard())
