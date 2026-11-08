"""客户仓储。"""

from __future__ import annotations

from typing import Any

from pymongo.database import Database

from database.repositories.base import BaseRepository, display_doc, object_id, regex_contains


class CustomerRepository(BaseRepository):
    collection_name = "customers"

    def list(
        self,
        db: Database,
        *,
        tenant_id: str = "default",
        search: str = "",
        region: str = "",
        include_deleted: bool = False,
        skip: int = 0,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        query: dict[str, Any] = {"tenant_id": tenant_id}
        if not include_deleted:
            query["is_deleted"] = {"$ne": True}
        if region:
            query["region"] = region
        if search:
            pattern = regex_contains(search)
            query["$or"] = [
                {"customer_code": pattern},
                {"customer_name": pattern},
                {"contact": pattern},
                {"phone": pattern},
                {"region": pattern},
                {"address": pattern},
            ]
        cursor = self.collection(db).find(query).sort("created_at", -1).skip(skip).limit(limit)
        return [display_doc(doc) for doc in cursor]

    def count_list(
        self,
        db: Database,
        *,
        tenant_id: str = "default",
        search: str = "",
        region: str = "",
        include_deleted: bool = False,
    ) -> int:
        query: dict[str, Any] = {"tenant_id": tenant_id}
        if not include_deleted:
            query["is_deleted"] = {"$ne": True}
        if region:
            query["region"] = region
        if search:
            pattern = regex_contains(search)
            query["$or"] = [
                {"customer_code": pattern},
                {"customer_name": pattern},
                {"contact": pattern},
                {"phone": pattern},
            ]
        return int(self.collection(db).count_documents(query))

    def get(self, db: Database, customer_id: str) -> dict[str, Any] | None:
        oid = object_id(customer_id)
        if not oid:
            return None
        return display_doc(self.collection(db).find_one({"_id": oid}))

    def find_by_code_key(self, db: Database, code_key: str, tenant_id: str, *, include_deleted: bool = False) -> list[dict[str, Any]]:
        if not code_key:
            return []
        query: dict[str, Any] = {"tenant_id": tenant_id, "customer_code_key": code_key}
        if not include_deleted:
            query["is_deleted"] = {"$ne": True}
        return [display_doc(doc) for doc in self.collection(db).find(query)]

    def find_by_phone(self, db: Database, phone: str, tenant_id: str, *, include_deleted: bool = False) -> list[dict[str, Any]]:
        if not phone:
            return []
        query: dict[str, Any] = {"tenant_id": tenant_id, "phone": phone}
        if not include_deleted:
            query["is_deleted"] = {"$ne": True}
        return [display_doc(doc) for doc in self.collection(db).find(query)]

    def find_by_name_key(self, db: Database, name_key: str, tenant_id: str, *, include_deleted: bool = False) -> list[dict[str, Any]]:
        if not name_key:
            return []
        query: dict[str, Any] = {"tenant_id": tenant_id, "customer_name_key": name_key}
        if not include_deleted:
            query["is_deleted"] = {"$ne": True}
        return [display_doc(doc) for doc in self.collection(db).find(query)]

    def all_active(self, db: Database, tenant_id: str = "default") -> list[dict[str, Any]]:
        cursor = self.collection(db).find({"tenant_id": tenant_id, "is_deleted": {"$ne": True}})
        return [display_doc(doc) for doc in cursor]

    def regions(self, db: Database, tenant_id: str = "default") -> list[str]:
        values = self.collection(db).distinct("region", {"tenant_id": tenant_id, "region": {"$nin": ["", None]}})
        return sorted(str(item) for item in values)

    def update(self, db: Database, customer_id: str, data: dict[str, Any]) -> bool:
        oid = object_id(customer_id)
        if not oid:
            return False
        return self.collection(db).update_one({"_id": oid}, {"$set": data}).matched_count > 0

