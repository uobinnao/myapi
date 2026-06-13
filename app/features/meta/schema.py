from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class EndpointDoc(BaseModel):
    path: str
    method: str
    description: str


class ApiInfo(BaseModel):
    name: str
    version: str
    environment: str
    git_sha: str
    release_id: str
    description: str
    base_url: str
    docs_url: str
    openapi_url: str
    endpoints: dict[str, EndpointDoc]


class HealthServices(BaseModel):
    api: str
    database: str = "not_checked"
    usda_api_key: str
    usda_api: str


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    uptime: float
    environment: str
    version: str
    git_sha: str
    release_id: str
    services: HealthServices


class ProbeResponse(BaseModel):
    status: str


class ProblemDetail(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str
    instance: str | None = None
    timestamp: datetime | None = None
    errors: list[dict[str, Any]] | None = None
    upstream_status: int | None = None
    upstream_details: Any | None = None

    model_config = ConfigDict(extra="allow")
