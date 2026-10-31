"""Job history."""

from __future__ import annotations

from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from database import get_db
from keyboards import history_keyboard, job_actions_keyboard, main_menu_keyboard

router = Router(name="history")


def _fmt_ts(ts) -> str:
    if not ts:
        return "—"
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return str(ts)


@router.message(F.text == "📥 My Downloads / Job History")
async def show_history(message: Message) -> None:
    db = await get_db()
    jobs = await db.get_user_jobs(message.from_user.id, limit=15)
    if not jobs:
        await message.answer(
            "You have no job history yet.",
            reply_markup=main_menu_keyboard(),
        )
        return
    lines = ["📥 <b>Your recent jobs</b>\n"]
    for j in jobs[:10]:
        lines.append(
            f"• <code>{j['id'][:8]}…</code> [{j['status']}] "
            f"{(j.get('title') or 'Untitled')[:40]} "
            f"({j.get('successful', 0)}/{j.get('total_tracks', 0)})"
        )
    await message.answer(
        "\n".join(lines),
        reply_markup=history_keyboard(jobs),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "hist:list")
async def cb_hist_list(callback: CallbackQuery) -> None:
    await callback.answer()
    db = await get_db()
    jobs = await db.get_user_jobs(callback.from_user.id, limit=15)
    await callback.message.edit_text(
        "📥 Your jobs",
        reply_markup=history_keyboard(jobs),
    )


@router.callback_query(F.data.startswith("hist:v:"))
@router.callback_query(F.data.startswith("hist:d:"))
async def cb_job_detail(callback: CallbackQuery) -> None:
    await callback.answer()
    job_id = callback.data.split(":")[-1]
    db = await get_db()
    job = await db.get_job(job_id)
    if not job or job["owner_id"] != callback.from_user.id:
        await callback.message.answer("Job not found or access denied.")
        return
    tracks = await db.get_job_tracks(job_id)
    text = (
        f"📄 <b>Job {job_id[:8]}…</b>\n"
        f"Title: {job.get('title') or '—'}\n"
        f"Status: {job['status']}\n"
        f"Created: {_fmt_ts(job.get('created_at'))}\n"
        f"Tracks: {job.get('total_tracks', 0)}\n"
        f"✅ {job.get('successful', 0)}  ❌ {job.get('failed', 0)}  ⏭ {job.get('skipped', 0)}\n"
    )
    if job.get("error_summary"):
        text += f"\nNote: {job['error_summary'][:300]}\n"
    # Show a few track statuses
    for t in tracks[:8]:
        text += f"\n• {t.get('title', '?')[:40]} [{t['status']}]"
    if len(tracks) > 8:
        text += f"\n… and {len(tracks)-8} more"
    await callback.message.answer(
        text,
        reply_markup=job_actions_keyboard(job_id, job["status"]),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("hist:r:"))
async def cb_retry(callback: CallbackQuery) -> None:
    await callback.answer("Retry is limited: only failed tracks that later gain a source can be re-queued.")
    await callback.message.answer(
        "Retry of failed tracks is registered, but without an authorized audio provider "
        "the tracks will remain unavailable. No Spotify stream ripping is performed."
    )
