"""Tests: validation, failure isolation, and platform integrations (HTTP mocked)."""
import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app
from app.platforms import get_platforms
from app.platforms.base import BasePlatform, PlatformError, PublishOutcome
from app.platforms.bluesky import BlueskyPlatform
from app.platforms.mastodon import MastodonPlatform
from app.platforms.telegram import TelegramPlatform
from app.schemas import extract_urls, validate_url
from app.services.posting_service import publish_everywhere

VALID = "Check out our latest business platform and grow your online visibility. https://example.com"


# ---------- helpers ----------
class OkPlatform(BasePlatform):
    name = "OkPlatform"

    def missing_credentials(self):
        return []

    async def publish(self, client, message):
        return PublishOutcome("https://ok.example/post/1", public_access=True)


class BrokenPlatform(OkPlatform):
    name = "BrokenPlatform"

    async def publish(self, client, message):
        raise PlatformError("Authentication failed (HTTP 401)")


class CrashingPlatform(OkPlatform):
    name = "CrashingPlatform"

    async def publish(self, client, message):
        raise RuntimeError("boom")


def settings(**over) -> Settings:
    base = dict(
        telegram_bot_token="", telegram_chat_id="", discord_webhook_url="", discord_guild_id="",
        mastodon_instance_url="https://mastodon.test", mastodon_access_token="",
        bluesky_handle="", bluesky_app_password="", devto_api_key="", request_timeout=5.0,
    )
    base.update(over)
    return Settings(**base)


@pytest.fixture
def client():
    app.dependency_overrides[get_platforms] = lambda: [OkPlatform(), BrokenPlatform(), CrashingPlatform()]
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---------- input validation ----------
def test_valid_message_and_failure_isolation(client):
    r = client.post("/posting", json={"message": VALID})
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    by_name = {x["platform"]: x for x in body["results"]}
    assert by_name["OkPlatform"]["status"] == "success"
    assert by_name["OkPlatform"]["posted_url"] == "https://ok.example/post/1"
    assert by_name["OkPlatform"]["date"] and by_name["OkPlatform"]["time"]
    assert by_name["BrokenPlatform"]["status"] == "failed"
    assert by_name["BrokenPlatform"]["error"].startswith("Authentication failed")
    assert by_name["BrokenPlatform"]["public_access"] is False
    # an unexpected exception in one platform must not break the others
    assert by_name["CrashingPlatform"]["status"] == "failed"


@pytest.mark.parametrize(
    "message, fragment",
    [
        ("x" * 190 + " https://example.com", "exceed 200"),
        ("No link here at all", "exactly one CTA link (found 0)"),
        ("Two links https://a.com and https://b.com", "exactly one CTA link (found 2)"),
        ("Bad url https://not_a_domain", "valid domain"),
        ("Bad url https://localhost", "valid domain"),
        ("Bad scheme ftp://example.com/file", "http:// or https://"),
        ("Missing scheme www.example.com", "http:// or https://"),
        ("Bad port https://example.com:99999", "invalid port"),
        ("   ", "must not be empty"),
    ],
)
def test_invalid_messages_rejected(client, message, fragment):
    r = client.post("/posting", json={"message": message})
    assert r.status_code == 422
    body = r.json()
    assert body["success"] is False
    assert body["errors"][0]["field"] == "message"
    assert fragment in body["errors"][0]["message"]


def test_missing_and_wrong_type_body(client):
    assert client.post("/posting", json={}).status_code == 422
    assert client.post("/posting", json={"message": 123}).status_code == 422
    assert client.post("/posting", content="not json",
                       headers={"content-type": "application/json"}).status_code == 422


def test_exactly_200_chars_is_accepted(client):
    url = "https://example.com"
    msg = "a" * (200 - len(url) - 1) + " " + url
    assert len(msg) == 200
    assert client.post("/posting", json={"message": msg}).status_code == 200


def test_trailing_punctuation_not_part_of_url():
    assert extract_urls("Visit https://example.com/page.") == ["https://example.com/page"]
    assert validate_url("https://example.com/page?a=1#x") is None


