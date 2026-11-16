"""Discord webhooks - https://discord.com/developers/docs/resources/webhook#execute-webhook"""
from __future__ import annotations

from app.config import Settings
from app.platforms.base import BasePlatform, PlatformError, PublishOutcome, describe_http_error


class DiscordPlatform(BasePlatform):
    name = "Discord"

    def __init__(self, settings: Settings):
        self.s = settings

    def missing_credentials(self):
        return [] if self.s.discord_webhook_url else ["DISCORD_WEBHOOK_URL"]

    async def publish(self, client, message):
        # wait=true makes Discord return the created message object
        resp = await client.post(
            self.s.discord_webhook_url, params={"wait": "true"}, json={"content": message}
        )
        if resp.status_code not in (200, 204):
            raise PlatformError(describe_http_error(self.name, resp))
        data = resp.json() if resp.content else {}
        if not data.get("id"):
            raise PlatformError("Discord returned no message id")
        guild = data.get("guild_id") or self.s.discord_guild_id or "@me"
        url = f"https://discord.com/channels/{guild}/{data['channel_id']}/{data['id']}"
        # Discord message links require login/membership, so they are never anonymously public.
        return PublishOutcome(url, public_access=False)
