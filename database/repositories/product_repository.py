"""商品仓储。"""

from __future__ import annotations

from typing import Any

from pymongo.database import Database

from database.repositories.base import BaseRepository, display_doc, object_id, regex_contains


class ProductRepository(BaseRepository):
    collection_name = "products"

    def list(
        self,
        db: Database,
        *,
        tenant_id: str = "default",
        search: str = "",
        category: str = "",
        include_deleted: bool = False,
        skip: int = 0,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        query: dict[str, Any] = {"tenant_id": tenant_id}
        if not include_deleted:
            query["is_deleted"] = {"$ne": True}
        if category:
            query["category"] = category
        if search:
            pattern = regex_contains(search)
            query["$or"] = [
                {"product_code": pattern},
                {"product_name": pattern},
                {"specification": pattern},
                {"category": pattern},
                {"unit": pattern},
            ]
        cursor = self.collection(db).find(query).sort("created_at", -1).skip(skip).limit(limit)
        return [display_doc(doc) for doc in cursor]

    def count_list(
        self,
        db: Database,
        *,
        tenant_id: str = "default",
        search: str = "",
        category: str = "",
        include_deleted: bool = False,
    ) -> int:
        query: dict[str, Any] = {"tenant_id": tenant_id}
        if not include_deleted:
            query["is_deleted"] = {"$ne": True}
        if category:
            query["category"] = category
        if search:
            pattern = regex_contains(search)
            query["$or"] = [
                {"product_code": pattern},
                {"product_name": pattern},
                {"specification": pattern},
            ]
        return int(self.collection(db).count_documents(query))

    def get(self, db: Database, product_id: str) -> dict[str, Any] | None:
        oid = object_id(product_id)
        if not oid:
            return None
        return display_doc(self.collection(db).find_one({"_id": oid}))

    def find_by_code_key(self, db: Database, code_key: str, tenant_id: str, *, include_deleted: bool = False) -> list[dict[str, Any]]:
        if not code_key:
            return []
        query: dict[str, Any] = {"tenant_id": tenant_id, "product_code_key": code_key}
        if not include_deleted:
            query["is_deleted"] = {"$ne": True}
        return [display_doc(doc) for doc in self.collection(db).find(query)]

    def find_by_name_spec(self, db: Database, name_key: str, spec_key: str, tenant_id: str, *, include_deleted: bool = False) -> list[dict[str, Any]]:
        if not name_key:
            return []
        query: dict[str, Any] = {"tenant_id": tenant_id, "product_name_key": name_key, "spec_key": spec_key}
        if not include_deleted:
            query["is_deleted"] = {"$ne": True}
        return [display_doc(doc) for doc in self.collection(db).find(query)]

    def find_by_name_key(self, db: Database, name_key: str, tenant_id: str, *, include_deleted: bool = False) -> list[dict[str, Any]]:
        if not name_key:
            return []
        query: dict[str, Any] = {"tenant_id": tenant_id, "product_name_key": name_key}
        if not include_deleted:
            query["is_deleted"] = {"$ne": True}
        return [display_doc(doc) for doc in self.collection(db).find(query)]

    def all_active(self, db: Database, tenant_id: str = "default") -> list[dict[str, Any]]:
        cursor = self.collection(db).find({"tenant_id": tenant_id, "is_deleted": {"$ne": True}})
        return [display_doc(doc) for doc in cursor]

    def categories(self, db: Database, tenant_id: str = "default") -> list[str]:
        values = self.collection(db).distinct("category", {"tenant_id": tenant_id, "category": {"$nin": ["", None]}})
        return sorted(str(item) for item in values)

    def update(self, db: Database, product_id: str, data: dict[str, Any]) -> bool:
        oid = object_id(product_id)
        if not oid:
            return False
        return self.collection(db).update_one({"_id": oid}, {"$set": data}).matched_count > 0

