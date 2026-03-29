from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.settings import Settings, get_settings


@pytest.fixture
def client() -> Iterator[TestClient]:
    def override_settings() -> Settings:
        return Settings(
            app_name="myapi",
            app_version="test",
            app_env="dev",
            usda_api_key=None,
        )

    app.dependency_overrides[get_settings] = override_settings

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
