"""轻量 MongoDB 测试替身。

仅用于自动化测试环境无法访问真实 MongoDB 时验证业务逻辑；
生产运行仍使用 PyMongo 连接真实 MongoDB。
"""

from __future__ import annotations

import copy
import re
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Iterable

from bson import ObjectId
from bson.decimal128 import Decimal128


class FakeClient:
    def __init__(self):
        self._databases: dict[str, FakeDatabase] = {}
        self.admin = FakeAdmin()
        self._server_info = {"version": "fake-mongo-1.0"}

    def __getitem__(self, name: str) -> "FakeDatabase":
        if name not in self._databases:
            self._databases[name] = FakeDatabase(self, name)
        return self._databases[name]

    def server_info(self):
        return dict(self._server_info)

    def drop_database(self, name: str) -> None:
        self._databases.pop(name, None)

    def close(self) -> None:
        pass


class FakeAdmin:
    def command(self, command: str):
        if command == "ping":
            return {"ok": 1}
        return {"ok": 1}


class FakeDatabase:
    def __init__(self, client: FakeClient, name: str):
        self.client = client
        self.name = name
        self._collections: dict[str, FakeCollection] = {}

    def __getitem__(self, name: str) -> "FakeCollection":
        if name not in self._collections:
            self._collections[name] = FakeCollection(name)
        return self._collections[name]


class FakeCursor:
    def __init__(self, docs: list[dict[str, Any]]):
        self._docs = docs

    def sort(self, key_or_list, direction: int | None = None):
        if isinstance(key_or_list, str):
            keys = [(key_or_list, direction if direction is not None else 1)]
        else:
            keys = list(key_or_list)
        for key, order in reversed(keys):
            self._docs.sort(key=lambda doc: _sort_value(doc.get(key)), reverse=order < 0)
        return self

    def skip(self, count: int):
        self._docs = self._docs[count:]
        return self

    def limit(self, count: int):
        self._docs = self._docs[:count]
        return self

    def __iter__(self):
        return iter(self._docs)

    def __len__(self):
        return len(self._docs)


class FakeCollection:
    def __init__(self, name: str):
        self.name = name
        self.docs: list[dict[str, Any]] = []

    def create_index(self, keys, **kwargs):
        return kwargs.get("name", "fake_index")

    def insert_one(self, doc: dict[str, Any]):
        doc = copy.deepcopy(doc)
        if "_id" not in doc:
            doc["_id"] = ObjectId()
        self.docs.append(doc)
        return SimpleNamespace(inserted_id=doc["_id"])

    def insert_many(self, docs: Iterable[dict[str, Any]]):
        inserted = []
        for doc in docs:
            inserted.append(self.insert_one(doc).inserted_id)
        return SimpleNamespace(inserted_ids=inserted)

    def find(self, query: dict[str, Any] | None = None, projection: dict[str, Any] | None = None):
        matched = [copy.deepcopy(doc) for doc in self.docs if _matches(doc, query or {})]
        return FakeCursor(matched)

    def find_one(self, query: dict[str, Any], projection: dict[str, Any] | None = None):
        for doc in self.docs:
            if _matches(doc, query):
                return copy.deepcopy(doc)
        return None

    def count_documents(self, query: dict[str, Any]) -> int:
        return sum(1 for doc in self.docs if _matches(doc, query))

    def update_one(self, query: dict[str, Any], update: dict[str, Any], upsert: bool = False):
        for doc in self.docs:
            if _matches(doc, query):
                before = copy.deepcopy(doc)
                _apply_update(doc, update)
                modified = 1 if doc != before else 0
                return SimpleNamespace(matched_count=1, modified_count=modified)
        if upsert:
            doc: dict[str, Any] = {}
            for key, value in query.items():
                if isinstance(value, dict) and any(str(k).startswith("$") for k in value):
                    continue
                doc[key] = copy.deepcopy(value)
            _apply_update(doc, update, on_insert=True)
            if "_id" not in doc:
                doc["_id"] = ObjectId()
            self.docs.append(doc)
            return SimpleNamespace(matched_count=0, modified_count=0, upserted_id=doc["_id"])
        return SimpleNamespace(matched_count=0, modified_count=0)

    def update_many(self, query: dict[str, Any], update: dict[str, Any]):
        matched = 0
        modified = 0
        for doc in self.docs:
            if _matches(doc, query):
                matched += 1
                before = copy.deepcopy(doc)
                _apply_update(doc, update)
                if doc != before:
                    modified += 1
        return SimpleNamespace(matched_count=matched, modified_count=modified)

    def replace_one(self, query: dict[str, Any], replacement: dict[str, Any], upsert: bool = False):
        for index, doc in enumerate(self.docs):
            if _matches(doc, query):
                new_doc = copy.deepcopy(replacement)
                new_doc.setdefault("_id", doc.get("_id", ObjectId()))
                self.docs[index] = new_doc
                return SimpleNamespace(matched_count=1, modified_count=1)
        if upsert:
            new_doc = copy.deepcopy(replacement)
            new_doc.setdefault("_id", ObjectId())
            self.docs.append(new_doc)
            return SimpleNamespace(matched_count=0, modified_count=0, upserted_id=new_doc["_id"])
        return SimpleNamespace(matched_count=0, modified_count=0)

    def delete_many(self, query: dict[str, Any]):
        before = len(self.docs)
        self.docs = [doc for doc in self.docs if not _matches(doc, query)]
        return SimpleNamespace(deleted_count=before - len(self.docs))

    def delete_one(self, query: dict[str, Any]):
        for index, doc in enumerate(self.docs):
            if _matches(doc, query):
                self.docs.pop(index)
                return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)

    def distinct(self, key: str, query: dict[str, Any] | None = None):
        values = []
        for doc in self.docs:
            if query and not _matches(doc, query):
                continue
            value = doc.get(key)
            if value not in values:
                values.append(value)
        return values

    def aggregate(self, pipeline: list[dict[str, Any]]):
        data = [copy.deepcopy(doc) for doc in self.docs]
        for stage in pipeline:
            if "$match" in stage:
                data = [doc for doc in data if _matches(doc, stage["$match"])]
            elif "$group" in stage:
                data = _group(data, stage["$group"])
            elif "$sort" in stage:
                sort_spec = stage["$sort"]
                items = sort_spec.items() if isinstance(sort_spec, dict) else sort_spec
                for key, order in reversed(list(items)):
                    data.sort(key=lambda doc: _sort_value(doc.get(key)), reverse=order < 0)
            elif "$limit" in stage:
                data = data[: stage["$limit"]]
        return data


