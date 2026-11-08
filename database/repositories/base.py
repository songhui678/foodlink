"""仓储基类与 Mongo 文档转换工具。"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable

from bson import ObjectId
from bson.decimal128 import Decimal128
from pymongo.database import Database


def object_id(value: Any) -> ObjectId | None:
    if isinstance(value, ObjectId):
        return value
    if isinstance(value, str) and ObjectId.is_valid(value):
        return ObjectId(value)
    return None


def display_doc(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    """把 Mongo 文档转换为 UI 友好格式：ObjectId -> str，Decimal128 -> Decimal。"""

    if doc is None:
        return None
    result: dict[str, Any] = {}
    for key, value in doc.items():
        if isinstance(value, ObjectId):
            result[key] = str(value)
        elif isinstance(value, Decimal128):
            result[key] = value.to_decimal()
        elif isinstance(value, Decimal):
            result[key] = value
        elif isinstance(value, (datetime, date)):
            result[key] = value
        elif key == "_id" and value is not None:
            result["id"] = str(value)
        elif isinstance(value, list):
            result[key] = [display_doc(item) if isinstance(item, dict) else item for item in value]
        elif isinstance(value, dict):
            result[key] = display_doc(value)
        else:
            result[key] = value
    if "_id" in doc:
        result["id"] = str(doc["_id"])
    return result


def regex_contains(text: str) -> re.Pattern:
    return re.compile(re.escape(text), re.IGNORECASE)


def date_bounds(start: date | str | None, end: date | str | None) -> dict[str, Any]:
    query: dict[str, Any] = {}
    if start:
        query["$gte"] = start.isoformat() if isinstance(start, date) else str(start)
    if end:
        query["$lte"] = end.isoformat() if isinstance(end, date) else str(end)
    return query


class BaseRepository:
    collection_name = ""

    def collection(self, db: Database):
        return db[self.collection_name]

    def count(self, db: Database, query: dict[str, Any] | None = None) -> int:
        return int(self.collection(db).count_documents(query or {}))

    def find(self, db: Database, query: dict[str, Any] | None = None, **kwargs) -> list[dict[str, Any]]:
        cursor = self.collection(db).find(query or {}, **kwargs)
        return [display_doc(doc) for doc in cursor]

    def find_one(self, db: Database, query: dict[str, Any], **kwargs) -> dict[str, Any] | None:
        return display_doc(self.collection(db).find_one(query, **kwargs))

    def insert_one(self, db: Database, doc: dict[str, Any]):
        return self.collection(db).insert_one(doc)

    def insert_many(self, db: Database, docs: Iterable[dict[str, Any]]):
        return self.collection(db).insert_many(list(docs))

    def update_one(self, db: Database, query: dict[str, Any], update: dict[str, Any]):
        return self.collection(db).update_one(query, update)

