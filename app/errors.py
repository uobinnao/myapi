from datetime import datetime, timezone
from typing import Any

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.problem import (
    default_problem_slug,
    http_title,
    problem_response,
    problem_type_uri,
)


async def rate_limit_exceeded_handler(
    request: Request,
    _exc: Exception,
) -> JSONResponse:
    return problem_response(
        request,
        title="Too Many Requests",
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Rate limit exceeded. Please try again later.",
        type_=problem_type_uri(request, "too-many-requests"),
    )


async def request_validation_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)

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


async def http_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)

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


async def unhandled_exception_handler(
    request: Request,
    _exc: Exception,
) -> JSONResponse:
    return problem_response(
        request,
        title="Internal Server Error",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="An unexpected error occurred. Please try again later.",
        type_=problem_type_uri(request, "internal-server-error"),
    )
