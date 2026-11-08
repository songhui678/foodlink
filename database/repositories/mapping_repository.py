"""字段映射配置仓储。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pymongo.database import Database

from database.repositories.base import BaseRepository, display_doc


class MappingRepository(BaseRepository):
    collection_name = "field_mapping_configs"

    def list(self, db: Database, tenant_id: str = "default", import_type: str = "") -> list[dict[str, Any]]:
        query: dict[str, Any] = {"tenant_id": tenant_id}
        if import_type:
            query["import_type"] = import_type
        cursor = self.collection(db).find(query).sort("updated_at", -1)
        return [display_doc(doc) for doc in cursor]

    def get(self, db: Database, tenant_id: str, import_type: str, name: str) -> dict[str, Any] | None:
        return display_doc(
            self.collection(db).find_one({"tenant_id": tenant_id, "import_type": import_type, "name": name})
        )

    def upsert(self, db: Database, tenant_id: str, import_type: str, name: str, mapping: dict[str, str]) -> None:
        now = datetime.now(timezone.utc)
        self.collection(db).update_one(
            {"tenant_id": tenant_id, "import_type": import_type, "name": name},
            {"$set": {"mapping": mapping, "updated_at": now}, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )

    def delete(self, db: Database, config_id: str) -> bool:
        from database.repositories.base import object_id

        oid = object_id(config_id)
        if not oid:
            return False
        return self.collection(db).delete_one({"_id": oid}).deleted_count > 0

