"""Database unit tests."""

import pytest

pytestmark = pytest.mark.asyncio


async def test_ensure_user_and_settings(db):
    uid = 12345
    await db.ensure_user(uid)
    settings = await db.get_user_settings(uid)
    assert "audio_bitrate" in settings
    settings["audio_bitrate"] = "192k"
    await db.set_user_settings(uid, settings)
    again = await db.get_user_settings(uid)
    assert again["audio_bitrate"] == "192k"


async def test_job_ownership(db):
    await db.create_job(
        job_id="job-a",
        owner_id=1,
        job_type="playlist",
        title="Test",
        source_url=None,
        total_tracks=2,
        delivery_mode="individual",
    )
    await db.create_job(
        job_id="job-b",
        owner_id=2,
        job_type="playlist",
        title="Other",
        source_url=None,
        total_tracks=1,
        delivery_mode="individual",
    )
    jobs1 = await db.get_user_jobs(1)
    jobs2 = await db.get_user_jobs(2)
    assert len(jobs1) == 1
    assert jobs1[0]["id"] == "job-a"
    assert len(jobs2) == 1
    assert jobs2[0]["id"] == "job-b"


async def test_selection(db):
    await db.set_selection(10, "pl123", [0, 2, 5])
    sel = await db.get_selection(10, "pl123")
    assert sel == [0, 2, 5]
    await db.clear_selection(10, "pl123")
    assert await db.get_selection(10, "pl123") == []
