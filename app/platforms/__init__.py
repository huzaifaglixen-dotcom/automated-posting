from typing import List

from app.config import get_settings
from app.platforms.base import BasePlatform
from app.platforms.bluesky import BlueskyPlatform
from app.platforms.devto import DevToPlatform
from app.platforms.discord import DiscordPlatform
from app.platforms.mastodon import MastodonPlatform
from app.platforms.telegram import TelegramPlatform


def get_platforms() -> List[BasePlatform]:
    """Platform selection is handled internally - callers never choose."""
    s = get_settings()
    return [
        TelegramPlatform(s),
        DiscordPlatform(s),
        MastodonPlatform(s),
        BlueskyPlatform(s),
        DevToPlatform(s),
    ]