def _sort_value(value: Any):
    if isinstance(value, Decimal128):
        return value.to_decimal()
    if isinstance(value, datetime):
        return value.timestamp()
    if isinstance(value, date):
        return value.toordinal()
    if value is None:
        return ""
    return value


def _matches(doc: dict[str, Any], query: dict[str, Any]) -> bool:
    for key, condition in query.items():
        if key == "$or":
            if not any(_matches(doc, item) for item in condition):
                return False
            continue
        if key == "$and":
            if not all(_matches(doc, item) for item in condition):
                return False
            continue
        value = doc.get(key)
        if isinstance(condition, re.Pattern):
            if not condition.search(str(value or "")):
                return False
        elif isinstance(condition, dict) and any(str(op).startswith("$") for op in condition):
            for op, expected in condition.items():
                if op == "$ne" and value == expected:
                    return False
                if op == "$in" and value not in expected:
                    return False
                if op == "$nin" and value in expected:
                    return False
                if op == "$exists" and bool(value is not None) != bool(expected):
                    return False
                if op == "$gte" and not _compare(value, expected) >= 0:
                    return False
                if op == "$lte" and not _compare(value, expected) <= 0:
                    return False
                if op == "$gt" and not _compare(value, expected) > 0:
                    return False
                if op == "$lt" and not _compare(value, expected) < 0:
                    return False
                if op == "$regex" and not re.search(expected, str(value or "")):
                    return False
        else:
            if isinstance(value, ObjectId) and isinstance(condition, str):
                if str(value) != condition:
                    return False
            elif value != condition:
                return False
    return True


def _compare(left: Any, right: Any) -> int:
    left = _sort_value(left)
    right = _sort_value(right)
    try:
        if left < right:
            return -1
        if left > right:
            return 1
        return 0
    except TypeError:
        return 0


def _apply_update(doc: dict[str, Any], update: dict[str, Any], *, on_insert: bool = False) -> None:
    if "$set" in update:
        for key, value in update["$set"].items():
            doc[key] = copy.deepcopy(value)
    if on_insert and "$setOnInsert" in update:
        for key, value in update["$setOnInsert"].items():
            doc.setdefault(key, copy.deepcopy(value))
    if "$inc" in update:
        for key, value in update["$inc"].items():
            doc[key] = (doc.get(key) or 0) + value
    plain = {key: value for key, value in update.items() if not str(key).startswith("$")}
    if plain:
        doc.update(copy.deepcopy(plain))


def _group(data: list[dict[str, Any]], spec: dict[str, Any]) -> list[dict[str, Any]]:
    group_key = spec.get("_id")
    accumulators = {key: value for key, value in spec.items() if key != "_id"}
    buckets: dict[Any, dict[str, Any]] = {}
    for doc in data:
        key = doc.get(group_key) if isinstance(group_key, str) else group_key
        if isinstance(group_key, dict):
            key = tuple(_resolve(doc, field[1:]) for field in group_key.values())
        bucket = buckets.setdefault(key, {"_id": key})
        for name, accumulator in accumulators.items():
            op, expression = next(iter(accumulator.items()))
            if op == "$sum":
                value = 1 if expression == 1 else _resolve(doc, expression[1:]) if isinstance(expression, str) else 0
                if isinstance(value, Decimal128):
                    value = value.to_decimal()
                bucket[name] = (bucket.get(name) or 0) + value
            elif op == "$addToSet":
                value = _resolve(doc, expression[1:]) if isinstance(expression, str) else expression
                bucket.setdefault(name, [])
                if value not in bucket[name]:
                    bucket[name].append(value)
            elif op == "$first":
                value = _resolve(doc, expression[1:]) if isinstance(expression, str) else expression
                bucket.setdefault(name, value)
    return list(buckets.values())


def _resolve(doc: dict[str, Any], path: str):
    value: Any = doc
    for part in path.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        else:
            return None
    return value

