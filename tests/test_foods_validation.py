from fastapi.testclient import TestClient


def test_foods_rejects_too_short_type(client: TestClient):
    response = client.get("/foods", params={"type": "a"})

    assert response.status_code == 400

    body = response.json()
    assert body["title"] == "Invalid Food Type"


def test_foods_rejects_symbol_only_type(client: TestClient):
    response = client.get("/foods", params={"type": "!!!"})

    assert response.status_code == 422
