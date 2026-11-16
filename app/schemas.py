"""Pydantic models and input validation."""
from __future__ import annotations

import re
from typing import List, Literal, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

MAX_MESSAGE_LENGTH = 200

# Anything that looks like a link: scheme://..., or starting with www.
_URL_CANDIDATE = re.compile(r"(?:\b[a-zA-Z][a-zA-Z0-9+.\-]*://|\bwww\.)[^\s<>\"']+")
_TRAILING_PUNCT = ".,;:!?)]}"
_HOSTNAME = re.compile(
    r"^(?=.{1,253}$)(?!-)[a-z0-9-]{1,63}(?<!-)"
    r"(?:\.(?!-)[a-z0-9-]{1,63}(?<!-))*"
    r"\.(?:[a-z]{2,63}|xn--[a-z0-9-]{1,59})$"
)


def extract_urls(text: str) -> List[str]:
    """Return every link-like token in the text, trailing punctuation removed."""
    return [m.group(0).rstrip(_TRAILING_PUNCT) for m in _URL_CANDIDATE.finditer(text)]


def validate_url(url: str) -> Optional[str]:
    """Return an error string if the URL is invalid, otherwise None."""
    if url.lower().startswith("www."):
        return f"'{url}' must start with http:// or https://"
    try:
        parsed = urlparse(url)
        port = parsed.port  # raises ValueError for a bad port
    except ValueError:
        return f"'{url}' is not a valid URL (malformed or invalid port)"
    if parsed.scheme not in ("http", "https"):
        return f"'{url}' must use http:// or https://"
    if parsed.username or parsed.password:
        return "URL must not contain credentials"
    host = (parsed.hostname or "").lower()
    if not _HOSTNAME.match(host):
        return f"'{url}' does not have a valid domain name"
    if port is not None and not (1 <= port <= 65535):
        return f"'{url}' has an invalid port"
    return None


class PostingRequest(BaseModel):
    message: str = Field(
        ...,
        description="Message to publish (max 200 chars, exactly one http(s) link).",
        examples=["Check out our latest business platform and grow your online visibility. https://example.com"],
    )

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Message must not be empty")
        if len(value) > MAX_MESSAGE_LENGTH:
            raise ValueError(
                f"Message must not exceed {MAX_MESSAGE_LENGTH} characters (got {len(value)})"
            )
        urls = extract_urls(value)
        if len(urls) != 1:
            raise ValueError(f"Message must contain exactly one CTA link (found {len(urls)})")
        problem = validate_url(urls[0])
        if problem:
            raise ValueError(f"Invalid CTA link: {problem}")
        return value


class PlatformResult(BaseModel):
    platform: str
    status: Literal["success", "failed"]
    posted_url: Optional[str] = None
    public_access: bool = False
    date: Optional[str] = None
    time: Optional[str] = None
    error: Optional[str] = None


class PostingResponse(BaseModel):
    success: bool = Field(..., description="True if at least one platform succeeded.")
    results: List[PlatformResult]


class ValidationErrorItem(BaseModel):
    field: str
    message: str


class ValidationErrorResponse(BaseModel):
    success: bool = False
    errors: List[ValidationErrorItem]
