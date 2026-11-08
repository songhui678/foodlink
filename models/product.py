"""商品数据模型。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import Field, field_validator

from models.common import FoodLinkBaseModel, TenantModel, optional_text, utcnow


class ProductBase(TenantModel):
    product_code: str = ""
    product_name: str = ""
    specification: str = ""
    unit: str = ""
    category: str = ""
    price: Decimal = Decimal("0")
    source: str = "manual"

    @field_validator("product_code", mode="before")
    @classmethod
    def _keep_code(cls, value: Any) -> str:
        return optional_text(value)

    @field_validator("price", mode="before")
    @classmethod
    def _price(cls, value: Any) -> Decimal:
        from utils.decimal_utils import to_decimal

        return to_decimal(value)


class ProductCreate(ProductBase):
    product_name: str = Field(min_length=1, description="商品名称")


class ProductUpdate(FoodLinkBaseModel):
    product_code: str | None = None
    product_name: str | None = None
    specification: str | None = None
    unit: str | None = None
    category: str | None = None
    price: Decimal | None = None

    @field_validator("price", mode="before")
    @classmethod
    def _price(cls, value: Any) -> Decimal | None:
        if value is None:
            return None
        from utils.decimal_utils import to_decimal

        return to_decimal(value)


class ProductOut(ProductBase):
    id: str = ""
    is_deleted: bool = False
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

