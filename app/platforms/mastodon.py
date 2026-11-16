"""Mastodon API - https://docs.joinmastodon.org/methods/statuses/#create"""
from __future__ import annotations

import uuid

from app.config import Settings
from app.platforms.base import BasePlatform, PlatformError, PublishOutcome, describe_http_error


class MastodonPlatform(BasePlatform):
    name = "Mastodon"

    def __init__(self, settings: Settings):
        self.s = settings

    def missing_credentials(self):
        return [] if self.s.mastodon_access_token else ["MASTODON_ACCESS_TOKEN"]

    async def publish(self, client, message):
        resp = await client.post(
            f"{self.s.mastodon_instance_url}/api/v1/statuses",
            headers={
                "Authorization": f"Bearer {self.s.mastodon_access_token}",
                "Idempotency-Key": str(uuid.uuid4()),
            },
            data={"status": message, "visibility": "public"},
        )
        if resp.status_code != 200:
            raise PlatformError(describe_http_error(self.name, resp))
        data = resp.json()
        if not data.get("url"):
            raise PlatformError("Mastodon returned no status URL")
        return PublishOutcome(data["url"], public_access=data.get("visibility") == "public")
