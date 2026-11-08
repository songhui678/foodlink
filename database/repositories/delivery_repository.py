"""发货记录仓储。"""

from __future__ import annotations

from datetime import date
from typing import Any

from pymongo.database import Database

from database.repositories.base import BaseRepository, display_doc, regex_contains


class DeliveryRepository(BaseRepository):
    collection_name = "delivery_records"

    def list(
        self,
        db: Database,
        *,
        tenant_id: str = "default",
        search: str = "",
        start_date: date | str | None = None,
        end_date: date | str | None = None,
        order_no: str = "",
        skip: int = 0,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        query: dict[str, Any] = {"tenant_id": tenant_id}
        if search:
            pattern = regex_contains(search)
            query["$or"] = [
                {"delivery_no": pattern},
                {"order_no": pattern},
                {"customer_code": pattern},
                {"product_code": pattern},
            ]
        if order_no:
            query["order_no"] = order_no
        if start_date:
            query.setdefault("delivery_date", {})["$gte"] = start_date.isoformat() if isinstance(start_date, date) else str(start_date)
        if end_date:
            query.setdefault("delivery_date", {})["$lte"] = end_date.isoformat() if isinstance(end_date, date) else str(end_date)
        cursor = self.collection(db).find(query).sort([("delivery_date", -1), ("created_at", -1)]).skip(skip).limit(limit)
        return [display_doc(doc) for doc in cursor]

    def count_list(self, db: Database, *, tenant_id: str = "default", search: str = "", order_no: str = "", start_date: date | str | None = None, end_date: date | str | None = None) -> int:
        query: dict[str, Any] = {"tenant_id": tenant_id}
        if search:
            pattern = regex_contains(search)
            query["$or"] = [{"delivery_no": pattern}, {"order_no": pattern}, {"customer_code": pattern}, {"product_code": pattern}]
        if order_no:
            query["order_no"] = order_no
        if start_date:
            query.setdefault("delivery_date", {})["$gte"] = start_date.isoformat() if isinstance(start_date, date) else str(start_date)
        if end_date:
            query.setdefault("delivery_date", {})["$lte"] = end_date.isoformat() if isinstance(end_date, date) else str(end_date)
        return int(self.collection(db).count_documents(query))

    def all_records(self, db: Database, tenant_id: str = "default") -> list[dict[str, Any]]:
        return [display_doc(doc) for doc in self.collection(db).find({"tenant_id": tenant_id})]

    def find_by_order_no(self, db: Database, order_no: str, tenant_id: str = "default") -> list[dict[str, Any]]:
        return [display_doc(doc) for doc in self.collection(db).find({"tenant_id": tenant_id, "order_no": order_no})]

    def find_by_delivery_no(self, db: Database, delivery_no: str, tenant_id: str = "default") -> list[dict[str, Any]]:
        return [display_doc(doc) for doc in self.collection(db).find({"tenant_id": tenant_id, "delivery_no": delivery_no})]

    def duplicate_delivery_nos(self, db: Database, tenant_id: str = "default") -> list[dict[str, Any]]:
        pipeline = [
            {"$match": {"tenant_id": tenant_id}},
            {"$group": {"_id": "$delivery_no", "count": {"$sum": 1}, "order_nos": {"$addToSet": "$order_no"}}},
            {"$match": {"count": {"$gt": 1}}},
            {"$sort": {"count": -1}},
        ]
        return list(self.collection(db).aggregate(pipeline))

    def delete_by_batch(self, db: Database, batch_id: str) -> int:
        return int(self.collection(db).delete_many({"import_batch_id": batch_id}).deleted_count)

