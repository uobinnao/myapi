from collections.abc import Mapping
from datetime import datetime, timezone
from http import HTTPStatus
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from app.schema import ProblemDetail


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
