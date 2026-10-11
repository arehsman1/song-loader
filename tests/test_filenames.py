"""Filename sanitization tests."""

from pathlib import Path

from utils.filenames import sanitize_filename, unique_path


def test_sanitize_basic():
    assert sanitize_filename("Hello World") == "Hello World"
    assert "/" not in sanitize_filename("a/b/c")
    assert ":" not in sanitize_filename("a:b")
    assert sanitize_filename("") == "unnamed"
    assert sanitize_filename("   ") == "unnamed"


def test_sanitize_length():
    long = "a" * 300
    result = sanitize_filename(long, max_length=50)
    assert len(result) <= 50


def test_unique_path(tmp_path):
    p1 = unique_path(tmp_path, "song.mp3")
    p1.write_text("x")
    p2 = unique_path(tmp_path, "song.mp3")
    assert p2.name == "song_1.mp3"
    assert p1 != p2
