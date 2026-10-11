"""Help text."""

from aiogram import F, Router
from aiogram.types import Message

from keyboards import main_menu_keyboard

router = Router(name="help")


HELP_TEXT = """
❓ <b>Help – Spotify Public Playlist Bot</b>

<b>What this bot does</b>
• Accepts public Spotify playlist or track links.
• Shows playlist title, owner, and track list (metadata only).
• Lets you select tracks or request all.
• Attempts to obtain audio only from an <b>authorized</b> source.

<b>What this bot does NOT do</b>
• It does <b>not</b> rip or download protected Spotify streams.
• Playlist visibility does <b>not</b> grant download rights.
• It will not silently substitute a different recording.
• It will not claim a 320 kbps file if the source is lower quality.

<b>How to use</b>
1. Tap 🎵 Download Playlist and paste a public playlist URL.
2. Review the preview and choose Download All, Select Tracks, or ZIP.
3. For single tracks use 🎶 Download Single Song.
4. Progress updates appear while a job runs.
5. Use ❌ Cancel Job to stop an active job.
6. 📥 My Downloads shows history (survives restarts).

<b>File size limit</b>
Files larger than the configured safety limit (default 45 MiB) are not uploaded.
Oversized tracks are skipped and reported.

<b>ZIP mode</b>
Only successfully obtained, permitted files are archived.
Multiple ZIP parts are created if needed to stay under the size limit.

<b>Unavailable tracks</b>
If no authorized source exists, the track is marked skipped and the job continues.
This is the expected result for most commercial catalogue tracks.

<b>Settings</b>
You can set preferred bitrate and delivery mode. These apply only when an authorized source provides a file that can be converted.

Need more help? Open an issue on the project repository.
"""


@router.message(F.text == "❓ Help")
@router.message(F.text.casefold() == "help")
async def show_help(message: Message) -> None:
    await message.answer(HELP_TEXT, parse_mode="HTML", reply_markup=main_menu_keyboard())