# ---------- service ----------
def test_all_platforms_failing_returns_success_false():
    res = asyncio.run(publish_everywhere(VALID, [BrokenPlatform()]))
    assert res.success is False and res.results[0].status == "failed"


def test_unconfigured_platform_reports_missing_credentials():
    res = asyncio.run(publish_everywhere(VALID, [MastodonPlatform(settings())]))
    assert res.results[0].status == "failed"
    assert "MASTODON_ACCESS_TOKEN" in res.results[0].error


# ---------- real integrations against a mocked HTTP layer ----------
def mock_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_mastodon_success():
    def handler(req: httpx.Request):
        assert req.url.path == "/api/v1/statuses"
        assert req.headers["authorization"] == "Bearer tok"
        return httpx.Response(200, json={"url": "https://mastodon.test/@me/1", "visibility": "public"})

    p = MastodonPlatform(settings(mastodon_access_token="tok"))
    res = asyncio.run(publish_everywhere(VALID, [p], client=mock_client(handler)))
    r = res.results[0]
    assert (r.status, r.posted_url, r.public_access) == ("success", "https://mastodon.test/@me/1", True)


def test_mastodon_auth_error_does_not_leak_token():
    def handler(req):
        return httpx.Response(401, json={"error": "The access token is invalid"})

    p = MastodonPlatform(settings(mastodon_access_token="SECRET"))
    r = asyncio.run(publish_everywhere(VALID, [p], client=mock_client(handler))).results[0]
    assert r.status == "failed" and "401" in r.error and "SECRET" not in r.error


def test_telegram_public_channel_link_and_token_not_leaked():
    def handler(req):
        assert "/botTOKEN123/sendMessage" in req.url.path
        return httpx.Response(200, json={"result": {"message_id": 7, "chat": {"id": -100123, "username": "mychan"}}})

    p = TelegramPlatform(settings(telegram_bot_token="TOKEN123", telegram_chat_id="@mychan"))
    r = asyncio.run(publish_everywhere(VALID, [p], client=mock_client(handler))).results[0]
    assert r.posted_url == "https://t.me/mychan/7" and r.public_access is True

    def bad(req):
        return httpx.Response(401, json={"description": "Unauthorized"})

    r = asyncio.run(publish_everywhere(VALID, [p], client=mock_client(bad))).results[0]
    assert r.status == "failed" and "TOKEN123" not in r.error


def test_bluesky_two_step_flow_and_link_facet():
    calls = []

    def handler(req: httpx.Request):
        calls.append(req.url.path)
        if req.url.path.endswith("createSession"):
            return httpx.Response(200, json={"accessJwt": "jwt", "did": "did:plc:abc", "handle": "me.bsky.social"})
        record = __import__("json").loads(req.content)["record"]
        assert record["facets"][0]["features"][0]["uri"] == "https://example.com"
        return httpx.Response(200, json={"uri": "at://did:plc:abc/app.bsky.feed.post/3kxyz"})

    p = BlueskyPlatform(settings(bluesky_handle="me.bsky.social", bluesky_app_password="pw"))
    # public_access verification GET also goes through the mock -> 200
    r = asyncio.run(publish_everywhere(VALID, [p], client=mock_client(
        lambda req: handler(req) if "/xrpc/" in req.url.path else httpx.Response(200)))).results[0]
    assert r.status == "success"
    assert r.posted_url == "https://bsky.app/profile/me.bsky.social/post/3kxyz"
    assert r.public_access is True


def test_bluesky_facet_byte_offsets_with_unicode():
    msg = "Café ☕ https://example.com"
    f = BlueskyPlatform.build_facets(msg)[0]["index"]
    assert msg.encode()[f["byteStart"]:f["byteEnd"]] == b"https://example.com"


def test_timeout_is_reported_not_raised():
    def handler(req):
        raise httpx.ConnectTimeout("t")

    p = MastodonPlatform(settings(mastodon_access_token="tok"))
    r = asyncio.run(publish_everywhere(VALID, [p], client=mock_client(handler))).results[0]
    assert r.status == "failed" and r.error == "Request timed out"
