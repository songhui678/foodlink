"""Excel 行级校验与标准化。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pandas as pd

from utils.decimal_utils import round_money, round_qty, to_decimal
from utils.errors import ImportValidationError
from utils.field_definitions import FieldSpec, ImportSchema, schema_for
from utils.phone_utils import is_valid_phone, normalize_phone, to_text
from utils.string_utils import is_blank, normalize_name, normalize_spec


@dataclass
class ValidationResult:
    import_type: str
    total_rows: int = 0
    rows: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def valid_rows(self) -> list[dict[str, Any]]:
        return [row for row in self.rows if row.get("__valid__")]

    @property
    def invalid_rows(self) -> list[dict[str, Any]]:
        return [row for row in self.rows if not row.get("__valid__")]

    @property
    def valid_count(self) -> int:
        return len(self.valid_rows)

    @property
    def error_count(self) -> int:
        return len({error.get("row_no") for error in self.errors})

    @property
    def error_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "行号": error.get("row_no", ""),
                    "字段": error.get("field_label", ""),
                    "错误原因": error.get("reason", ""),
                    "原始数据": error.get("raw", ""),
                }
                for error in self.errors
            ],
            columns=["行号", "字段", "错误原因", "原始数据"],
        )


def parse_date(value: Any) -> date | None:
    if value is None or is_blank(value):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime().date()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        if 20000 <= number <= 80000:  # Excel 日期序列号
            try:
                return (datetime(1899, 12, 30) + timedelta(days=number)).date()
            except Exception:
                return None
        text_number = str(int(number)) if number.is_integer() else str(number)
        if re.fullmatch(r"\d{8}", text_number):
            value = text_number
    text = to_text(value).strip()
    if not text:
        return None
    text = text.replace("年", "-").replace("月", "-").replace("日", "")
    text = text.replace("/", "-").replace(".", "-")
    text = re.sub(r"\s+.*$", "", text)
    if re.fullmatch(r"\d{8}", text):
        text = f"{text[:4]}-{text[4:6]}-{text[6:]}"
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return None
    try:
        return parsed.date()
    except Exception:
        return None


def format_date(value: Any) -> str:
    parsed = parse_date(value)
    return parsed.isoformat() if parsed else ""


def _convert_field(field: FieldSpec, raw_value: Any) -> tuple[Any, str | None]:
    if field.kind == "code":
        return to_text(raw_value).strip(), None
    if field.kind == "phone":
        text = to_text(raw_value)
        phone = normalize_phone(raw_value)
        if text and not phone:
            return "", "手机号格式不正确"
        if phone and not is_valid_phone(phone):
            return phone, "手机号格式不正确（应为 11 位手机号或带区号座机）"
        return phone, None
    if field.kind == "date":
        text = to_text(raw_value)
        parsed = parse_date(raw_value)
        if text and parsed is None:
            return "", "日期格式无法识别，请使用 2026-01-15 或 2026/01/15"
        return parsed, None
    if field.kind == "money":
        text = to_text(raw_value)
        if not text:
            return None, None
        if not re.fullmatch(r"[\s\d,，.￥¥元\-+()]*", text):
            return None, "金额格式不正确"
        amount = to_decimal(text, default=Decimal("-1"))
        if amount < 0 and not (text.strip().startswith("(") and text.strip().endswith(")")):
            return amount, "金额不能为负数"
        return amount, None
    if field.kind == "number":
        text = to_text(raw_value)
        if not text:
            return None, None
        value_decimal = to_decimal(text, default=Decimal("-1"))
        if value_decimal < 0:
            return value_decimal, "数量不能为负数"
        return value_decimal, None
    return to_text(raw_value).strip(), None


def _raw_snapshot(row: pd.Series) -> str:
    data = {str(key): to_text(value) for key, value in row.to_dict().items()}
    return json.dumps(data, ensure_ascii=False, default=str)[:2000]


def _duplicate_keys(row: dict[str, Any], import_type: str) -> list[str]:
    if import_type == "customer":
        keys = []
        if row.get("customer_code"):
            keys.append("code:" + row["customer_code"].upper())
        if row.get("phone"):
            keys.append("phone:" + row["phone"])
        return keys
    if import_type == "product":
        keys = []
        if row.get("product_code"):
            keys.append("code:" + row["product_code"].upper())
        if row.get("product_name"):
            keys.append(
                "name_spec:"
                + normalize_name(row["product_name"])
                + "|"
                + normalize_spec(row.get("specification", ""))
            )
        return keys
    if import_type == "order":
        product_identity = row.get("product_code") or (
            normalize_name(row.get("product_name", ""))
            + "|"
            + normalize_spec(row.get("specification", ""))
        )
        return [f"order_item:{row.get('order_no','')}|{str(product_identity).upper()}"]
    if import_type == "delivery":
        return [f"delivery:{row.get('delivery_no','')}"]
    if import_type == "payment":
        return [f"payment:{row.get('payment_no','')}"]
    return []


def validate_dataframe(
    df: pd.DataFrame,
    import_type: str,
    mapping: dict[str, str | None],
    *,
    row_offset: int = 2,
) -> ValidationResult:
    schema = schema_for(import_type)
    required = {field.key: field for field in schema.required_fields}
    for key, field in required.items():
        column = mapping.get(key)
        if not column:
            raise ImportValidationError(f"未找到{field.label}字段，请检查 Excel 字段映射。")
        if column not in df.columns:
            raise ImportValidationError(
                f"Excel 中不存在“{column}”列，无法映射到{field.label}，请重新选择。"
            )

    result = ValidationResult(import_type=import_type, total_rows=len(df))
    seen_keys: dict[str, int] = {}
    for index, row in df.iterrows():
        row_no = int(index) + row_offset
        record: dict[str, Any] = {"__row_no__": row_no, "__raw__": _raw_snapshot(row), "__valid__": True}
        row_errors: list[tuple[str, str]] = []

        for field in schema.fields:
            column = mapping.get(field.key)
            raw_value = row.get(column) if column else None
            value, error = _convert_field(field, raw_value)
            record[field.key] = value
            if error:
                row_errors.append((field.label, error))
            if field.required and (value is None or value == "" or value == []):
                row_errors.append((field.label, "必填字段为空"))

        _validate_custom_rules(record, import_type, row_errors)

        keys = _duplicate_keys(record, import_type)
        for key in keys:
            if key in seen_keys:
                row_errors.append(("重复记录", f"与第 {seen_keys[key]} 行重复"))
                break
        for key in keys:
            seen_keys.setdefault(key, row_no)

        if row_errors:
            record["__valid__"] = False
            record["__errors__"] = [f"{field}：{reason}" for field, reason in row_errors]
            for field, reason in row_errors:
                result.errors.append(
                    {
                        "row_no": row_no,
                        "field": field,
                        "field_label": field,
                        "reason": reason,
                        "raw": record["__raw__"],
                    }
                )

        if import_type == "order":
            _calculate_order_line(record)
        result.rows.append(record)

    return result


def _validate_custom_rules(record: dict[str, Any], import_type: str, errors: list[tuple[str, str]]) -> None:
    if import_type == "customer":
        if not record.get("customer_name"):
            errors.append(("客户名称", "客户名称不能为空"))
        if not any(record.get(key) for key in ("customer_code", "phone", "customer_name")):
            errors.append(("客户标识", "客户编码、手机号和名称至少填写一项"))
    elif import_type == "product":
        if not record.get("product_name"):
            errors.append(("商品名称", "商品名称不能为空"))
        if not record.get("product_code") and not record.get("specification"):
            errors.append(("商品标识", "商品编码与规格至少填写一项，避免同名商品误合并"))
    elif import_type == "order":
        if not record.get("customer_code") and not record.get("customer_name"):
            errors.append(("客户信息", "客户编码和客户名称至少填写一项"))
        if not record.get("product_code") and not record.get("product_name"):
            errors.append(("商品信息", "商品编码和商品名称至少填写一项"))
        quantity = record.get("quantity")
        if quantity is not None and quantity <= 0:
            errors.append(("订单数量", "订单数量必须大于 0"))
        if record.get("unit_price") is None and record.get("amount") is None:
            errors.append(("金额", "单价和金额至少填写一项"))
    elif import_type == "delivery":
        quantity = record.get("quantity")
        if quantity is not None and quantity <= 0:
            errors.append(("发货数量", "发货数量必须大于 0"))
    elif import_type == "payment":
        amount = record.get("amount")
        if amount is not None and amount <= 0:
            errors.append(("回款金额", "回款金额必须大于 0"))


def _calculate_order_line(record: dict[str, Any]) -> None:
    quantity = to_decimal(record.get("quantity"))
    unit_price = to_decimal(record.get("unit_price"))
    amount = record.get("amount")
    if amount is None and quantity and unit_price:
        amount = round_money(quantity * unit_price)
        record["amount"] = amount
    if amount is not None and quantity and unit_price:
        expected = round_money(quantity * unit_price)
        if abs(to_decimal(amount) - expected) > Decimal("0.01"):
            record["__amount_mismatch__"] = True
            record["__expected_amount__"] = expected
    record["quantity"] = round_qty(quantity) if quantity is not None else None

