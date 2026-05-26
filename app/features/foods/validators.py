import re

from fastapi import HTTPException, Request, status

from app.problem import problem_body, problem_type_uri

FOOD_TYPE_PATTERN = re.compile(r"^[a-zA-Z0-9\s\-_]+$")

PROBLEMATIC_PATTERNS = [
    re.compile(r"^\d+$"),
    re.compile(r"^[^\w\s]+$"),
    re.compile(r"^(test|debug|admin|system)$", re.IGNORECASE),
]


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
