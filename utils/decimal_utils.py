"""金额与数量精度工具。

业务金额统一使用 Decimal 计算，写入 MongoDB 时使用 Decimal128，
读取时再转换成 Decimal，禁止使用浮点数做金额累加。
"""

from __future__ import annotations

import math
import re
import unicodedata
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from typing import Any

try:
    from bson.decimal128 import Decimal128
except Exception:  # pragma: no cover
    Decimal128 = None  # type: ignore


ZERO = Decimal("0")
MONEY_QUANT = Decimal("0.01")
QTY_QUANT = Decimal("0.0001")


def to_decimal(value: Any, default: Decimal | None = None) -> Decimal:
    """把 Excel/数据库/字符串值安全转换为 Decimal。"""

    if value is None:
        return default if default is not None else ZERO
    if Decimal128 is not None and isinstance(value, Decimal128):
        try:
            return value.to_decimal()
        except Exception:
            return default if default is not None else ZERO
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return Decimal(int(value))
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return default if default is not None else ZERO
        return Decimal(str(value))

    text = unicodedata.normalize("NFKC", str(value)).strip()
    if not text or text.lower() in {"nan", "none", "null", "-", "--", "无"}:
        return default if default is not None else ZERO

    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    text = (
        text.replace(",", "")
        .replace("，", "")
        .replace("￥", "")
        .replace("¥", "")
        .replace("元", "")
        .replace(" ", "")
        .replace("\u00a0", "")
    )
    text = re.sub(r"[^0-9eE+\-.]", "", text)
    if text in {"", ".", "-", "+"}:
        return default if default is not None else ZERO
    try:
        with localcontext() as ctx:
            ctx.prec = 38
            result = Decimal(text)
        return -result if negative else result
    except (InvalidOperation, ValueError):
        return default if default is not None else ZERO


def to_decimal128(value: Any) -> Any:
    amount = to_decimal(value)
    if Decimal128 is None:
        return str(amount)
    try:
        return Decimal128(amount)
    except Exception:
        return Decimal128(ZERO)


def from_db_decimal(value: Any) -> Decimal:
    if value is None:
        return ZERO
    if isinstance(value, Decimal128):
        return value.to_decimal()
    return to_decimal(value)


def round_money(value: Any) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = 38
        return to_decimal(value).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def round_qty(value: Any) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = 38
        return to_decimal(value).quantize(QTY_QUANT, rounding=ROUND_HALF_UP)


def money_str(value: Any) -> str:
    return f"{round_money(value):,.2f}"


def qty_str(value: Any) -> str:
    number = round_qty(value)
    text = format(number.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def decimal_to_float(value: Any) -> float:
    return float(to_decimal(value))


def amounts_equal(left: Any, right: Any, tolerance: Decimal | str = "0.01") -> bool:
    return abs(to_decimal(left) - to_decimal(right)) <= to_decimal(tolerance)


def safe_sum(values: Any) -> Decimal:
    total = ZERO
    for value in values:
        total += to_decimal(value)
    return total

