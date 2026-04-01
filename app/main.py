from __future__ import annotations

import re
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from http import HTTPStatus
from time import monotonic
from typing import Annotated, Any, Protocol, cast

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.schema import (
    ApiInfo,
    EndpointDoc,
    FoodItem,
    FoodsResponse,
    HealthResponse,
    HealthServices,
    Macros,
    ProbeResponse,
    ProblemDetail,
)
from app.settings import Settings, get_settings

FOOD_TYPE_PATTERN = re.compile(r"^[a-zA-Z0-9\s\-_]+$")
PROBLEMATIC_PATTERNS = [
    re.compile(r"^\d+$"),
    re.compile(r"^[^\w\s]+$"),
    re.compile(r"^(test|debug|admin|system)$", re.IGNORECASE),
]

settings = get_settings()
rate_limiter = Limiter(
    key_func=get_remote_address,
    headers_enabled=False,
)


class AppState(Protocol):
    started_at: float
    http: httpx.AsyncClient
    limiter: Limiter


def problem_openapi_response(description: str) -> dict[str, Any]:
    return {
        "model": ProblemDetail,
        "content": {"application/problem+json": {}},
        "description": description,
    }


PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: problem_openapi_response("Bad request"),
    401: problem_openapi_response("Unauthorized"),
    403: problem_openapi_response("Forbidden"),
    404: problem_openapi_response("Not found"),
    405: problem_openapi_response("Method not allowed"),
    422: problem_openapi_response("Request validation failed"),
    429: problem_openapi_response("Too many requests"),
    500: problem_openapi_response("Internal server error"),
    502: problem_openapi_response("Bad gateway"),
    503: problem_openapi_response("Service unavailable"),
}


def problem_type_uri(request: Request, slug: str) -> str:
    base = str(request.base_url).rstrip("/")
    return f"{base}/problems/{slug}"


def default_problem_slug(status_code: int) -> str:
    return {
        400: "bad-request",
        401: "unauthorized",
        403: "forbidden",
        404: "not-found",
        405: "method-not-allowed",
        422: "validation-error",
        429: "too-many-requests",
        500: "internal-server-error",
        502: "bad-gateway",
        503: "service-unavailable",
    }.get(status_code, "http-error")


