from typing import Protocol, cast

import httpx
from fastapi import Request
from slowapi import Limiter


class AppState(Protocol):
    started_at: float
    http: httpx.AsyncClient
    limiter: Limiter


def get_app_state(request: Request) -> AppState:
    return cast(AppState, request.app.state)
