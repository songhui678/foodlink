"""回款记录仓储。"""

from __future__ import annotations

from datetime import date
from typing import Any

from pymongo.database import Database

from database.repositories.base import BaseRepository, display_doc, regex_contains


class PaymentRepository(BaseRepository):
    collection_name = "payment_records"

    def list(self, db: Database, *, tenant_id: str = "default", search: str = "", start_date: date | str | None = None, end_date: date | str | None = None, skip: int = 0, limit: int = 20) -> list[dict[str, Any]]:
        query: dict[str, Any] = {"tenant_id": tenant_id}
        if search:
            pattern = regex_contains(search)
            query["$or"] = [{"payment_no": pattern}, {"customer_code": pattern}, {"remark": pattern}]
        if start_date:
            query.setdefault("payment_date", {})["$gte"] = start_date.isoformat() if isinstance(start_date, date) else str(start_date)
        if end_date:
            query.setdefault("payment_date", {})["$lte"] = end_date.isoformat() if isinstance(end_date, date) else str(end_date)
        cursor = self.collection(db).find(query).sort("payment_date", -1).skip(skip).limit(limit)
        return [display_doc(doc) for doc in cursor]

    def count_list(self, db: Database, *, tenant_id: str = "default", search: str = "", start_date: date | str | None = None, end_date: date | str | None = None) -> int:
        query: dict[str, Any] = {"tenant_id": tenant_id}
        if search:
            pattern = regex_contains(search)
            query["$or"] = [{"payment_no": pattern}, {"customer_code": pattern}, {"remark": pattern}]
        if start_date:
            query.setdefault("payment_date", {})["$gte"] = start_date.isoformat() if isinstance(start_date, date) else str(start_date)
        if end_date:
            query.setdefault("payment_date", {})["$lte"] = end_date.isoformat() if isinstance(end_date, date) else str(end_date)
        return int(self.collection(db).count_documents(query))

    def find_by_payment_no(self, db: Database, payment_no: str, tenant_id: str = "default") -> list[dict[str, Any]]:
        return [display_doc(doc) for doc in self.collection(db).find({"tenant_id": tenant_id, "payment_no": payment_no})]

