"""Base class shared by every platform integration."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

import httpx

from app.schemas import PlatformResult

logger = logging.getLogger("posting")


class PlatformError(Exception):
    """Raised by an integration with a safe, human-readable message."""


@dataclass
class PublishOutcome:
    posted_url: str
    # True/False if the platform knows; None -> verify with an unauthenticated GET.
    public_access: Optional[bool] = None


def describe_http_error(platform: str, response: httpx.Response) -> str:
    """Build an error message from a response WITHOUT echoing request URLs (tokens!)."""
    detail = ""
    try:
        data = response.json()
        if isinstance(data, dict):
            detail = str(
                data.get("error_description") or data.get("error") or data.get("message")
                or data.get("description") or ""
            )
    except ValueError:
        detail = response.text[:150]
    detail = detail.strip()[:200]
    if response.status_code in (401, 403):
        base = "Authentication failed"
    elif response.status_code == 429:
        base = "Rate limited"
    else:
        base = "Request rejected"
    return f"{base} (HTTP {response.status_code})" + (f": {detail}" if detail else "")


async def check_public_access(client: httpx.AsyncClient, url: str) -> bool:
    """Fetch the URL anonymously and see whether it is publicly reachable."""
    try:
        resp = await client.get(url, follow_redirects=True, headers={"User-Agent": "posting-checker/1.0"})
        return resp.status_code == 200
    except httpx.HTTPError:
        return False


class BasePlatform(ABC):
    name: str = "base"

    @abstractmethod
    def missing_credentials(self) -> List[str]:
        """Return env var names that are not set."""

    @abstractmethod
    async def publish(self, client: httpx.AsyncClient, message: str) -> PublishOutcome:
        """Publish the message; raise PlatformError on failure."""

    async def post(self, client: httpx.AsyncClient, message: str):
        """Never raises: always returns a PlatformResult."""
        missing = self.missing_credentials()
        if missing:
            return self._failed("Missing credentials: " + ", ".join(missing))
        try:
            outcome = await self.publish(client, message)
            public = outcome.public_access
            if public is None:
                public = await check_public_access(client, outcome.posted_url)
            now = datetime.now(timezone.utc)
            logger.info("%s: posted -> %s", self.name, outcome.posted_url)
            return PlatformResult(
                platform=self.name,
                status="success",
                posted_url=outcome.posted_url,
                public_access=public,
                date=now.date().isoformat(),
                time=now.strftime("%H:%M:%S"),
                error=None,
            )
        except PlatformError as exc:
            return self._failed(str(exc))
        except httpx.TimeoutException:
            return self._failed("Request timed out")
        except httpx.HTTPError as exc:
            return self._failed(f"Network error ({type(exc).__name__})")
        except Exception as exc:  # last line of defence: one platform must never break the rest
            logger.exception("%s: unexpected error", self.name)
            return self._failed(f"Unexpected error ({type(exc).__name__})")

    def _failed(self, error: str) -> PlatformResult:
        logger.warning("%s: failed - %s", self.name, error)
        return PlatformResult(
            platform=self.name, status="failed", posted_url=None,
            public_access=False, date=None, time=None, error=error,
        )
