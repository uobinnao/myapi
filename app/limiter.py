from fastapi import Request
from slowapi import Limiter


def _first_forwarded_for(value: str | None) -> str:
    if not value:
        return "unknown"
    return value.split(",", 1)[0].strip() or "unknown"


def rapidapi_backend_key_func(request: Request) -> str:
    rapid_user = request.headers.get("X-RapidAPI-User")
    if rapid_user:
        return f"rapid-user:{rapid_user}"

    forwarded_for = request.headers.get("X-Forwarded-For")
    return f"ip:{_first_forwarded_for(forwarded_for)}"


limiter = Limiter(
    key_func=rapidapi_backend_key_func,
    headers_enabled=False,
)
