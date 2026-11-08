"""客户数据模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, field_validator

from models.common import FoodLinkBaseModel, TenantModel, optional_text, utcnow


class CustomerBase(TenantModel):
    customer_code: str = ""
    customer_name: str = ""
    contact: str = ""
    phone: str = ""
    region: str = ""
    address: str = ""
    source: str = "manual"

    @field_validator("customer_code", "phone", mode="before")
    @classmethod
    def _keep_text(cls, value: Any) -> str:
        return optional_text(value)


class CustomerCreate(CustomerBase):
    customer_name: str = Field(min_length=1, description="客户名称")


class CustomerUpdate(FoodLinkBaseModel):
    customer_code: str | None = None
    customer_name: str | None = None
    contact: str | None = None
    phone: str | None = None
    region: str | None = None
    address: str | None = None

    @field_validator("customer_code", "phone", mode="before")
    @classmethod
    def _keep_text(cls, value: Any) -> str | None:
        return None if value is None else optional_text(value)


class CustomerOut(CustomerBase):
    id: str = ""
    is_deleted: bool = False
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

