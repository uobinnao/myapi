from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def check_database(
    session: AsyncSession,
    *,
    timeout_seconds: float = 2.0,
) -> str:
    try:
        async with asyncio.timeout(timeout_seconds):
            await session.execute(select(1))

        return "healthy"

    except TimeoutError as exc:
        return f"timeout: {type(exc).__name__}: {exc}"

    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"
