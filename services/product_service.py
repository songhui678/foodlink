"""商品资料管理。"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pandas as pd
from pymongo.database import Database

from database.repositories.log_repository import LogRepository
from database.repositories.product_repository import ProductRepository
from database.repositories.base import display_doc
from models.product import ProductCreate, ProductUpdate
from utils.decimal_utils import round_money, to_decimal128
from utils.errors import DataValidationError
from utils.phone_utils import code_key
from utils.string_utils import normalize_name, normalize_spec


_repo = ProductRepository()
_logs = LogRepository()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _base_doc(record: dict[str, Any], tenant_id: str = "default", source: str = "manual") -> dict[str, Any]:
    now = _now()
    price = round_money(record.get("price", 0))
    return {
        "tenant_id": tenant_id,
        "product_code": str(record.get("product_code") or "").strip(),
        "product_name": str(record.get("product_name") or "").strip(),
        "specification": str(record.get("specification") or "").strip(),
        "unit": str(record.get("unit") or "").strip(),
        "category": str(record.get("category") or "").strip(),
        "price": to_decimal128(price),
        "source": source,
        "product_code_key": code_key(record.get("product_code")),
        "product_name_key": normalize_name(record.get("product_name")),
        "spec_key": normalize_spec(record.get("specification")),
        "is_deleted": False,
        "is_demo": bool(record.get("is_demo", False)),
        "created_at": now,
        "updated_at": now,
    }


def create_product(
    db: Database,
    record: dict[str, Any],
    *,
    tenant_id: str = "default",
    source: str = "manual",
    allow_duplicate_code: bool = False,
    allow_duplicate_identity: bool = False,
) -> dict[str, Any]:
    try:
        validated = ProductCreate(tenant_id=tenant_id, source=source, **record)
    except Exception as exc:
        from utils.errors import friendly_error

        raise DataValidationError(f"商品资料校验失败：{friendly_error(exc)}") from exc
    data = validated.model_dump()
    data.update(record)
    doc = _base_doc(data, tenant_id=tenant_id, source=source)
    if not doc["product_name"]:
        raise DataValidationError("商品名称不能为空。")
    if round_money(record.get("price", 0)) < 0:
        raise DataValidationError("商品价格不能为负数。")
    if doc["product_code_key"] and not allow_duplicate_code:
        existing = _repo.find_by_code_key(db, doc["product_code_key"], tenant_id)
        if existing:
            raise DataValidationError(f"商品编码“{doc['product_code']}”已存在，请勿重复创建。")
    # 名称 + 规格完全相同视为重复；规格不同则允许创建为不同商品
    if doc["product_name_key"] and doc["spec_key"] and not allow_duplicate_identity:
        existing = _repo.find_by_name_spec(db, doc["product_name_key"], doc["spec_key"], tenant_id)
        if existing:
            raise DataValidationError("相同商品名称和规格的商品已存在，请勿重复创建。")
    result = _repo.insert_one(db, doc)
    _logs.add_audit_log(db, "新增商品", {"product_code": doc["product_code"], "product_name": doc["product_name"]}, tenant_id)
    return display_doc({**doc, "_id": result.inserted_id})


def import_product_document(
    db: Database,
    record: dict[str, Any],
    *,
    batch_id: str,
    tenant_id: str = "default",
    update_existing: bool = False,
) -> tuple[str, str]:
    doc = _base_doc(record, tenant_id=tenant_id, source="excel_import")
    doc["import_batch_id"] = batch_id
    doc["raw_data"] = record.get("__raw__", "")
    if not doc["product_name"]:
        return "skipped", "商品名称为空"

    if doc["product_code_key"]:
        existing = _repo.find_by_code_key(db, doc["product_code_key"], tenant_id)
        if existing:
            if len(existing) > 1:
                return "duplicate", f"商品编码对应 {len(existing)} 条商品记录，需人工处理"
            if update_existing:
                target = existing[0]
                update = {
                    key: doc[key]
                    for key in ("product_name", "specification", "unit", "category", "price",
                                "product_name_key", "spec_key", "updated_at")
                }
                _repo.update(db, target["id"], update)
                return "updated", "按商品编码更新"
            return "skipped", "商品编码已存在，已跳过"

    if doc["product_name_key"]:
        same_name_spec = _repo.find_by_name_spec(db, doc["product_name_key"], doc["spec_key"], tenant_id)
        if same_name_spec:
            return "duplicate", "相同名称和规格的商品已存在，已跳过"
    result = _repo.insert_one(db, doc)
    return "inserted", str(result.inserted_id)


def update_product(db: Database, product_id: str, changes: dict[str, Any], *, tenant_id: str = "default") -> bool:
    current = _repo.get(db, product_id)
    if not current:
        raise DataValidationError("商品不存在或已被删除。")
    try:
        validated = ProductUpdate(**changes)
    except Exception as exc:
        from utils.errors import friendly_error

        raise DataValidationError(f"商品资料校验失败：{friendly_error(exc)}") from exc
    update = {key: value for key, value in validated.model_dump(exclude_none=True).items()}
    if "product_name" in update:
        update["product_name_key"] = normalize_name(update["product_name"])
    if "specification" in update:
        update["spec_key"] = normalize_spec(update["specification"])
    if "product_code" in update:
        new_key = code_key(update["product_code"])
        existing = _repo.find_by_code_key(db, new_key, tenant_id)
        if any(item["id"] != product_id for item in existing):
            raise DataValidationError("修改后的商品编码已被其他商品使用。")
        update["product_code_key"] = new_key
    if "price" in update:
        update["price"] = to_decimal128(round_money(update["price"]))
    update["updated_at"] = _now()
    ok = _repo.update(db, product_id, update)
    if ok:
        _logs.add_audit_log(db, "编辑商品", {"product_id": product_id, "fields": list(update)}, tenant_id)
    return ok


def soft_delete_product(db: Database, product_id: str, *, tenant_id: str = "default") -> bool:
    current = _repo.get(db, product_id)
    if not current:
        return False
    ok = _repo.update(db, product_id, {"is_deleted": True, "deleted_at": _now(), "updated_at": _now()})
    if ok:
        _logs.add_audit_log(db, "删除商品（软删除）", {"product_id": product_id, "product_name": current.get("product_name")}, tenant_id)
    return ok


def restore_product(db: Database, product_id: str, *, tenant_id: str = "default") -> bool:
    ok = _repo.update(db, product_id, {"is_deleted": False, "deleted_at": None, "updated_at": _now()})
    if ok:
        _logs.add_audit_log(db, "恢复商品", {"product_id": product_id}, tenant_id)
    return ok


def get_product(db: Database, product_id: str) -> dict[str, Any] | None:
    return _repo.get(db, product_id)


def list_products(db: Database, **filters) -> list[dict[str, Any]]:
    return _repo.list(db, **filters)


def count_products(db: Database, tenant_id: str = "default", include_deleted: bool = False) -> int:
    query = {"tenant_id": tenant_id}
    if not include_deleted:
        query["is_deleted"] = {"$ne": True}
    return _repo.count(db, query)


def list_categories(db: Database, tenant_id: str = "default") -> list[str]:
    return _repo.categories(db, tenant_id)


def product_dataframe(products: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for item in products:
        from utils.decimal_utils import from_db_decimal

        rows.append(
            {
                "商品编码": item.get("product_code", ""),
                "商品名称": item.get("product_name", ""),
                "商品规格": item.get("specification", ""),
                "商品单位": item.get("unit", ""),
                "商品分类": item.get("category", ""),
                "商品价格": from_db_decimal(item.get("price")),
                "来源": item.get("source", ""),
                "是否删除": "是" if item.get("is_deleted") else "否",
                "创建时间": item.get("created_at", ""),
            }
        )
    return pd.DataFrame(
        rows,
        columns=["商品编码", "商品名称", "商品规格", "商品单位", "商品分类", "商品价格", "来源", "是否删除", "创建时间"],
    )


def duplicate_product_groups(db: Database, tenant_id: str = "default") -> pd.DataFrame:
    products = _repo.all_active(db, tenant_id)
    groups: list[dict[str, Any]] = []
    for field, label in (("product_code_key", "商品编码"), ("product_name_key", "商品名称")):
        buckets: dict[str, list[dict[str, Any]]] = {}
        for item in products:
            value = item.get(field) or ""
            if value:
                buckets.setdefault(str(value), []).append(item)
        for value, items in buckets.items():
            if len(items) > 1:
                groups.append(
                    {
                        "重复字段": label,
                        "重复值": value,
                        "商品数量": len(items),
                        "商品": "；".join(
                            f"{item.get('product_name','')} / {item.get('specification','') or '无规格'}"
                            for item in items
                        ),
                    }
                )
    return pd.DataFrame(groups, columns=["重复字段", "重复值", "商品数量", "商品"])


def product_options(db: Database, tenant_id: str = "default") -> list[dict[str, Any]]:
    return _repo.all_active(db, tenant_id)

