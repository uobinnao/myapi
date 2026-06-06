from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from app.features.foods.service import search_foods_service
from app.features.foods.validators import validate_food_type
from app.limiter import limiter
from app.problem import PROBLEM_RESPONSES
from app.features.foods.schema import FoodsResponse
from app.security.rapidapi import enforce_trusted_caller
from app.settings import Settings, get_settings
from app.state import AppState, get_app_state

router = APIRouter(tags=["foods"])


@router.get(
    "/foods",
    summary="Search foods",
    description=(
        "Search USDA FoodData Central by food type and return normalized results. "
        "RapidAPI enforces public plan quotas/rate limits; this endpoint only "
        "keeps a small backend safety limit to protect the USDA upstream."
    ),
    response_description="Normalized food search results",
    response_model=FoodsResponse,
    responses=PROBLEM_RESPONSES,
)
@limiter.limit("5/second")
async def search_foods(
    request: Request,
    response: Response,
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
    enforce_trusted_caller(request, cfg)

    query_value = validate_food_type(request, food_type.strip())

    result = await search_foods_service(
        request=request,
        cfg=cfg,
        state=state,
        query_value=query_value,
        limit=limit,
    )

    response.headers["X-Upstream-Provider"] = "USDA"

    subscription = request.headers.get("X-RapidAPI-Subscription")
    if subscription:
        response.headers["X-RapidAPI-Subscription"] = subscription

    return result
