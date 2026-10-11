"""Application-specific exceptions."""

from __future__ import annotations


class BotError(Exception):
    """Base class for user-facing bot errors. Message is safe to show to the user."""

    def __init__(self, message: str, *, technical: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.technical = technical or message


class ConfigError(BotError):
    """Configuration or environment problem."""


class SpotifyMetadataError(BotError):
    """Failed to retrieve or parse Spotify playlist/track metadata."""


class AudioSourceUnavailable(BotError):
    """No authorized audio source can provide this track."""


class FileTooLargeError(BotError):
    """File exceeds the configured Telegram safety limit."""


class JobCancelledError(BotError):
    """Job was cancelled by the user or system."""


class UnauthorizedActionError(BotError):
    """User tried to act on a job or selection that does not belong to them."""


class RateLimitError(BotError):
    """External service or Telegram rate limit hit."""


class ConversionError(BotError):
    """FFmpeg or format conversion failed."""
