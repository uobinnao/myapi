from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine


async def check_database(
    engine: AsyncEngine,
    *,
    timeout_seconds: float = 2.0,
) -> str:
    try:
        async with asyncio.timeout(timeout_seconds):
            async with engine.connect() as conn:
                await conn.execute(select(1))

        return "healthy"

    except TimeoutError:
        return "timeout"

    except Exception:
        return "unhealthy"
