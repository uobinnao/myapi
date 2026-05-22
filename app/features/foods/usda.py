from typing import Any

import httpx

from app.schema import FoodItem, Macros


def safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return None


def normalize_foods(data: dict[str, Any]) -> list[FoodItem]:
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

    return normalized


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
