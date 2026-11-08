"""客户资料管理。"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pandas as pd
from pymongo.database import Database

from database.repositories.customer_repository import CustomerRepository
from database.repositories.base import display_doc
from database.repositories.log_repository import LogRepository
from models.customer import CustomerCreate, CustomerUpdate
from utils.errors import DataValidationError
from utils.phone_utils import code_key, is_valid_phone, mask_phone, normalize_phone
from utils.string_utils import normalize_name


_repo = CustomerRepository()
_logs = LogRepository()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _base_doc(record: dict[str, Any], tenant_id: str = "default", source: str = "manual") -> dict[str, Any]:
    now = _now()
    return {
        "tenant_id": tenant_id,
        "customer_code": str(record.get("customer_code") or "").strip(),
        "customer_name": str(record.get("customer_name") or "").strip(),
        "contact": str(record.get("contact") or "").strip(),
        "phone": normalize_phone(record.get("phone")),
        "region": str(record.get("region") or "").strip(),
        "address": str(record.get("address") or "").strip(),
        "source": source,
        "customer_code_key": code_key(record.get("customer_code")),
        "customer_name_key": normalize_name(record.get("customer_name")),
        "is_deleted": False,
        "is_demo": bool(record.get("is_demo", False)),
        "created_at": now,
        "updated_at": now,
    }


def create_customer(
    db: Database,
    record: dict[str, Any],
    *,
    tenant_id: str = "default",
    source: str = "manual",
    allow_duplicate_code: bool = False,
) -> dict[str, Any]:
    try:
        validated = CustomerCreate(tenant_id=tenant_id, source=source, **record)
    except Exception as exc:
        from utils.errors import friendly_error

        raise DataValidationError(f"客户资料校验失败：{friendly_error(exc)}") from exc
    data = validated.model_dump()
    data.update(record)
    doc = _base_doc(data, tenant_id=tenant_id, source=source)
    if not doc["customer_name"]:
        raise DataValidationError("客户名称不能为空。")
    if doc["phone"] and not is_valid_phone(doc["phone"]):
        raise DataValidationError("手机号格式不正确，请填写 11 位手机号或带区号的座机号码。")
    code_key_value = doc["customer_code_key"]
    if code_key_value and not allow_duplicate_code:
        existing = _repo.find_by_code_key(db, code_key_value, tenant_id)
        if existing:
            raise DataValidationError(
                f"客户编码“{doc['customer_code']}”已存在，请勿重复创建。可改为编辑现有客户。"
            )
    result = _repo.insert_one(db, doc)
    doc["_id"] = result.inserted_id
    _logs.add_audit_log(db, "新增客户", {"customer_code": doc["customer_code"], "customer_name": doc["customer_name"]}, tenant_id)
    return display_doc({**doc, "_id": result.inserted_id})


def import_customer_document(
    db: Database,
    record: dict[str, Any],
    *,
    batch_id: str,
    tenant_id: str = "default",
    update_existing: bool = False,
) -> tuple[str, str]:
    """导入单条客户。返回 (状态, 说明)。状态：inserted/updated/skipped/duplicate。"""

    doc = _base_doc(record, tenant_id=tenant_id, source="excel_import")
    doc["import_batch_id"] = batch_id
    doc["raw_data"] = record.get("__raw__", "")
    if not doc["customer_name"]:
        return "skipped", "客户名称为空"

    if doc["customer_code_key"]:
        existing = _repo.find_by_code_key(db, doc["customer_code_key"], tenant_id)
        if existing:
            if len(existing) > 1:
                return "duplicate", f"客户编码对应 {len(existing)} 条客户记录，需人工处理"
            if update_existing:
                target = existing[0]
                update = {key: doc[key] for key in ("customer_name", "contact", "phone", "region", "address",
                                                    "customer_name_key", "updated_at")}
                _repo.update(db, target["id"], update)
                return "updated", "按客户编码更新"
            return "skipped", "客户编码已存在，已跳过"

    if doc["phone"]:
        same_phone = _repo.find_by_phone(db, doc["phone"], tenant_id)
        if len(same_phone) > 1:
            return "duplicate", f"手机号对应 {len(same_phone)} 条客户记录，已跳过，请人工核对"
        if len(same_phone) == 1:
            # 手机号相同不自动覆盖，交由人工确认
            return "duplicate", "手机号已存在，已跳过，请到客户匹配页人工确认"

    result = _repo.insert_one(db, doc)
    return "inserted", str(result.inserted_id)


def update_customer(db: Database, customer_id: str, changes: dict[str, Any], *, tenant_id: str = "default") -> bool:
    current = _repo.get(db, customer_id)
    if not current:
        raise DataValidationError("客户不存在或已被删除。")
    try:
        validated = CustomerUpdate(**changes)
    except Exception as exc:
        from utils.errors import friendly_error

        raise DataValidationError(f"客户资料校验失败：{friendly_error(exc)}") from exc
    update = {key: value for key, value in validated.model_dump(exclude_none=True).items()}
    if "customer_name" in update:
        update["customer_name_key"] = normalize_name(update["customer_name"])
    if "customer_code" in update:
        new_key = code_key(update["customer_code"])
        existing = _repo.find_by_code_key(db, new_key, tenant_id)
        if any(item["id"] != customer_id for item in existing):
            raise DataValidationError("修改后的客户编码已被其他客户使用。")
        update["customer_code_key"] = new_key
    if "phone" in update:
        update["phone"] = normalize_phone(update["phone"])
        if update["phone"] and not is_valid_phone(update["phone"]):
            raise DataValidationError("手机号格式不正确，请填写 11 位手机号或带区号的座机号码。")
    update["updated_at"] = _now()
    ok = _repo.update(db, customer_id, update)
    if ok:
        _logs.add_audit_log(db, "编辑客户", {"customer_id": customer_id, "fields": list(update)}, tenant_id)
    return ok


def soft_delete_customer(db: Database, customer_id: str, *, tenant_id: str = "default") -> bool:
    current = _repo.get(db, customer_id)
    if not current:
        return False
    ok = _repo.update(db, customer_id, {"is_deleted": True, "deleted_at": _now(), "updated_at": _now()})
    if ok:
        _logs.add_audit_log(db, "删除客户（软删除）", {"customer_id": customer_id, "customer_name": current.get("customer_name")}, tenant_id)
    return ok


def restore_customer(db: Database, customer_id: str, *, tenant_id: str = "default") -> bool:
    ok = _repo.update(db, customer_id, {"is_deleted": False, "deleted_at": None, "updated_at": _now()})
    if ok:
        _logs.add_audit_log(db, "恢复客户", {"customer_id": customer_id}, tenant_id)
    return ok


def get_customer(db: Database, customer_id: str) -> dict[str, Any] | None:
    return _repo.get(db, customer_id)


def list_customers(db: Database, **filters) -> list[dict[str, Any]]:
    return _repo.list(db, **filters)


def count_customers(db: Database, tenant_id: str = "default", include_deleted: bool = False) -> int:
    query = {"tenant_id": tenant_id}
    if not include_deleted:
        query["is_deleted"] = {"$ne": True}
    return _repo.count(db, query)


def list_regions(db: Database, tenant_id: str = "default") -> list[str]:
    return _repo.regions(db, tenant_id)


def customer_dataframe(customers: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for item in customers:
        rows.append(
            {
                "客户编码": item.get("customer_code", ""),
                "客户名称": item.get("customer_name", ""),
                "联系人": item.get("contact", ""),
                "手机号": item.get("phone", ""),
                "所属区域": item.get("region", ""),
                "详细地址": item.get("address", ""),
                "来源": item.get("source", ""),
                "是否删除": "是" if item.get("is_deleted") else "否",
                "创建时间": item.get("created_at", ""),
            }
        )
    return pd.DataFrame(
        rows,
        columns=["客户编码", "客户名称", "联系人", "手机号", "所属区域", "详细地址", "来源", "是否删除", "创建时间"],
    )


def duplicate_customer_groups(db: Database, tenant_id: str = "default") -> pd.DataFrame:
    customers = _repo.all_active(db, tenant_id)
    groups: list[dict[str, Any]] = []
    for field, label in (("customer_code_key", "客户编码"), ("phone", "手机号"), ("customer_name_key", "客户名称")):
        buckets: dict[str, list[dict[str, Any]]] = {}
        for item in customers:
            value = item.get(field) or ""
            if not value:
                continue
            if field == "phone" and len(str(value)) < 7:
                continue
            buckets.setdefault(str(value), []).append(item)
        for value, items in buckets.items():
            if len(items) > 1:
                groups.append(
                    {
                        "重复字段": label,
                        "重复值": mask_phone(value) if field == "phone" else value,
                        "客户数量": len(items),
                        "客户": "；".join(
                            f"{item.get('customer_name','')}({item.get('customer_code','') or '无编码'})"
                            for item in items
                        ),
                    }
                )
    return pd.DataFrame(groups, columns=["重复字段", "重复值", "客户数量", "客户"])


def customer_options(db: Database, tenant_id: str = "default") -> list[dict[str, Any]]:
    return _repo.all_active(db, tenant_id)

