from datetime import datetime, timezone
from time import monotonic

import httpx

from app.db.health import check_database
from app.features.meta.schema import (
    ApiInfo,
    EndpointDoc,
    HealthResponse,
    HealthServices,
)
from app.settings import Settings
from app.state import AppState


def build_api_info(base_url: str, cfg: Settings) -> ApiInfo:
    return ApiInfo(
        name=cfg.app_name,
        version=cfg.app_version,
        environment=cfg.app_env,
        git_sha=cfg.git_sha,
        release_id=cfg.release_id,
        description="A REST API to fetch food information from USDA FoodData Central.",
        base_url=base_url,
        docs_url=f"{base_url}/docs",
        openapi_url=f"{base_url}/openapi.json",
        endpoints={
            "root": EndpointDoc(
                path="/",
                method="GET",
                description="API metadata",
            ),
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


def _database_ready(database_status: str) -> bool:
    return database_status in {"disabled", "healthy"}


async def check_readiness(cfg: Settings) -> tuple[HealthServices, bool]:
    """
    Cheap readiness check.

    DB is required only when DATABASE_URL exists.
    USDA API key is still required because this app depends on USDA.
    """
    database_status = await check_database(cfg)

    services = HealthServices(
        api="healthy",
        database=database_status,
        usda_api_key="configured" if cfg.usda_api_key else "missing",
        usda_api="not_checked",
    )

    ready = _database_ready(database_status) and bool(cfg.usda_api_key)
    return services, ready


async def check_dependencies(
    cfg: Settings,
    state: AppState,
) -> tuple[HealthServices, bool]:
    """
    Detailed dependency check.

    DB-less projects report database='disabled' and can still be ready.
    """
    database_status = await check_database(cfg)

    services = HealthServices(
        api="healthy",
        database=database_status,
        usda_api_key="configured" if cfg.usda_api_key else "missing",
        usda_api="not_configured",
    )

    db_ready = _database_ready(database_status)
    usda_ready = False

    if cfg.usda_api_key:
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

        except httpx.TimeoutException as exc:
            services.usda_api = f"timeout: {type(exc).__name__}: {exc}"

        except httpx.RequestError as exc:
            services.usda_api = f"unreachable: {type(exc).__name__}: {exc}"

        else:
            if response.is_success:
                services.usda_api = "healthy"
                usda_ready = True
            else:
                services.usda_api = (
                    f"unhealthy: HTTP {response.status_code}: {response.text[:300]}"
                )

    ready = db_ready and usda_ready
    return services, ready


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
        git_sha=cfg.git_sha,
        release_id=cfg.release_id,
        services=services,
    )
