from __future__ import annotations

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TimestampMixin


class FoodSearchLog(Base, TimestampMixin):
    __tablename__ = "food_search_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    query: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    limit: Mapped[int] = mapped_column(nullable=False)
    count: Mapped[int] = mapped_column(nullable=False)
    response_json: Mapped[dict] = mapped_column(JSON, nullable=False)
