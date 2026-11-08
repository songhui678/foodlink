"""系统设置仓储。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pymongo.database import Database

from database.repositories.base import BaseRepository, display_doc


class SettingsRepository(BaseRepository):
    collection_name = "system_settings"

    def get(self, db: Database, key: str, tenant_id: str = "default", default: Any = None) -> Any:
        doc = self.collection(db).find_one({"tenant_id": tenant_id, "key": key})
        return doc.get("value", default) if doc else default

    def set(self, db: Database, key: str, value: Any, tenant_id: str = "default", description: str = "") -> None:
        now = datetime.now(timezone.utc)
        self.collection(db).update_one(
            {"tenant_id": tenant_id, "key": key},
            {"$set": {"value": value, "description": description, "updated_at": now},
             "$setOnInsert": {"created_at": now}},
            upsert=True,
        )

    def all(self, db: Database, tenant_id: str = "default") -> list[dict[str, Any]]:
        cursor = self.collection(db).find({"tenant_id": tenant_id}).sort("key", 1)
        return [display_doc(doc) for doc in cursor]

