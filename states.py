"""FSM states for multi-step interactions."""

from aiogram.fsm.state import State, StatesGroup


class PlaylistStates(StatesGroup):
    waiting_for_url = State()
    confirming = State()


class SingleTrackStates(StatesGroup):
    waiting_for_url = State()
    confirming = State()


class SelectionStates(StatesGroup):
    browsing = State()
    confirming = State()


class SettingsStates(StatesGroup):
    choosing = State()
