from fastapi import HTTPException, Request, status

from app.problem import problem_body, problem_type_uri
from app.settings import Settings


def enforce_trusted_caller(request: Request, cfg: Settings) -> None:
    if not cfg.rapidapi_proxy_secret and not cfg.internal_app_token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=problem_body(
                request,
                title="Configuration Error",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Trusted caller credentials are not configured.",
                type_=problem_type_uri(request, "configuration-error"),
            ),
        )

    proxy_secret = request.headers.get("X-RapidAPI-Proxy-Secret")
    auth = request.headers.get("Authorization")

    rapid_ok = bool(
        cfg.rapidapi_proxy_secret and proxy_secret == cfg.rapidapi_proxy_secret
    )

    internal_ok = bool(
        cfg.internal_app_token and auth == f"Bearer {cfg.internal_app_token}"
    )

    if rapid_ok or internal_ok:
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=problem_body(
            request,
            title="Forbidden",
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Request is not from a trusted caller.",
            type_=problem_type_uri(request, "forbidden"),
        ),
    )
