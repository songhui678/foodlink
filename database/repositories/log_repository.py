"""匹配日志、异常日志与操作审计。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pymongo.database import Database

from database.repositories.base import BaseRepository, display_doc, object_id, regex_contains


class LogRepository(BaseRepository):
    collection_name = "matching_logs"

    def add_matching_log(self, db: Database, log: dict[str, Any]) -> str:
        result = db["matching_logs"].insert_one(log)
        return str(result.inserted_id)

    def update_matching_log(self, db: Database, log_id: str, data: dict[str, Any]) -> bool:
        oid = object_id(log_id)
        if not oid:
            return False
        return db["matching_logs"].update_one({"_id": oid}, {"$set": data}).matched_count > 0

    def get_matching_log(self, db: Database, log_id: str) -> dict[str, Any] | None:
        oid = object_id(log_id)
        if not oid:
            return None
        return display_doc(db["matching_logs"].find_one({"_id": oid}))

    def list_matching_logs(self, db: Database, *, tenant_id: str = "default", entity_type: str = "", status: str = "", search: str = "", skip: int = 0, limit: int = 50) -> list[dict[str, Any]]:
        query: dict[str, Any] = {"tenant_id": tenant_id}
        if entity_type:
            query["entity_type"] = entity_type
        if status:
            query["status"] = status
        if search:
            pattern = regex_contains(search)
            query["$or"] = [{"input_code": pattern}, {"input_name": pattern}, {"source_ref": pattern}]
        cursor = db["matching_logs"].find(query).sort("created_at", -1).skip(skip).limit(limit)
        return [display_doc(doc) for doc in cursor]

    def count_matching_logs(self, db: Database, *, tenant_id: str = "default", entity_type: str = "", status: str = "") -> int:
        query: dict[str, Any] = {"tenant_id": tenant_id}
        if entity_type:
            query["entity_type"] = entity_type
        if status:
            query["status"] = status
        return int(db["matching_logs"].count_documents(query))

    def pending_matching_count(self, db: Database, tenant_id: str = "default") -> int:
        return int(
            db["matching_logs"].count_documents(
                {
                    "tenant_id": tenant_id,
                    "status": {"$in": ["unmatched", "multiple", "abnormal", "duplicate"]},
                    "resolved": {"$ne": True},
                }
            )
        )

    def add_error_log(self, db: Database, log: dict[str, Any]) -> str:
        result = db["error_logs"].insert_one(log)
        return str(result.inserted_id)

    def list_error_logs(self, db: Database, *, tenant_id: str = "default", error_type: str = "", batch_id: str = "", skip: int = 0, limit: int = 100) -> list[dict[str, Any]]:
        query: dict[str, Any] = {"tenant_id": tenant_id}
        if error_type:
            query["error_type"] = error_type
        if batch_id:
            query["batch_id"] = batch_id
        cursor = db["error_logs"].find(query).sort("created_at", -1).skip(skip).limit(limit)
        return [display_doc(doc) for doc in cursor]

    def count_error_logs(self, db: Database, tenant_id: str = "default", error_type: str = "") -> int:
        query: dict[str, Any] = {"tenant_id": tenant_id}
        if error_type:
            query["error_type"] = error_type
        return int(db["error_logs"].count_documents(query))

    def add_audit_log(self, db: Database, action: str, detail: dict[str, Any], tenant_id: str = "default") -> None:
        db["import_logs"].insert_one(
            {
                "tenant_id": tenant_id,
                "log_type": "audit",
                "action": action,
                "detail": detail,
                "created_at": datetime.now(timezone.utc),
            }
        )

