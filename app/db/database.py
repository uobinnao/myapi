"""
engine is lazy
DB-less app does not crash at import time
DATABASE_URL is runtime only
DATABASE_MIGRATION_URL is migration only
Dependency injectable via make_engine(), make_session_maker(), and session_context()
"""


# SQLAlchemy async engine requires non-standard driver DSN that don't work with other libraries.
# We use the standard but transform it for the async engine.
# engine_mappings = {
#     "sqlite": "sqlite+aiosqlite",
#     "postgresql": "postgresql+psycopg",
# }
# db_url = settings.database_url
# for find, replace in engine_mappings.items():
#     db_url = db_url.replace(find, replace)
# engine = create_async_engine(db_url, future=True)

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncGenerator

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import NullPool

from app.settings import Settings, get_settings


NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


_engine: AsyncEngine | None = None
_session_maker: async_sessionmaker[AsyncSession] | None = None


def to_async_db_url(url: str) -> str:
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)

    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)

    if url.startswith("postgresql+psycopg://"):
        return url

    if url.startswith("sqlite:///"):
        return url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)

    if url.startswith("sqlite+aiosqlite:///"):
        return url

    return url


def get_database_url(settings: Settings) -> str | None:
    """
    Runtime app DB only.

    This should read DATABASE_URL.
    It should not read DATABASE_MIGRATION_URL.
    """
    return settings.database_url


def require_database_url(settings: Settings) -> str:
    url = get_database_url(settings)

    if not url:
        raise RuntimeError(
            "Database is not configured. Set DATABASE_URL to enable runtime database access."
        )

    return url


def get_migration_database_url(settings: Settings) -> str:
    """
    Alembic migration DB only.

    This should read DATABASE_MIGRATION_URL.
    Runtime app code should not call this.
    """
    if settings.database_migration_url:
        return settings.database_migration_url

    if settings.app_env == "dev" and settings.database_url:
        return settings.database_url

    raise RuntimeError("DATABASE_MIGRATION_URL is required for migrations outside dev.")


def make_engine(settings: Settings) -> AsyncEngine:
    """
    Pure factory.

    Good for tests and dependency injection.
    Does not use globals.
    """
    engine_kwargs: dict[str, Any] = {
        "future": True,
        "pool_pre_ping": True,
    }

    if settings.app_env in {"preview", "staging", "prod"}:
        engine_kwargs["poolclass"] = NullPool

    return create_async_engine(
        to_async_db_url(require_database_url(settings)),
        **engine_kwargs,
    )


def make_session_maker(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """
    Pure factory.

    Good for injecting custom test engines.
    """
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


def get_engine(settings: Settings | None = None) -> AsyncEngine:
    """
    Lazy app singleton.

    DATABASE_URL is required only when this function is called.
    """
    global _engine

    if _engine is None:
        _engine = make_engine(settings or get_settings())

    return _engine


def get_session_maker(
    settings: Settings | None = None,
) -> async_sessionmaker[AsyncSession]:
    """
    Lazy app singleton.

    Session maker is created only when DB access is requested.
    """
    global _session_maker

    if _session_maker is None:
        _session_maker = make_session_maker(get_engine(settings))

    return _session_maker


@asynccontextmanager
async def session_context(
    session_maker: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """
    Fully injectable session context.
    """
    async with session_maker() as session:
        yield session


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    App runtime session context.
    """
    async with session_context(get_session_maker()) as session:
        yield session


async def get_session_depends() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency.
    """
    async with get_session() as session:
        yield session


async def dispose_engine() -> None:
    """
    Test/shutdown helper.
    """
    global _engine, _session_maker

    if _engine is not None:
        await _engine.dispose()

    _engine = None
    _session_maker = None


async def test_data(session: AsyncSession) -> None:
    cfg = get_settings()

    if cfg.app_env != "dev":
        raise ValueError("test_data() can only run when APP_ENV=dev")

    # Add test/dev data here.
