"""订单数据模型。"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import Field

from models.common import FoodLinkBaseModel, TenantModel, utcnow


class OrderItemIn(FoodLinkBaseModel):
    product_id: str = ""
    product_code: str = ""
    product_name: str = ""
    specification: str = ""
    unit: str = ""
    quantity: Decimal = Decimal("0")
    unit_price: Decimal = Decimal("0")
    amount: Decimal = Decimal("0")


class OrderCreate(TenantModel):
    order_no: str = Field(min_length=1)
    customer_id: str = ""
    customer_code: str = ""
    customer_name: str = ""
    order_date: date
    status: str = "正常"
    import_batch_id: str = ""
    items: list[OrderItemIn] = Field(default_factory=list)


class OrderOut(OrderCreate):
    id: str = ""
    total_quantity: Decimal = Decimal("0")
    total_amount: Decimal = Decimal("0")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

