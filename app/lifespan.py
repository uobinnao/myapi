from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import monotonic
from typing import cast

import httpx
from fastapi import FastAPI

from app.limiter import limiter
from app.settings import get_settings
from app.state import AppState


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    state = cast(AppState, app.state)

    state.started_at = monotonic()
    state.limiter = limiter

    async with httpx.AsyncClient(
        base_url=settings.usda_base_url,
        headers={"Accept": "application/json"},
    ) as client:
        state.http = client
        yield
