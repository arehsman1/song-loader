"""Inline and reply keyboards."""

from __future__ import annotations

from typing import List, Optional, Sequence

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from services.playlist_reader import TrackMeta


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🎵 Download Playlist"),
                KeyboardButton(text="🎶 Download Single Song"),
            ],
            [
                KeyboardButton(text="📦 Download as ZIP"),
                KeyboardButton(text="🎼 Select Tracks"),
            ],
            [
                KeyboardButton(text="📥 My Downloads / Job History"),
                KeyboardButton(text="⚙️ Settings"),
            ],
            [
                KeyboardButton(text="❓ Help"),
                KeyboardButton(text="❌ Cancel Job"),
            ],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def remove_keyboard() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


def playlist_preview_keyboard(playlist_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬇️ Download All",
                    callback_data=f"pl:all:{playlist_id[:16]}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🎼 Select Tracks",
                    callback_data=f"pl:sel:{playlist_id[:16]}",
                ),
                InlineKeyboardButton(
                    text="📦 As ZIP",
                    callback_data=f"pl:zip:{playlist_id[:16]}",
                ),
            ],
            [
                InlineKeyboardButton(text="❌ Cancel", callback_data="pl:cancel"),
            ],
        ]
    )


def track_confirm_keyboard(track_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Confirm download",
                    callback_data=f"tr:ok:{track_id[:16]}",
                ),
                InlineKeyboardButton(text="❌ Cancel", callback_data="tr:cancel"),
            ]
        ]
    )


def selection_keyboard(
    tracks: Sequence[TrackMeta],
    selected: set[int],
    page: int,
    page_size: int = 8,
    playlist_token: str = "",
) -> InlineKeyboardMarkup:
    """Paginated track selection. Callback data is kept short."""
    total = len(tracks)
    start = page * page_size
    end = min(start + page_size, total)
    rows: List[List[InlineKeyboardButton]] = []

    for i in range(start, end):
        t = tracks[i]
        mark = "✅" if i in selected else "⬜"
        label = f"{mark} {i+1}. {t.name[:30]} – {t.artists[:20]}"
        rows.append([
            InlineKeyboardButton(
                text=label,
                callback_data=f"sel:t:{playlist_token}:{i}",
            )
        ])

    nav: List[InlineKeyboardButton] = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(
                text="⬅️ Prev",
                callback_data=f"sel:p:{playlist_token}:{page-1}",
            )
        )
    nav.append(
        InlineKeyboardButton(
            text=f"{page+1}/{(total-1)//page_size+1}",
            callback_data="sel:noop",
        )
    )
    if end < total:
        nav.append(
            InlineKeyboardButton(
                text="Next ➡️",
                callback_data=f"sel:p:{playlist_token}:{page+1}",
            )
        )
    if nav:
        rows.append(nav)

    rows.append([
        InlineKeyboardButton(
            text="Select All (page)",
            callback_data=f"sel:allp:{playlist_token}:{page}",
        ),
        InlineKeyboardButton(
            text="Clear",
            callback_data=f"sel:clear:{playlist_token}",
        ),
    ])
    rows.append([
        InlineKeyboardButton(
            text=f"✅ Confirm ({len(selected)} selected)",
            callback_data=f"sel:ok:{playlist_token}",
        ),
        InlineKeyboardButton(text="❌ Cancel", callback_data="sel:cancel"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def history_keyboard(jobs: List[dict]) -> InlineKeyboardMarkup:
    rows = []
    for j in jobs[:10]:
        short = j["id"][:8]
        status = j.get("status", "?")
        title = (j.get("title") or "Untitled")[:25]
        rows.append([
            InlineKeyboardButton(
                text=f"{short}… {status} – {title}",
                callback_data=f"hist:v:{j['id']}",
            )
        ])
    if not rows:
        rows.append([InlineKeyboardButton(text="No jobs yet", callback_data="hist:noop")])
    rows.append([InlineKeyboardButton(text="« Back", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def job_actions_keyboard(job_id: str, status: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="📄 Details",
                callback_data=f"hist:d:{job_id}",
            )
        ]
    ]
    if status in ("failed", "partial"):
        rows.append([
            InlineKeyboardButton(
                text="🔁 Retry failed",
                callback_data=f"hist:r:{job_id}",
            )
        ])
    if status in ("pending", "running"):
        rows.append([
            InlineKeyboardButton(
                text="⏹ Cancel",
                callback_data=f"cancel:j:{job_id}",
            )
        ])
    rows.append([InlineKeyboardButton(text="« Back", callback_data="hist:list")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cancel_jobs_keyboard(jobs: List[dict]) -> InlineKeyboardMarkup:
    rows = []
    for j in jobs:
        short = j["id"][:8]
        title = (j.get("title") or "Job")[:30]
        rows.append([
            InlineKeyboardButton(
                text=f"⏹ {short}… – {title}",
                callback_data=f"cancel:j:{j['id']}",
            )
        ])
    if not rows:
        rows.append([InlineKeyboardButton(text="No active jobs", callback_data="cancel:noop")])
    rows.append([InlineKeyboardButton(text="« Back", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_keyboard(settings: dict) -> InlineKeyboardMarkup:
    br = settings.get("audio_bitrate", "320k")
    mode = settings.get("delivery_mode", "individual")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"Bitrate: {br}",
                    callback_data="set:bitrate",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"Delivery: {mode}",
                    callback_data="set:delivery",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Reset to defaults",
                    callback_data="set:reset",
                )
            ],
            [InlineKeyboardButton(text="« Back", callback_data="menu:main")],
        ]
    )


def bitrate_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="320 kbps", callback_data="set:br:320k"),
                InlineKeyboardButton(text="192 kbps", callback_data="set:br:192k"),
            ],
            [InlineKeyboardButton(text="« Back", callback_data="set:menu")],
        ]
    )


def delivery_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Individual files", callback_data="set:dm:individual"),
                InlineKeyboardButton(text="ZIP archive", callback_data="set:dm:zip"),
            ],
            [InlineKeyboardButton(text="« Back", callback_data="set:menu")],
        ]
    )
