# Best way to fake auth, DB, or external services
from fastapi.testclient import TestClient
from app.main import app, get_current_user

def fake_user():
    return {"id": 1, "name": "Test User"}

def test_me():
    app.dependency_overrides[get_current_user] = fake_user
    client = TestClient(app)

    r = client.get("/me")
    assert r.status_code == 200
    assert r.json()["name"] == "Test User"

    app.dependency_overrides = {}
