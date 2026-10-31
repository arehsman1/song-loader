"""Unit tests for dual-format Spotify playlist response parsing."""

from services.playlist_reader import PlaylistReader


def test_get_paging_object_old_style():
    pl = {"tracks": {"items": [], "total": 5, "next": None}}
    paging, style = PlaylistReader._get_paging_object(pl)
    assert style == "tracks"
    assert paging["total"] == 5


def test_get_paging_object_new_style():
    pl = {"items": {"items": [], "total": 3, "next": None}}
    paging, style = PlaylistReader._get_paging_object(pl)
    assert style == "items"
    assert paging["total"] == 3


def test_extract_track_old_style():
    item = {"track": {"id": "abc", "name": "Song", "artists": [{"name": "A"}]}}
    obj = PlaylistReader._extract_track_from_item(item, "tracks")
    assert obj["name"] == "Song"


def test_extract_track_new_style():
    item = {"item": {"id": "xyz", "name": "NewSong", "artists": [{"name": "B"}]}}
    obj = PlaylistReader._extract_track_from_item(item, "items")
    assert obj["name"] == "NewSong"


def test_parse_track_object():
    reader = PlaylistReader.__new__(PlaylistReader)
    track = {
        "id": "tid123456789012345678",
        "name": "Test Track",
        "artists": [{"name": "Artist One"}, {"name": "Artist Two"}],
        "duration_ms": 200000,
        "is_playable": True,
        "explicit": False,
        "album": {"name": "Album X"},
        "preview_url": None,
    }
    meta = reader._parse_track_object(track, 0)
    assert meta.name == "Test Track"
    assert meta.artists == "Artist One, Artist Two"
    assert meta.spotify_id == "tid123456789012345678"
