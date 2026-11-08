"""常用模型与数据校验辅助。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import Field, field_validator

from models.common import FoodLinkBaseModel, TenantModel, utcnow


class MappingConfigIn(TenantModel):
    import_type: str
    name: str = "默认映射"
    mapping: dict[str, str] = Field(default_factory=dict)


class PaymentIn(TenantModel):
    payment_no: str
    customer_code: str = ""
    payment_date: date
    amount: Decimal = Decimal("0")
    remark: str = ""
    import_batch_id: str = ""

    @field_validator("amount", mode="before")
    @classmethod
    def _amount(cls, value: Any) -> Decimal:
        from utils.decimal_utils import to_decimal

        return to_decimal(value)


class SystemSettingIn(FoodLinkBaseModel):
    key: str
    value: Any = None

