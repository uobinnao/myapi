import httpx
from fastapi import HTTPException, Request, status

from app.features.foods.usda import normalize_foods, safe_json
from app.problem import problem_body, problem_type_uri
from app.schema import FoodsResponse
from app.settings import Settings
from app.state import AppState


async def search_foods_service(
    *,
    request: Request,
    cfg: Settings,
    state: AppState,
    query_value: str,
    limit: int,
) -> FoodsResponse:
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

    try:
        response_upstream = await state.http.get(
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

    if response_upstream.is_error:
        upstream_details = safe_json(response_upstream)

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

        mapped_status = (
            503
            if response_upstream.status_code >= 500
            else response_upstream.status_code
        )

        raise HTTPException(
            status_code=mapped_status,
            detail=problem_body(
                request,
                title="Upstream API Error",
                status_code=mapped_status,
                detail=message_map.get(
                    response_upstream.status_code,
                    "USDA API error occurred.",
                ),
                type_=problem_type_uri(request, "upstream-api-error"),
                upstream_status=response_upstream.status_code,
                upstream_details=upstream_details,
            ),
        )

    data = safe_json(response_upstream)

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

    normalized = normalize_foods(data)

    return FoodsResponse(
        query=query_value,
        limit=limit,
        count=len(normalized),
        foods=normalized,
    )
