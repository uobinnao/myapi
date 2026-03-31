import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.anyio
async def test_health_live_async(override_settings: None) -> None:
    async with LifespanManager(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


@pytest.mark.anyio
async def test_health_ready_async(override_settings: None) -> None:
    async with LifespanManager(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}


@pytest.mark.anyio
async def test_health_async(override_settings: None) -> None:
    async with LifespanManager(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.get("/health")

    assert response.status_code == 503

    body = response.json()
    assert body["status"] == "unhealthy"
    assert body["environment"] == "dev"
    assert body["version"] == "test"
    assert body["services"]["api"] == "healthy"
    assert body["services"]["usda_api_key"] == "missing"
    assert body["services"]["usda_api"] == "not_configured"
