"""Bluesky / AT Protocol - https://docs.bsky.app/docs/api/com-atproto-repo-create-record"""
from __future__ import annotations

from datetime import datetime, timezone

from app.config import Settings
from app.platforms.base import BasePlatform, PlatformError, PublishOutcome, describe_http_error
from app.schemas import extract_urls

BSKY_HOST = "https://bsky.social"


class BlueskyPlatform(BasePlatform):
    name = "Bluesky"

    def __init__(self, settings: Settings):
        self.s = settings

    def missing_credentials(self):
        return [n for n, v in (("BLUESKY_HANDLE", self.s.bluesky_handle),
                               ("BLUESKY_APP_PASSWORD", self.s.bluesky_app_password)) if not v]

    @staticmethod
    def build_facets(message: str):
        """Make the link clickable. Facet offsets are UTF-8 *byte* positions."""
        facets = []
        for url in extract_urls(message):
            start = message.find(url)
            if start < 0:
                continue
            byte_start = len(message[:start].encode("utf-8"))
            byte_end = byte_start + len(url.encode("utf-8"))
            facets.append({
                "index": {"byteStart": byte_start, "byteEnd": byte_end},
                "features": [{"$type": "app.bsky.richtext.facet#link", "uri": url}],
            })
        return facets

    async def publish(self, client, message):
        session = await client.post(
            f"{BSKY_HOST}/xrpc/com.atproto.server.createSession",
            json={"identifier": self.s.bluesky_handle, "password": self.s.bluesky_app_password},
        )
        if session.status_code != 200:
            raise PlatformError(describe_http_error(self.name, session))
        sdata = session.json()

        record = {
            "$type": "app.bsky.feed.post",
            "text": message,
            "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "facets": self.build_facets(message),
        }
        resp = await client.post(
            f"{BSKY_HOST}/xrpc/com.atproto.repo.createRecord",
            headers={"Authorization": f"Bearer {sdata['accessJwt']}"},
            json={"repo": sdata["did"], "collection": "app.bsky.feed.post", "record": record},
        )
        if resp.status_code != 200:
            raise PlatformError(describe_http_error(self.name, resp))
        uri = resp.json().get("uri", "")  # at://did:plc:xxx/app.bsky.feed.post/<rkey>
        rkey = uri.rsplit("/", 1)[-1]
        if not rkey:
            raise PlatformError("Bluesky returned no post id")
        handle = sdata.get("handle") or self.s.bluesky_handle
        return PublishOutcome(f"https://bsky.app/profile/{handle}/post/{rkey}")
