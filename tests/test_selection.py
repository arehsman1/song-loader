"""Selection keyboard / pagination helpers (logic level)."""

from services.playlist_reader import TrackMeta
from keyboards import selection_keyboard


def test_selection_keyboard_builds():
    tracks = [
        TrackMeta(spotify_id=f"id{i}", name=f"Song {i}", artists="Artist")
        for i in range(20)
    ]
    selected = {0, 3, 7}
    kb = selection_keyboard(tracks, selected, page=0, page_size=8, playlist_token="abc")
    assert kb.inline_keyboard
    # First page has 8 track buttons + nav + actions
    assert len(kb.inline_keyboard) >= 8
