"""MongoDB 连接管理与连接检测。"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import ConfigurationError, InvalidURI, PyMongoError, ServerSelectionTimeoutError

from utils.config import get_settings
from utils.errors import DatabaseConnectionError
from utils.logger import get_logger
from utils.security import mask_mongodb_uri


_CLIENTS: dict[str, MongoClient] = {}
_LOCK = threading.Lock()


@dataclass
class ConnectionStatus:
    ok: bool
    message: str
    database: str
    uri: str
    server_version: str = ""
    latency_ms: int = 0


def get_client(uri: str | None = None) -> MongoClient:
    settings = get_settings()
    connection_uri = uri or settings.mongodb_uri
    with _LOCK:
        client = _CLIENTS.get(connection_uri)
        if client is None:
            try:
                client = MongoClient(
                    connection_uri,
                    serverSelectionTimeoutMS=3000,
                    connectTimeoutMS=3000,
                    socketTimeoutMS=8000,
                    appname="foodlink-v1",
                )
            except (InvalidURI, ConfigurationError) as exc:
                raise DatabaseConnectionError(
                    "MongoDB 连接地址格式不正确，请检查 .env 中的 MONGODB_URI。", detail=str(exc)
                ) from exc
            _CLIENTS[connection_uri] = client
    return client


def get_db(database: str | None = None, *, uri: str | None = None, ping: bool = True) -> Database:
    settings = get_settings()
    dbname = database or settings.mongodb_database
    client = get_client(uri)
    db = client[dbname]
    if ping:
        try:
            client.admin.command("ping")
        except ServerSelectionTimeoutError as exc:
            raise DatabaseConnectionError(
                "无法连接 MongoDB 数据库。请先启动 MongoDB，或检查 .env 中的 MONGODB_URI。",
                detail=str(exc),
            ) from exc
        except PyMongoError as exc:
            raise DatabaseConnectionError(
                "MongoDB 连接异常，请检查数据库服务和账号权限。", detail=str(exc)
            ) from exc
    return db


def check_connection(uri: str | None = None, database: str | None = None) -> ConnectionStatus:
    settings = get_settings()
    dbname = database or settings.mongodb_database
    used_uri = uri or settings.mongodb_uri
    started = time.time()
    try:
        client = get_client(used_uri)
        info = client.server_info()
        client.admin.command("ping")
        latency = int((time.time() - started) * 1000)
        return ConnectionStatus(
            ok=True,
            message="MongoDB 连接正常",
            database=dbname,
            uri=mask_mongodb_uri(used_uri),
            server_version=str(info.get("version", "")),
            latency_ms=latency,
        )
    except Exception as exc:
        get_logger().warning("MongoDB 连接检测失败：%s", type(exc).__name__)
        return ConnectionStatus(
            ok=False,
            message="无法连接 MongoDB。请确认服务已启动，并检查 MONGODB_URI 配置。",
            database=dbname,
            uri=mask_mongodb_uri(used_uri),
        )


def reset_connection_cache() -> None:
    global _CLIENTS
    with _LOCK:
        for client in _CLIENTS.values():
            try:
                client.close()
            except Exception:
                pass
        _CLIENTS = {}


def masked_current_uri() -> str:
    return mask_mongodb_uri(get_settings().mongodb_uri)


def database_summary(db: Database) -> list[dict[str, Any]]:
    """返回集合名称与文档数量，用于系统设置页展示。"""

    result: list[dict[str, Any]] = []
    names = ["customers", "products", "sales_orders", "sales_order_items", "delivery_records",
             "payment_records", "import_batches", "import_logs", "matching_logs", "error_logs",
             "field_mapping_configs", "system_settings"]
    for name in names:
        try:
            result.append({"集合": name, "文档数": db[name].count_documents({})})
        except Exception:
            result.append({"集合": name, "文档数": "读取失败"})
    return result

