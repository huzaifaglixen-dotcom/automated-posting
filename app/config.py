"""Configuration loaded from environment variables (and an optional .env file)."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    telegram_chat_id: str
    discord_webhook_url: str
    discord_guild_id: str
    mastodon_instance_url: str
    mastodon_access_token: str
    bluesky_handle: str
    bluesky_app_password: str
    devto_api_key: str
    request_timeout: float


def get_settings() -> Settings:
    """Read settings fresh each call so tests / env changes are respected."""
    try:
        timeout = float(_env("REQUEST_TIMEOUT_SECONDS", "15"))
    except ValueError:
        timeout = 15.0
    return Settings(
        telegram_bot_token=_env("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=_env("TELEGRAM_CHAT_ID"),
        discord_webhook_url=_env("DISCORD_WEBHOOK_URL"),
        discord_guild_id=_env("DISCORD_GUILD_ID"),
        mastodon_instance_url=_env("MASTODON_INSTANCE_URL", "https://mastodon.social").rstrip("/"),
        mastodon_access_token=_env("MASTODON_ACCESS_TOKEN"),
        bluesky_handle=_env("BLUESKY_HANDLE"),
        bluesky_app_password=_env("BLUESKY_APP_PASSWORD"),
        devto_api_key=_env("DEVTO_API_KEY"),
        request_timeout=timeout,
    )
