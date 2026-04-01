from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.settings import Settings, get_settings


@pytest.fixture
def override_settings() -> Iterator[None]:
    def _override_settings() -> Settings:
        return Settings(
            app_name="myapi",
            app_version="test",
            app_env="dev",
            usda_api_key=None,
        )

    app.dependency_overrides[get_settings] = _override_settings
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client(override_settings: None) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
