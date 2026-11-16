"""Fan the message out to every platform concurrently and isolate failures."""
from __future__ import annotations

import asyncio
from typing import List, Optional, Sequence

import httpx

from app.config import get_settings
from app.platforms.base import BasePlatform
from app.schemas import PlatformResult, PostingResponse


async def publish_everywhere(
    message: str,
    platforms: Sequence[BasePlatform],
    client: Optional[httpx.AsyncClient] = None,
) -> PostingResponse:
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=get_settings().request_timeout)
    try:
        # BasePlatform.post never raises; return_exceptions is a second safety net.
        raw = await asyncio.gather(*(p.post(client, message) for p in platforms), return_exceptions=True)
    finally:
        if owns_client:
            await client.aclose()

    results: List[PlatformResult] = []
    for platform, item in zip(platforms, raw):
        if isinstance(item, BaseException):
            item = platform._failed(f"Unexpected error ({type(item).__name__})")
        results.append(item)
    return PostingResponse(success=any(r.status == "success" for r in results), results=results)
