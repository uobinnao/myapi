from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "myapi"
    app_version: str = "0.1.0"
    app_env: Literal["dev", "preview","staging", "prod"] = "dev"

    usda_base_url: str = "https://api.nal.usda.gov/fdc/v1"
    usda_api_key: str | None = None

    host: str = "0.0.0.0"
    port: int = 8000

    cors_allow_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "https://your-frontend.com",
        ]
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()

