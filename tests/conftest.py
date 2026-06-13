import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.db import Base, get_session_depends, test_data
from fastapi.testclient import TestClient
from app.main import app
from app.settings import Settings, get_settings


@pytest_asyncio.fixture
async def db_session_maker(tmpdir):
    """Creates a test database engine, complete with fake data."""
    test_database_url = f"sqlite+aiosqlite:///{tmpdir}/test_database.db"  # Use SQLite for testing; adjust as needed
    engine = create_async_engine(test_database_url, future=True, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session_maker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session_maker() as session:
        await test_data(session)

    yield async_session_maker

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_session_maker):
    async with db_session_maker() as session:
        yield session


@pytest_asyncio.fixture
async def fastapi_client(db_session_maker):
    """Fixture to create a FastAPI test client with isolated test dependencies."""

    async def get_session_depends_override():
        async with db_session_maker() as session:
            yield session

    def get_settings_override():
        return Settings(
            app_name="myapi",
            app_env="dev",
            usda_api_key=None,
        )

    app.dependency_overrides[get_session_depends] = get_session_depends_override
    app.dependency_overrides[get_settings] = get_settings_override

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()
    get_settings.cache_clear()