def http_title(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return "HTTP Error"


def problem_body(
    request: Request,
    *,
    title: str,
    status_code: int,
    detail: str,
    type_: str | None = None,
    instance: str | None = None,
    **extensions: Any,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "type": type_ or problem_type_uri(request, default_problem_slug(status_code)),
        "title": title,
        "status": status_code,
        "detail": detail,
        "instance": instance or str(request.url),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    for key, value in extensions.items():
        if value is not None:
            body[key] = value

    return body


def problem_response(
    request: Request,
    *,
    title: str,
    status_code: int,
    detail: str,
    type_: str | None = None,
    headers: Mapping[str, str] | None = None,
    **extensions: Any,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=problem_body(
            request,
            title=title,
            status_code=status_code,
            detail=detail,
            type_=type_,
            **extensions,
        ),
        media_type="application/problem+json",
        headers=dict(headers) if headers is not None else None,
    )


def get_app_state(request: Request) -> AppState:
    return cast(AppState, request.app.state)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    state = cast(AppState, app.state)

    state.started_at = monotonic()
    state.limiter = rate_limiter

    async with httpx.AsyncClient(
        base_url=settings.usda_base_url,
        headers={"Accept": "application/json"},
    ) as client:
        state.http = client
        yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    summary="Search USDA FoodData Central foods",
    description="FastAPI service that proxies USDA FoodData Central food search.",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "meta", "description": "Service metadata and health"},
        {"name": "foods", "description": "Food search operations"},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(
    request: Request, _exc: RateLimitExceeded
) -> JSONResponse:
    return problem_response(
        request,
        title="Too Many Requests",
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Rate limit exceeded. Please try again later.",
        type_=problem_type_uri(request, "too-many-requests"),
    )


@app.exception_handler(RequestValidationError)
async def request_validation_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors: list[dict[str, Any]] = []

    for err in exc.errors():
        loc = [str(part) for part in err.get("loc", ())]
        pointer = "#/" + "/".join(loc) if loc else "#/"
        errors.append(
            {
                "detail": err["msg"],
                "pointer": pointer,
                "error_type": err.get("type"),
            }
        )

    return problem_response(
        request,
        title="Request Validation Failed",
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail="The request parameters or body are invalid.",
        type_=problem_type_uri(request, "validation-error"),
        errors=errors,
    )


def coerce_problem_detail(
    request: Request,
    *,
    status_code: int,
    detail: Any,
) -> dict[str, Any] | None:
    if not isinstance(detail, dict):
        return None

    if not {"title", "status", "detail"} <= set(detail.keys()):
        return None

    body = dict(detail)
    body.setdefault(
        "type", problem_type_uri(request, default_problem_slug(status_code))
    )
    body.setdefault("title", http_title(status_code))
    body["status"] = status_code
    body.setdefault("instance", str(request.url))
    body.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    return body


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    existing_problem = coerce_problem_detail(
        request,
        status_code=exc.status_code,
        detail=exc.detail,
    )
    if existing_problem is not None:
        return JSONResponse(
            status_code=exc.status_code,
            content=existing_problem,
            media_type="application/problem+json",
            headers=exc.headers,
        )

    title = http_title(exc.status_code)
    detail = exc.detail if isinstance(exc.detail, str) and exc.detail else title

    return problem_response(
        request,
        title=title,
        status_code=exc.status_code,
        detail=detail,
        type_=problem_type_uri(request, default_problem_slug(exc.status_code)),
        headers=exc.headers,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    request: Request, _exc: Exception
) -> JSONResponse:
    return problem_response(
        request,
        title="Internal Server Error",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="An unexpected error occurred. Please try again later.",
        type_=problem_type_uri(request, "internal-server-error"),
    )


@app.get(
    "/",
    tags=["meta"],
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


# @app.get(
#     "/health",
#     tags=["meta"],
#     response_model=HealthResponse,
#     responses={
#         429: PROBLEM_RESPONSES[429],
#         503: PROBLEM_RESPONSES[503],
#     },
# )
# async def get_health(
#     request: Request,
#     cfg: Settings = Depends(get_settings),
#     state: AppState = Depends(get_app_state),
# ) -> HealthResponse:
#     services = HealthServices(
#         api="healthy",
#         usda_api_key="configured" if cfg.usda_api_key else "missing",
#         usda_api="not_configured",
#     )

#     if cfg.usda_api_key:
#         try:
#             response = await state.http.get(
#                 "/foods/search",
#                 params={
#                     "api_key": cfg.usda_api_key,
#                     "query": "test",
#                     "pageSize": 1,
#                 },
#                 timeout=httpx.Timeout(5.0, connect=5.0),
#             )
#             services.usda_api = "healthy" if response.is_success else "unhealthy"
#         except httpx.RequestError:
#             services.usda_api = "unreachable"

#     return HealthResponse(
#         status="healthy",
#         timestamp=datetime.now(timezone.utc),
#         uptime=monotonic() - state.started_at,
#         environment=cfg.app_env,
#         version=cfg.app_version,
#         services=services,
#     )


async def check_usda_dependency(
    cfg: Settings,
    state: AppState,
) -> tuple[HealthServices, bool]:
    services = HealthServices(
        api="healthy",
        usda_api_key="configured" if cfg.usda_api_key else "missing",
        usda_api="not_configured",
    )

    # This app cannot serve /foods correctly without the API key.
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


@app.get(
    "/health/live",
    tags=["meta"],
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
    # Keep liveness cheap and dependency-free.
    return ProbeResponse(status="alive")


@app.get(
    "/health/ready",
    tags=["meta"],
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
    state: AppState = Depends(get_app_state),
) -> ProbeResponse:
    _services, ready = await check_usda_dependency(cfg, state)

    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ProbeResponse(status="not_ready")

    return ProbeResponse(status="ready")


@app.get(
    "/health",
    tags=["meta"],
    summary="Get health report",
    description="Return a detailed health report for the API and its USDA dependency.",
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
) -> HealthResponse:
    services, ready = await check_usda_dependency(cfg, state)

    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthResponse(
        status="healthy" if ready else "unhealthy",
        timestamp=datetime.now(timezone.utc),
        uptime=monotonic() - state.started_at,
        environment=cfg.app_env,
        version=cfg.app_version,
        services=services,
    )


@app.get(
    "/foods",
    tags=["foods"],
    summary="Search foods",
    description="Search USDA FoodData Central by food type and return normalized results.",
    response_description="Normalized food search results",
    response_model=FoodsResponse,
    responses=PROBLEM_RESPONSES,
    openapi_extra={
        "x-rateLimiting": {
            "windowMs": "15 minutes",
            "maxRequests": 100,
            "description": "Rate limited to 100 requests per IP address per 15-minute window",
        }
    },
)
async def search_foods(
    request: Request,
    food_type: Annotated[
        str,
        Query(
            alias="type",
            min_length=1,
            max_length=100,
            pattern=r"^[a-zA-Z0-9\s\-_]+$",
            description='Food type to search for (e.g. "apple", "chicken breast")',
            openapi_examples={
                "apple": {
                    "summary": "Simple search",
                    "value": "apple",
                },
                "protein": {
                    "summary": "Protein source",
                    "value": "chicken breast",
                },
            },
        ),
    ],
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=50,
            description="Maximum number of results to return (1-50, default: 10)",
            openapi_examples={
                "default": {
                    "summary": "Default result size",
                    "value": 10,
                },
                "small": {
                    "summary": "Small result set",
                    "value": 5,
                },
            },
        ),
    ] = 10,
    cfg: Settings = Depends(get_settings),
    state: AppState = Depends(get_app_state),
) -> FoodsResponse:

    query_value = validate_food_type(request, food_type.strip())

    if not cfg.usda_api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=problem_body(
                request,
                title="Configuration Error",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="USDA_API_KEY is not configured.",
                type_=problem_type_uri(request, "configuration-error"),
            ),
        )

    # query_value = validate_food_type(request, food_type.strip())

    try:
        response = await state.http.get(
            "/foods/search",
            params={
                "api_key": cfg.usda_api_key,
                "query": query_value,
                "pageSize": limit,
            },
            timeout=httpx.Timeout(10.0, connect=5.0),
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=problem_body(
                request,
                title="Upstream Timeout",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Request to USDA API timed out.",
                type_=problem_type_uri(request, "upstream-timeout"),
            ),
        )
    except httpx.RequestError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=problem_body(
                request,
                title="Upstream Network Error",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Failed to connect to USDA API.",
                type_=problem_type_uri(request, "upstream-network-error"),
            ),
        )

    if response.is_error:
        upstream_details = safe_json(response)
        message_map = {
            400: "Invalid request sent to USDA API.",
            401: "USDA API authentication failed.",
            403: "Access to USDA API denied.",
            404: "USDA API endpoint not found.",
            429: "USDA API rate limit exceeded.",
            500: "USDA API internal server error.",
            502: "USDA API gateway error.",
            503: "USDA API service unavailable.",
            504: "USDA API gateway timeout.",
        }
        mapped_status = 503 if response.status_code >= 500 else response.status_code

        raise HTTPException(
            status_code=mapped_status,
            detail=problem_body(
                request,
                title="Upstream API Error",
                status_code=mapped_status,
                detail=message_map.get(
                    response.status_code,
                    "USDA API error occurred.",
                ),
                type_=problem_type_uri(request, "upstream-api-error"),
                upstream_status=response.status_code,
                upstream_details=upstream_details,
            ),
        )

    data = safe_json(response)
    if not isinstance(data, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=problem_body(
                request,
                title="Bad Gateway",
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="USDA API returned an invalid JSON document.",
                type_=problem_type_uri(request, "bad-gateway"),
            ),
        )

    foods_raw = data.get("foods", [])
    if not isinstance(foods_raw, list):
        foods_raw = []

    normalized: list[FoodItem] = []
    for item in foods_raw:
        if not isinstance(item, dict):
            continue

        nutrients = item.get("foodNutrients", [])
        if not isinstance(nutrients, list):
            nutrients = []

        normalized.append(
            FoodItem(
                fdcId=item.get("fdcId"),
                description=item.get("description"),
                brandName=item.get("brandName") or item.get("brandOwner"),
                servingSize=item.get("servingSize"),
                servingSizeUnit=item.get("servingSizeUnit"),
                calories=get_energy_kcal(nutrients),
                macros=Macros(
                    protein_g=get_nutrient_grams(nutrients, ["1003", "Protein"]),
                    carbs_g=get_nutrient_grams(
                        nutrients,
                        ["1005", "Carbohydrate, by difference", "Carbohydrate"],
                    ),
                    fat_g=get_nutrient_grams(
                        nutrients,
                        ["1004", "Total lipid (fat)", "Total Fat"],
                    ),
                ),
            )
        )

    return FoodsResponse(
        query=query_value,
        limit=limit,
        count=len(normalized),
        foods=normalized,
    )


