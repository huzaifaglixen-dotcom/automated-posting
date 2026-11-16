"""Telegram Bot API - https://core.telegram.org/bots/api#sendmessage"""
from __future__ import annotations

from app.config import Settings
from app.platforms.base import BasePlatform, PlatformError, PublishOutcome, describe_http_error


class TelegramPlatform(BasePlatform):
    name = "Telegram"

    def __init__(self, settings: Settings):
        self.s = settings

    def missing_credentials(self):
        return [n for n, v in (("TELEGRAM_BOT_TOKEN", self.s.telegram_bot_token),
                               ("TELEGRAM_CHAT_ID", self.s.telegram_chat_id)) if not v]

    async def publish(self, client, message):
        url = f"https://api.telegram.org/bot{self.s.telegram_bot_token}/sendMessage"
        resp = await client.post(url, json={"chat_id": self.s.telegram_chat_id, "text": message})
        if resp.status_code != 200:
            raise PlatformError(describe_http_error(self.name, resp))
        result = resp.json().get("result", {})
        message_id = result.get("message_id")
        username = (result.get("chat") or {}).get("username")
        if not message_id:
            raise PlatformError("Telegram returned no message id")
        if username:  # public channel/group -> permanent public link
            return PublishOutcome(f"https://t.me/{username}/{message_id}", public_access=True)
        chat_id = str(result.get("chat", {}).get("id", "")).replace("-100", "", 1)
        return PublishOutcome(f"https://t.me/c/{chat_id}/{message_id}", public_access=False)
