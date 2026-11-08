"""系统设置、数据库初始化与演示数据清理。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pymongo.database import Database

from database.indexes import ensure_indexes
from database.repositories.settings_repository import SettingsRepository
from utils.config import get_settings


_settings = SettingsRepository()

DEFAULT_SETTINGS = {
    "company_name": ("本地食品企业", "企业名称，仅用于页面展示"),
    "max_file_size_mb": (50, "单个上传文件大小限制（MB）"),
    "auto_cleanup_uploads": (True, "处理完成后自动清理临时上传文件"),
    "tenant_name": ("默认企业", "当前企业名称（第一版为单企业模式）"),
}


def initialize_database(db: Database, tenant_id: str = "default") -> dict[str, Any]:
    indexes = ensure_indexes(db)
    for key, (value, description) in DEFAULT_SETTINGS.items():
        if _settings.get(db, key, tenant_id, default=None) is None:
            _settings.set(db, key, value, tenant_id, description)
    _settings.set(db, "initialized_at", datetime.now(timezone.utc).isoformat(), tenant_id, "数据库初始化时间")
    return {"ok": True, "indexes": indexes, "database": db.name}


def get_setting(db: Database, key: str, default: Any = None, tenant_id: str = "default") -> Any:
    return _settings.get(db, key, tenant_id, default=default)


def set_setting(db: Database, key: str, value: Any, *, tenant_id: str = "default", description: str = "") -> None:
    _settings.set(db, key, value, tenant_id, description)


def list_settings(db: Database, tenant_id: str = "default") -> list[dict[str, Any]]:
    return _settings.all(db, tenant_id)


def clear_demo_data(db: Database, tenant_id: str = "default") -> dict[str, int]:
    """只删除带 is_demo=True 标记的数据，不触碰正式业务数据。"""

    result: dict[str, int] = {}
    demo_order_nos = [doc.get("order_no", "") for doc in db["sales_orders"].find({"tenant_id": tenant_id, "is_demo": True}, {"order_no": 1})]
    demo_order_ids = [doc["_id"] for doc in db["sales_orders"].find({"tenant_id": tenant_id, "is_demo": True}, {"_id": 1})]
    demo_batch_ids = [doc.get("batch_id", "") for doc in db["import_batches"].find({"tenant_id": tenant_id, "is_demo": True}, {"batch_id": 1})]
    if demo_order_ids:
        result["sales_order_items"] = int(db["sales_order_items"].delete_many({"order_id": {"$in": demo_order_ids}}).deleted_count)
    if demo_order_nos:
        result["matching_logs"] = int(db["matching_logs"].delete_many({"tenant_id": tenant_id, "order_no": {"$in": demo_order_nos}}).deleted_count)
    if demo_batch_ids:
        result["error_logs"] = int(db["error_logs"].delete_many({"tenant_id": tenant_id, "batch_id": {"$in": demo_batch_ids}}).deleted_count)
    for collection in ("customers", "products", "sales_orders", "sales_order_items", "delivery_records",
                       "payment_records", "import_batches", "import_logs", "matching_logs", "error_logs"):
        query: dict[str, Any] = {"tenant_id": tenant_id, "is_demo": True}
        result[collection] = result.get(collection, 0) + int(db[collection].delete_many(query).deleted_count)
    return result

