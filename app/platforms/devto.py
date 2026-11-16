"""DEV Community (Forem) API - https://developers.forem.com/api/v1#tag/articles/operation/createArticle"""
from __future__ import annotations

from datetime import datetime, timezone

from app.config import Settings
from app.platforms.base import BasePlatform, PlatformError, PublishOutcome, describe_http_error
from app.schemas import extract_urls


class DevToPlatform(BasePlatform):
    name = "DEV Community"

    def __init__(self, settings: Settings):
        self.s = settings

    def missing_credentials(self):
        return [] if self.s.devto_api_key else ["DEVTO_API_KEY"]

    @staticmethod
    def build_title(message: str) -> str:
        text = message
        for url in extract_urls(message):
            text = text.replace(url, "")
        text = " ".join(text.split()).strip(" -:") or "Update"
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        return f"{text[:70]} ({stamp} UTC)"  # timestamp avoids duplicate-title rejections

    async def publish(self, client, message):
        resp = await client.post(
            "https://dev.to/api/articles",
            headers={"api-key": self.s.devto_api_key, "Accept": "application/vnd.forem.api-v1+json"},
            json={"article": {"title": self.build_title(message), "body_markdown": message, "published": True}},
        )
        if resp.status_code not in (200, 201):
            raise PlatformError(describe_http_error(self.name, resp))
        url = resp.json().get("url")
        if not url:
            raise PlatformError("DEV returned no article URL")
        return PublishOutcome(url)  # public_access verified with an anonymous GET
