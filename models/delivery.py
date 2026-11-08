"""发货记录数据模型。"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import Field

from models.common import FoodLinkBaseModel, TenantModel, utcnow


class DeliveryCreate(TenantModel):
    delivery_no: str = Field(min_length=1)
    order_no: str = Field(min_length=1)
    customer_code: str = ""
    product_code: str = ""
    delivery_date: date
    quantity: Decimal = Decimal("0")
    import_batch_id: str = ""


class DeliveryOut(DeliveryCreate):
    id: str = ""
    created_at: datetime = Field(default_factory=utcnow)

