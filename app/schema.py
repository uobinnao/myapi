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
    description: str
    baseUrl: str
    docsUrl: str
    openapiUrl: str
    endpoints: dict[str, EndpointDoc]


class HealthServices(BaseModel):
    api: str
    usda_api_key: str
    usda_api: str


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    uptime: float
    environment: str
    version: str
    services: HealthServices


class Macros(BaseModel):
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None


class FoodItem(BaseModel):
    fdcId: int | None = None
    description: str | None = None
    brandName: str | None = None
    servingSize: float | None = None
    servingSizeUnit: str | None = None
    calories: float | None = None
    macros: Macros


class FoodsResponse(BaseModel):
    query: str
    limit: int
    count: int
    foods: list[FoodItem]


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


class ProbeResponse(BaseModel):
    status: str
