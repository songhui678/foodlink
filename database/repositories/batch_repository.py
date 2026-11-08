"""导入批次与日志仓储。"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from pymongo.database import Database

from database.repositories.base import BaseRepository, display_doc, regex_contains


class BatchRepository(BaseRepository):
    collection_name = "import_batches"

    def create(self, db: Database, batch: dict[str, Any]) -> str:
        self.collection(db).insert_one(batch)
        return str(batch.get("batch_id", ""))

    def get(self, db: Database, batch_id: str) -> dict[str, Any] | None:
        return display_doc(self.collection(db).find_one({"batch_id": batch_id}))

    def update(self, db: Database, batch_id: str, data: dict[str, Any]) -> bool:
        return self.collection(db).update_one({"batch_id": batch_id}, {"$set": data}).matched_count > 0

    def find_by_hash(self, db: Database, file_hash: str, import_type: str, tenant_id: str = "default") -> list[dict[str, Any]]:
        cursor = self.collection(db).find({"tenant_id": tenant_id, "file_hash": file_hash, "import_type": import_type}).sort("created_at", -1)
        return [display_doc(doc) for doc in cursor]

    def list(self, db: Database, *, tenant_id: str = "default", import_type: str = "", status: str = "", search: str = "", start_date: str = "", end_date: str = "", skip: int = 0, limit: int = 20) -> list[dict[str, Any]]:
        query: dict[str, Any] = {"tenant_id": tenant_id}
        if import_type:
            query["import_type"] = import_type
        if status:
            query["status"] = status
        if search:
            pattern = regex_contains(search)
            query["$or"] = [{"filename": pattern}, {"batch_id": pattern}, {"sheet_name": pattern}]
        if start_date or end_date:
            date_query: dict[str, Any] = {}
            if start_date:
                value = start_date if isinstance(start_date, datetime) else datetime.combine(date.fromisoformat(str(start_date)), time.min)
                date_query["$gte"] = value
            if end_date:
                value = end_date if isinstance(end_date, datetime) else datetime.combine(date.fromisoformat(str(end_date)), time.max)
                date_query["$lte"] = value
            query["created_at"] = date_query
        cursor = self.collection(db).find(query).sort("created_at", -1).skip(skip).limit(limit)
        return [display_doc(doc) for doc in cursor]

    def count_list(self, db: Database, *, tenant_id: str = "default", import_type: str = "", status: str = "", search: str = "") -> int:
        query: dict[str, Any] = {"tenant_id": tenant_id}
        if import_type:
            query["import_type"] = import_type
        if status:
            query["status"] = status
        if search:
            pattern = regex_contains(search)
            query["$or"] = [{"filename": pattern}, {"batch_id": pattern}, {"sheet_name": pattern}]
        return int(self.collection(db).count_documents(query))

    def recent(self, db: Database, tenant_id: str = "default", limit: int = 5) -> list[dict[str, Any]]:
        cursor = self.collection(db).find({"tenant_id": tenant_id}).sort("created_at", -1).limit(limit)
        return [display_doc(doc) for doc in cursor]

    def add_log(self, db: Database, log: dict[str, Any]) -> None:
        db["import_logs"].insert_one(log)

    def list_logs(self, db: Database, batch_id: str) -> list[dict[str, Any]]:
        cursor = db["import_logs"].find({"batch_id": batch_id}).sort("created_at", 1)
        return [display_doc(doc) for doc in cursor]

    def list_batch_logs(self, db: Database, batch_id: str) -> list[dict[str, Any]]:
        return self.list_logs(db, batch_id)