def validate_food_type(request: Request, value: str) -> str:
    if not value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=problem_body(
                request,
                title="Invalid Food Type",
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Food type cannot be empty.",
                type_=problem_type_uri(request, "invalid-food-type"),
            ),
        )

    if len(value) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=problem_body(
                request,
                title="Invalid Food Type",
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Food type must be at least 2 characters long.",
                type_=problem_type_uri(request, "invalid-food-type"),
            ),
        )

    if not FOOD_TYPE_PATTERN.fullmatch(value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=problem_body(
                request,
                title="Invalid Food Type",
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Food type can only contain letters, numbers, spaces, "
                    "hyphens, and underscores."
                ),
                type_=problem_type_uri(request, "invalid-food-type"),
            ),
        )

    for pattern in PROBLEMATIC_PATTERNS:
        if pattern.fullmatch(value):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=problem_body(
                    request,
                    title="Invalid Food Type",
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid food type: '{value}'.",
                    type_=problem_type_uri(request, "invalid-food-type"),
                ),
            )

    return value


def safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return None


def find_nutrient(
    nutrients: list[Any], ids_or_names: list[str]
) -> dict[str, Any] | None:
    wanted_numbers = {str(x).strip() for x in ids_or_names}
    wanted_names = {str(x).strip().lower() for x in ids_or_names}

    for nutrient in nutrients:
        if not isinstance(nutrient, dict):
            continue

        number = str(
            nutrient.get("nutrientNumber") or nutrient.get("number") or ""
        ).strip()
        name = (
            str(nutrient.get("nutrientName") or nutrient.get("name") or "")
            .strip()
            .lower()
        )

        if number in wanted_numbers or name in wanted_names:
            return nutrient

    return None


def get_energy_kcal(nutrients: list[Any]) -> float | None:
    match = find_nutrient(nutrients, ["1008", "Energy"])
    if not match:
        return None

    unit = str(match.get("unitName") or match.get("unit") or "").lower()
    raw_value = match.get("value")
    if raw_value is None:
        return None

    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return None

    if unit == "kj":
        return round(value / 4.184, 1)

    return round(value, 1)


def get_nutrient_grams(nutrients: list[Any], ids_or_names: list[str]) -> float | None:
    match = find_nutrient(nutrients, ids_or_names)
    if not match:
        return None

    unit = str(match.get("unitName") or match.get("unit") or "").lower()
    raw_value = match.get("value")
    if raw_value is None:
        return None

    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return None

    if unit == "mg":
        return round(value / 1000, 2)

    return round(value, 2)
