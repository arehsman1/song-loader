"""URL validation tests."""

import pytest

from utils.validation import (
    SpotifyResourceType,
    extract_spotify_id,
    is_valid_spotify_playlist_url,
    is_valid_spotify_track_url,
)


def test_valid_playlist_urls():
    urls = [
        "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M",
        "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=abc",
        "https://open.spotify.com/intl-de/playlist/37i9dQZF1DXcBWIGoYBM5M",
        "spotify:playlist:37i9dQZF1DXcBWIGoYBM5M",
    ]
    for u in urls:
        assert is_valid_spotify_playlist_url(u), u
        rtype, rid = extract_spotify_id(u)
        assert rtype == SpotifyResourceType.PLAYLIST
        assert rid == "37i9dQZF1DXcBWIGoYBM5M"


def test_invalid_playlist_urls():
    bad = [
        "",
        "https://example.com/playlist/foo",
        "https://open.spotify.com/album/abc",
        "not a url",
        "https://open.spotify.com/track/3n3Ppam7vgaVa1iaRUc9Lp",
    ]
    for u in bad:
        assert not is_valid_spotify_playlist_url(u), u


def test_valid_track_urls():
    urls = [
        "https://open.spotify.com/track/3n3Ppam7vgaVa1iaRUc9Lp",
        "spotify:track:3n3Ppam7vgaVa1iaRUc9Lp",
    ]
    for u in urls:
        assert is_valid_spotify_track_url(u)
        rtype, rid = extract_spotify_id(u)
        assert rtype == SpotifyResourceType.TRACK
        assert len(rid) == 22
