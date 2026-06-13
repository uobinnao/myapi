from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session_depends
from app.features.meta.schema import ApiInfo, HealthResponse, ProbeResponse
from app.features.meta.service import (
    build_api_info,
    build_health_response,
    check_dependencies,
    check_readiness,
)
from app.problem import PROBLEM_RESPONSES
from app.settings import Settings, get_settings
from app.state import AppState, get_app_state

router = APIRouter(tags=["meta"])


@router.get(
    "/",
    summary="Get API info",
    description="Return service metadata, documentation links, and the list of available endpoints.",
    response_description="API metadata and endpoint catalog",
    response_model=ApiInfo,
    responses={
        429: PROBLEM_RESPONSES[429],
        500: PROBLEM_RESPONSES[500],
    },
)
async def get_api_info(
    request: Request,
    cfg: Settings = Depends(get_settings),
) -> ApiInfo:
    base_url = str(request.base_url).rstrip("/")
    return build_api_info(base_url, cfg)


@router.get(
    "/health/live",
    summary="Get liveness status",
    description="Cheap liveness probe that only confirms the app process is running.",
    response_description="Liveness probe result",
    response_model=ProbeResponse,
    responses={
        429: PROBLEM_RESPONSES[429],
        500: PROBLEM_RESPONSES[500],
    },
)
async def get_live() -> ProbeResponse:
    return ProbeResponse(status="alive")


@router.get(
    "/health/ready",
    summary="Get readiness status",
    description="Readiness probe that checks whether the service is ready to receive traffic.",
    response_description="Readiness probe result",
    response_model=ProbeResponse,
    responses={
        429: PROBLEM_RESPONSES[429],
        503: {
            "model": ProbeResponse,
            "description": "Instance is alive but not ready to receive traffic",
        },
        500: PROBLEM_RESPONSES[500],
    },
)
async def get_ready(
    response: Response,
    cfg: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session_depends),
) -> ProbeResponse:
    _services, ready = await check_readiness(cfg, session)

    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ProbeResponse(status="not_ready")

    return ProbeResponse(status="ready")


@router.get(
    "/health",
    summary="Get health report",
    description="Return a detailed health report for the API, database, and USDA dependency.",
    response_description="Detailed health status report",
    response_model=HealthResponse,
    responses={
        429: PROBLEM_RESPONSES[429],
        503: {
            "model": HealthResponse,
            "description": "Detailed health report when the instance is not ready",
        },
        500: PROBLEM_RESPONSES[500],
    },
)
async def get_health(
    response: Response,
    cfg: Settings = Depends(get_settings),
    state: AppState = Depends(get_app_state),
    session: AsyncSession = Depends(get_session_depends),
) -> HealthResponse:
    services, ready = await check_dependencies(cfg, state, session)

    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return build_health_response(
        cfg=cfg,
        state=state,
        services=services,
        ready=ready,
    )
