"""FastAPI entry point.

Run:  uvicorn app.main:app --host 0.0.0.0 --port 4000
Docs: http://localhost:4000/docs
"""
from __future__ import annotations

import logging
from typing import List

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.platforms import get_platforms
from app.platforms.base import BasePlatform
from app.schemas import (
    PostingRequest, PostingResponse, ValidationErrorItem, ValidationErrorResponse,
)
from app.services.posting_service import publish_everywhere

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(
    title="Automated Multi-Platform Posting System",
    description="Publishes one short message with a single CTA link to multiple platforms.",
    version="1.0.0",
)


@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    errors = []
    for err in exc.errors():
        loc = [str(p) for p in err.get("loc", ()) if p != "body"]
        msg = str(err.get("msg", "Invalid input"))
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, "):]
        errors.append(ValidationErrorItem(field=".".join(loc) or "body", message=msg))
    body = ValidationErrorResponse(success=False, errors=errors)
    return JSONResponse(status_code=422, content=body.model_dump())


@app.get("/health", tags=["meta"])
async def health() -> dict:
    return {"status": "ok"}


@app.post(
    "/posting",
    response_model=PostingResponse,
    responses={422: {"model": ValidationErrorResponse, "description": "Invalid input"}},
    tags=["posting"],
)
async def posting(
    payload: PostingRequest,
    platforms: List[BasePlatform] = Depends(get_platforms),
) -> PostingResponse:
    return await publish_everywhere(payload.message, platforms)
