from fastapi.testclient import TestClient


def test_root_returns_metadata(client: TestClient):
    response = client.get("/")

    assert response.status_code == 200

    body = response.json()
    assert body["name"] == "myapi"
    assert body["endpoints"]["health_live"]["path"] == "/health/live"
    assert body["endpoints"]["foods"]["path"] == "/foods"


def test_live_returns_alive(client: TestClient):
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_ready_503_when_usda_key_missing(client: TestClient):
    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}


def test_health_unhealthy_when_usda_key_missing(client: TestClient):
    response = client.get("/health")

    assert response.status_code == 503

    body = response.json()
    assert body["status"] == "unhealthy"
    assert body["services"]["usda_api_key"] == "missing"
