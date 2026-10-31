"""Register all routers."""

from aiogram import Router

from . import (
    start,
    playlist,
    single_track,
    track_selection,
    downloads,
    settings,
    history,
    help as help_handler,
    cancellation,
)


def setup_routers() -> Router:
    root = Router()
    root.include_router(start.router)
    root.include_router(playlist.router)
    root.include_router(single_track.router)
    root.include_router(track_selection.router)
    root.include_router(downloads.router)
    root.include_router(settings.router)
    root.include_router(history.router)
    root.include_router(help_handler.router)
    root.include_router(cancellation.router)
    return root
