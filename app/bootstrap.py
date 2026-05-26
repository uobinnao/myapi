from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exceptions import RequestValidationError

from app.errors import (
    http_exception_handler,
    rate_limit_exceeded_handler,
    request_validation_handler,
    unhandled_exception_handler,
)
from app.features.foods.route import router as foods_router
from app.features.meta.route import router as meta_router
from app.lifespan import lifespan
from app.limiter import limiter
from app.settings import get_settings


def create_app() -> FastAPI:
    settings = get_settings()

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

    app.state.limiter = limiter

    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.add_exception_handler(RequestValidationError, request_validation_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    app.include_router(meta_router)
    app.include_router(foods_router)

    return app
