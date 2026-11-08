"""模型公共定义。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class FoodLinkBaseModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore", populate_by_name=True)


class TenantModel(FoodLinkBaseModel):
    tenant_id: str = "default"
    is_demo: bool = False

    @field_validator("tenant_id", mode="before")
    @classmethod
    def _tenant(cls, value: Any) -> str:
        return str(value or "default")


def optional_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()

