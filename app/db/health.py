from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.database import get_session, session_context
from app.settings import Settings


async def check_database(
    cfg: Settings,
    *,
    session_maker: async_sessionmaker[AsyncSession] | None = None,
    timeout_seconds: float = 2.0,
) -> str:
    """
    Runtime DB health check.

    If DATABASE_URL is missing, DB is intentionally disabled.
    This lets DB-less apps pass readiness without importing/creating an engine.
    """
    if not cfg.database_enabled:
        return "disabled"

    try:
        async with asyncio.timeout(timeout_seconds):
            if session_maker is None:
                async with get_session() as session:
                    await session.execute(select(1))
            else:
                async with session_context(session_maker) as session:
                    await session.execute(select(1))

        return "healthy"

    except TimeoutError as exc:
        return f"timeout: {type(exc).__name__}: {exc}"

    except Exception as exc:
        return f"unhealthy: {type(exc).__name__}: {exc}"
