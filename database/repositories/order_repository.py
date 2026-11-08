"""订单与订单明细仓储。"""

from __future__ import annotations

from datetime import date
from typing import Any

from pymongo.database import Database

from database.repositories.base import BaseRepository, display_doc, object_id, regex_contains


class OrderRepository(BaseRepository):
    collection_name = "sales_orders"
    items_collection_name = "sales_order_items"

    def items(self, db: Database):
        return db[self.items_collection_name]

    def insert_order(self, db: Database, order_doc: dict[str, Any], item_docs: list[dict[str, Any]]) -> str:
        result = self.collection(db).insert_one(order_doc)
        order_id = result.inserted_id
        for item in item_docs:
            item["order_id"] = order_id
        if item_docs:
            self.items(db).insert_many(item_docs)
        return str(order_id)

    def list(
        self,
        db: Database,
        *,
        tenant_id: str = "default",
        search: str = "",
        customer_id: str = "",
        start_date: date | str | None = None,
        end_date: date | str | None = None,
        status: str = "",
        order_nos: list[str] | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        query: dict[str, Any] = {"tenant_id": tenant_id}
        if search:
            pattern = regex_contains(search)
            query["$or"] = [
                {"order_no": pattern},
                {"customer_code": pattern},
                {"customer_name": pattern},
            ]
        if customer_id:
            oid = object_id(customer_id)
            if oid:
                query["customer_id"] = oid
        if start_date:
            query.setdefault("order_date", {})["$gte"] = start_date.isoformat() if isinstance(start_date, date) else str(start_date)
        if end_date:
            query.setdefault("order_date", {})["$lte"] = end_date.isoformat() if isinstance(end_date, date) else str(end_date)
        if status:
            query["status"] = status
        if order_nos is not None:
            query["order_no"] = {"$in": order_nos}
        cursor = self.collection(db).find(query).sort([("order_date", -1), ("created_at", -1)]).skip(skip).limit(limit)
        return [display_doc(doc) for doc in cursor]

    def count_list(
        self,
        db: Database,
        *,
        tenant_id: str = "default",
        search: str = "",
        customer_id: str = "",
        start_date: date | str | None = None,
        end_date: date | str | None = None,
        status: str = "",
        order_nos: list[str] | None = None,
    ) -> int:
        query: dict[str, Any] = {"tenant_id": tenant_id}
        if search:
            pattern = regex_contains(search)
            query["$or"] = [
                {"order_no": pattern},
                {"customer_code": pattern},
                {"customer_name": pattern},
            ]
        if customer_id:
            oid = object_id(customer_id)
            if oid:
                query["customer_id"] = oid
        if start_date:
            query.setdefault("order_date", {})["$gte"] = start_date.isoformat() if isinstance(start_date, date) else str(start_date)
        if end_date:
            query.setdefault("order_date", {})["$lte"] = end_date.isoformat() if isinstance(end_date, date) else str(end_date)
        if status:
            query["status"] = status
        if order_nos is not None:
            query["order_no"] = {"$in": order_nos}
        return int(self.collection(db).count_documents(query))

    def get(self, db: Database, order_id: str) -> dict[str, Any] | None:
        oid = object_id(order_id)
        if not oid:
            return None
        return display_doc(self.collection(db).find_one({"_id": oid}))

    def find_by_order_no(self, db: Database, order_no: str, tenant_id: str = "default") -> list[dict[str, Any]]:
        cursor = self.collection(db).find({"tenant_id": tenant_id, "order_no": order_no})
        return [display_doc(doc) for doc in cursor]

    def get_items(self, db: Database, order_id: str) -> list[dict[str, Any]]:
        oid = object_id(order_id)
        if not oid:
            return []
        cursor = self.items(db).find({"order_id": oid})
        return [display_doc(doc) for doc in cursor]

    def get_items_by_order_no(self, db: Database, order_no: str) -> list[dict[str, Any]]:
        cursor = self.items(db).find({"order_no": order_no})
        return [display_doc(doc) for doc in cursor]

    def all_orders(self, db: Database, *, tenant_id: str = "default", start_date: date | str | None = None, end_date: date | str | None = None) -> list[dict[str, Any]]:
        query: dict[str, Any] = {"tenant_id": tenant_id}
        if start_date:
            query.setdefault("order_date", {})["$gte"] = start_date.isoformat() if isinstance(start_date, date) else str(start_date)
        if end_date:
            query.setdefault("order_date", {})["$lte"] = end_date.isoformat() if isinstance(end_date, date) else str(end_date)
        return [display_doc(doc) for doc in self.collection(db).find(query)]

    def order_nos_for_product(self, db: Database, product_id: str, tenant_id: str = "default") -> list[str]:
        oid = object_id(product_id)
        if not oid:
            return []
        order_ids = self.items(db).distinct("order_id", {"product_id": oid})
        if not order_ids:
            return []
        cursor = self.collection(db).find({"tenant_id": tenant_id, "_id": {"$in": order_ids}}, {"order_no": 1})
        return [str(doc.get("order_no", "")) for doc in cursor]

    def update(self, db: Database, order_id: str, data: dict[str, Any]) -> bool:
        oid = object_id(order_id)
        if not oid:
            return False
        return self.collection(db).update_one({"_id": oid}, {"$set": data}).matched_count > 0

    def update_by_order_no(self, db: Database, order_no: str, data: dict[str, Any], tenant_id: str = "default") -> int:
        return int(self.collection(db).update_many({"tenant_id": tenant_id, "order_no": order_no}, {"$set": data}).modified_count)

    def update_items_by_order_no(self, db: Database, order_no: str, data: dict[str, Any]) -> int:
        return int(self.items(db).update_many({"order_no": order_no}, {"$set": data}).modified_count)

    def update_items_by_product(self, db: Database, product_code: str, product_name: str, data: dict[str, Any]) -> int:
        query: dict[str, Any] = {"product_code": product_code} if product_code else {"product_name": product_name}
        return int(self.items(db).update_many(query, {"$set": data}).modified_count)

    def delete_by_batch(self, db: Database, batch_id: str) -> int:
        order_ids = [doc["_id"] for doc in self.collection(db).find({"import_batch_id": batch_id}, {"_id": 1})]
        if order_ids:
            self.items(db).delete_many({"order_id": {"$in": order_ids}})
        return int(self.collection(db).delete_many({"import_batch_id": batch_id}).deleted_count)

    def count(self, db: Database, tenant_id: str = "default") -> int:
        return int(self.collection(db).count_documents({"tenant_id": tenant_id}))

    def duplicate_order_nos(self, db: Database, tenant_id: str = "default") -> list[dict[str, Any]]:
        pipeline = [
            {"$match": {"tenant_id": tenant_id}},
            {"$group": {"_id": "$order_no", "count": {"$sum": 1}}},
            {"$match": {"count": {"$gt": 1}}},
            {"$sort": {"count": -1}},
        ]
        return list(self.collection(db).aggregate(pipeline))

