"""MongoDB 数据库备份与恢复。

使用 BSON JSON 格式打包为 zip，不依赖 mongodump/mongorestore，
普通 Python 环境即可完成备份和恢复，适合本地单机部署。
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bson import json_util
from pymongo.database import Database

from utils.config import get_settings
from utils.errors import BackupError
from utils.logger import get_logger


BACKUP_COLLECTIONS = [
    "customers", "products", "sales_orders", "sales_order_items", "delivery_records",
    "payment_records", "import_batches", "import_logs", "matching_logs", "error_logs",
    "field_mapping_configs", "system_settings",
]


def _safe_db_name(name: str) -> str:
    return "".join(char for char in name if char.isalnum() or char in "_-") or "foodlink"


def create_backup(db: Database, backup_dir: Path | str | None = None) -> Path:
    settings = get_settings()
    target_dir = Path(backup_dir or settings.backup_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = target_dir / f"foodlink_backup_{timestamp}.zip"
    manifest: dict[str, Any] = {
        "database": db.name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "format": "foodlink-jsonl-v1",
        "collections": {},
    }
    try:
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for name in BACKUP_COLLECTIONS:
                buffer = io.StringIO()
                count = 0
                for doc in db[name].find({}):
                    buffer.write(json_util.dumps(doc, json_options=json_util.RELAXED_JSON_OPTIONS))
                    buffer.write("\n")
                    count += 1
                zf.writestr(f"{name}.jsonl", buffer.getvalue())
                manifest["collections"][name] = count
            zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        get_logger().info("数据库备份完成：%s", path.name)
        return path
    except Exception as exc:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise BackupError("数据库备份失败，请检查备份目录权限。", detail=str(exc)) from exc


def list_backups(backup_dir: Path | str | None = None) -> list[dict[str, Any]]:
    settings = get_settings()
    directory = Path(backup_dir or settings.backup_dir)
    directory.mkdir(parents=True, exist_ok=True)
    result = []
    for path in sorted(directory.glob("foodlink_backup_*.zip"), reverse=True):
        try:
            stat = path.stat()
            result.append({"文件名": path.name, "大小MB": round(stat.st_size / 1024 / 1024, 2), "修改时间": datetime.fromtimestamp(stat.st_mtime)})
        except OSError:
            continue
    return result


def backup_file_bytes(path: Path | str) -> bytes:
    return Path(path).read_bytes()


def restore_backup(
    db: Database,
    content: bytes,
    *,
    mode: str = "merge",
    confirm_text: str = "",
) -> dict[str, Any]:
    if mode not in {"merge", "replace"}:
        raise BackupError("未知的恢复模式。")
    if mode == "replace" and confirm_text != "确认覆盖":
        raise BackupError("覆盖恢复需要输入“确认覆盖”四个字。")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            names = set(zf.namelist())
            if "manifest.json" not in names:
                raise BackupError("备份文件缺少 manifest.json，可能不是食链通备份。")
            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            if manifest.get("format") != "foodlink-jsonl-v1":
                raise BackupError("备份文件格式不受支持。")
            restored: dict[str, int] = {}
            for collection_name in BACKUP_COLLECTIONS:
                file_name = f"{collection_name}.jsonl"
                if file_name not in names:
                    continue
                if mode == "replace":
                    db[collection_name].delete_many({})
                content_text = zf.read(file_name).decode("utf-8")
                count = 0
                for line in content_text.splitlines():
                    if not line.strip():
                        continue
                    doc = json_util.loads(line)
                    if "_id" in doc:
                        db[collection_name].replace_one({"_id": doc["_id"]}, doc, upsert=True)
                    else:
                        db[collection_name].insert_one(doc)
                    count += 1
                restored[collection_name] = count
        get_logger().info("数据库恢复完成：mode=%s collections=%s", mode, restored)
        return {"ok": True, "message": "数据库恢复完成。", "collections": restored, "manifest": manifest}
    except BackupError:
        raise
    except Exception as exc:
        raise BackupError("数据库恢复失败，请检查备份文件是否完整。", detail=str(exc)) from exc

