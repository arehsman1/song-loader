"""Cancellation flag tests."""

from services.download_manager import request_cancel, is_cancelled, _cancelled_jobs


def test_cancel_flag():
    _cancelled_jobs.clear()
    jid = "test-job-123"
    assert not is_cancelled(jid)
    request_cancel(jid)
    assert is_cancelled(jid)
    _cancelled_jobs.discard(jid)
    assert not is_cancelled(jid)
