from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncGenerator

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import NullPool

from app.settings import Settings, get_settings

settings = get_settings()


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


def get_database_url(settings: Settings) -> str:
    """
    Runtime app DB.

    dev  -> local PostgreSQL
    prod -> Neon pooled PostgreSQL
    """
    if settings.app_env == "dev":
        return settings.database_url

    if settings.app_env == "prod":
        if not settings.database_url_pooled:
            raise RuntimeError("DATABASE_URL_POOLED is required when APP_ENV=prod")
        return settings.database_url_pooled

    return settings.database_url


def get_migration_database_url(settings: Settings) -> str:
    """
    Alembic migration DB.

    dev  -> local PostgreSQL
    prod -> Neon direct PostgreSQL
    """
    if settings.app_env == "dev":
        return settings.database_url

    if settings.app_env == "prod":
        if not settings.database_url_direct:
            raise RuntimeError("DATABASE_URL_DIRECT is required when APP_ENV=prod")
        return settings.database_url_direct

    return settings.database_url


engine = create_async_engine(
    to_async_db_url(get_database_url(settings)),
    future=True,
    pool_pre_ping=True,
    poolclass=NullPool if settings.app_env == "prod" else None,
)

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

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def get_session_depends() -> AsyncGenerator[AsyncSession, None]:
    async with get_session() as session:
        yield session


async def test_data(session: AsyncSession) -> None:
    """Populate the development database with initial data."""

    if settings.app_env != "dev":
        raise ValueError("test_data() can only run when APP_ENV=dev")

    # Add test/dev data here
    # Example: Add initial data to the session
    # await session.add_all([YourModel(name="Test")])
    # await session.commit()
