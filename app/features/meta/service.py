from datetime import datetime, timezone
from time import monotonic

import httpx

from app.schema import ApiInfo, EndpointDoc, HealthResponse, HealthServices
from app.settings import Settings
from app.state import AppState


def build_api_info(base_url: str, cfg: Settings) -> ApiInfo:
    return ApiInfo(
        name=cfg.app_name,
        version=cfg.app_version,
        description="A REST API to fetch food information from USDA FoodData Central.",
        baseUrl=base_url,
        docsUrl=f"{base_url}/docs",
        openapiUrl=f"{base_url}/openapi.json",
        endpoints={
            "root": EndpointDoc(path="/", method="GET", description="API metadata"),
            "health_live": EndpointDoc(
                path="/health/live",
                method="GET",
                description="Cheap liveness probe",
            ),
            "health_ready": EndpointDoc(
                path="/health/ready",
                method="GET",
                description="Readiness probe for traffic routing",
            ),
            "health": EndpointDoc(
                path="/health",
                method="GET",
                description="Detailed health status",
            ),
            "foods": EndpointDoc(
                path="/foods",
                method="GET",
                description="Search for food items",
            ),
        },
    )


async def check_usda_dependency(
    cfg: Settings,
    state: AppState,
) -> tuple[HealthServices, bool]:
    services = HealthServices(
        api="healthy",
        usda_api_key="configured" if cfg.usda_api_key else "missing",
        usda_api="not_configured",
    )

    if not cfg.usda_api_key:
        return services, False

    try:
        response = await state.http.get(
            "/foods/search",
            params={
                "api_key": cfg.usda_api_key,
                "query": "test",
                "pageSize": 1,
            },
            timeout=httpx.Timeout(3.0, connect=1.5),
        )
    except httpx.TimeoutException:
        services.usda_api = "timeout"
        return services, False
    except httpx.RequestError:
        services.usda_api = "unreachable"
        return services, False

    if response.is_success:
        services.usda_api = "healthy"
        return services, True

    services.usda_api = "unhealthy"
    return services, False


def build_health_response(
    *,
    cfg: Settings,
    state: AppState,
    services: HealthServices,
    ready: bool,
) -> HealthResponse:
    return HealthResponse(
        status="healthy" if ready else "unhealthy",
        timestamp=datetime.now(timezone.utc),
        uptime=monotonic() - state.started_at,
        environment=cfg.app_env,
        version=cfg.app_version,
        services=services,
    )
