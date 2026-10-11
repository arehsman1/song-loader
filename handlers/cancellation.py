"""Job cancellation."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from database import get_db
from keyboards import cancel_jobs_keyboard, main_menu_keyboard
from services.download_manager import request_cancel

router = Router(name="cancellation")


@router.message(F.text == "❌ Cancel Job")
async def list_active(message: Message) -> None:
    db = await get_db()
    jobs = await db.get_active_jobs(message.from_user.id)
    if not jobs:
        await message.answer(
            "You have no active jobs to cancel.",
            reply_markup=main_menu_keyboard(),
        )
        return
    await message.answer(
        "Select a job to cancel:",
        reply_markup=cancel_jobs_keyboard(jobs),
    )


@router.callback_query(F.data.startswith("cancel:j:"))
async def cb_cancel_job(callback: CallbackQuery) -> None:
    await callback.answer()
    job_id = callback.data.split(":")[-1]
    db = await get_db()
    job = await db.get_job(job_id)
    if not job:
        await callback.message.answer("Job not found.")
        return
    if job["owner_id"] != callback.from_user.id:
        await callback.message.answer("You can only cancel your own jobs.")
        return
    if job["status"] not in ("pending", "running"):
        await callback.message.answer(f"Job is already {job['status']}.")
        return

    request_cancel(job_id)
    await db.update_job_status(job_id, "cancelled", completed=True)
    await callback.message.answer(
        f"Cancellation requested for job <code>{job_id[:8]}…</code>.\n"
        "In-progress work will stop; completed files already sent are kept.",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


@router.callback_query(F.data == "cancel:noop")
async def cb_noop(callback: CallbackQuery) -> None:
    await callback.answer()
