from __future__ import annotations

from pydantic import BaseModel


class Macros(BaseModel):
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None


class FoodItem(BaseModel):
    fdc_Id: int | None = None
    description: str | None = None
    brand_name: str | None = None
    serving_size: float | None = None
    serving_size_unit: str | None = None
    calories: float | None = None
    macros: Macros


class FoodsResponse(BaseModel):
    query: str
    limit: int
    count: int
    foods: list[FoodItem]
