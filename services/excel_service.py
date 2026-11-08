"""Excel 文件读取、预览、字段识别与校验分析。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from pymongo.database import Database

from database.repositories.batch_repository import BatchRepository
from database.repositories.customer_repository import CustomerRepository
from database.repositories.delivery_repository import DeliveryRepository
from database.repositories.order_repository import OrderRepository
from database.repositories.product_repository import ProductRepository
from utils.excel_utils import list_sheets, preview_dataframe, read_dataframe
from utils.errors import DataValidationError
from utils.field_definitions import IMPORT_SCHEMAS, auto_map_columns, schema_for
from utils.file_utils import file_sha256, validate_upload
from utils.phone_utils import code_key
from utils.validator import ValidationResult, validate_dataframe


_batches = BatchRepository()
_customers = CustomerRepository()
_products = ProductRepository()
_orders = OrderRepository()
_deliveries = DeliveryRepository()


@dataclass
class ImportAnalysis:
    import_type: str
    filename: str
    sheet_name: str
    mapping: dict[str, str]
    dataframe: pd.DataFrame
    validation: ValidationResult
    file_hash: str
    duplicate_batches: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    existing_count: int = 0

    @property
    def preview(self) -> pd.DataFrame:
        return preview_dataframe(self.dataframe, rows=20)

    @property
    def valid_rows(self) -> list[dict[str, Any]]:
        return self.validation.valid_rows

    @property
    def error_dataframe(self) -> pd.DataFrame:
        return self.validation.error_dataframe


def list_file_sheets(content: bytes, filename: str) -> list[tuple[str, int, int]]:
    return list_sheets(content, filename)


def auto_detect_mapping(columns: list[str], import_type: str) -> dict[str, str]:
    return auto_map_columns(columns, import_type)


def _database_duplicate_count(db: Database | None, import_type: str, rows: list[dict[str, Any]], tenant_id: str) -> int:
    if db is None or import_type not in {"customer", "product", "order", "delivery", "payment"}:
        return 0
    count = 0
    seen: set[str] = set()
    for row in rows:
        key = ""
        if import_type == "customer" and row.get("customer_code"):
            key = f"c:{code_key(row['customer_code'])}"
            exists = bool(_customers.find_by_code_key(db, code_key(row["customer_code"]), tenant_id))
        elif import_type == "product" and row.get("product_code"):
            key = f"p:{code_key(row['product_code'])}"
            exists = bool(_products.find_by_code_key(db, code_key(row["product_code"]), tenant_id))
        elif import_type == "order" and row.get("order_no"):
            key = f"o:{row['order_no']}"
            exists = bool(_orders.find_by_order_no(db, row["order_no"], tenant_id))
        elif import_type == "delivery" and row.get("delivery_no"):
            key = f"d:{row['delivery_no']}"
            exists = bool(_deliveries.find_by_delivery_no(db, row["delivery_no"], tenant_id))
        elif import_type == "payment" and row.get("payment_no"):
            key = f"pm:{row['payment_no']}"
            exists = bool(db["payment_records"].find_one({"tenant_id": tenant_id, "payment_no": row["payment_no"]}))
        else:
            continue
        if key and key not in seen:
            seen.add(key)
            if exists:
                count += 1
    return count


def analyze_file(
    db: Database | None,
    content: bytes,
    filename: str,
    import_type: str,
    *,
    sheet_name: str | int | None = None,
    mapping: dict[str, str] | None = None,
    tenant_id: str = "default",
    header_row: int | None = None,
) -> ImportAnalysis:
    validate_upload(filename, len(content))
    schema = schema_for(import_type)
    df = read_dataframe(
        content,
        filename,
        sheet_name=sheet_name,
        import_type=import_type,
        header_row=header_row,
    )
    if df.empty:
        raise DataValidationError("所选 Sheet 没有可导入的数据，请检查文件内容或更换 Sheet。")
    detected = auto_detect_mapping([str(column) for column in df.columns], import_type)
    final_mapping = {key: value for key, value in (mapping or detected).items() if value}
    if not final_mapping:
        final_mapping = detected
    validation = validate_dataframe(df, import_type, final_mapping, row_offset=2)
    file_hash = file_sha256(content)
    duplicate_batches = _batches.find_by_hash(db, file_hash, import_type, tenant_id) if db is not None else []
    warnings: list[str] = []
    if duplicate_batches:
        warnings.append(
            f"检测到该文件曾导入过 {len(duplicate_batches)} 次，请选择跳过、重新导入或取消。"
        )
    existing_count = _database_duplicate_count(db, import_type, validation.valid_rows, tenant_id)
    if existing_count:
        warnings.append(f"数据库已存在 {existing_count} 条相同业务编号的记录，导入时将按规则跳过或更新。")
    missing_required = [field.label for field in schema.required_fields if not final_mapping.get(field.key)]
    if missing_required:
        warnings.append("以下必填字段尚未映射：" + "、".join(missing_required))
    return ImportAnalysis(
        import_type=import_type,
        filename=filename,
        sheet_name=str(sheet_name if sheet_name is not None else "CSV数据"),
        mapping=final_mapping,
        dataframe=df,
        validation=validation,
        file_hash=file_hash,
        duplicate_batches=duplicate_batches,
        warnings=warnings,
        existing_count=existing_count,
    )


def template_dataframe(import_type: str) -> pd.DataFrame:
    schema = schema_for(import_type)
    return pd.DataFrame([{field.label: field.example for field in schema.fields}])


def schema_columns(import_type: str) -> list[tuple[str, str, bool]]:
    schema = schema_for(import_type)
    return [(field.key, field.label, field.required) for field in schema.fields]


def mapping_preview(mapping: dict[str, str], import_type: str) -> pd.DataFrame:
    schema = schema_for(import_type)
    rows = []
    for field in schema.fields:
        rows.append(
            {
                "系统字段": field.label,
                "字段代码": field.key,
                "是否必填": "是" if field.required else "否",
                "映射到的 Excel 列": mapping.get(field.key, "（未映射）"),
            }
        )
    return pd.DataFrame(rows, columns=["系统字段", "字段代码", "是否必填", "映射到的 Excel 列"])

