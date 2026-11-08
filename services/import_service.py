"""导入批次管理、字段映射持久化与正式导入。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pandas as pd
from pymongo.database import Database

from database.repositories.batch_repository import BatchRepository
from database.repositories.mapping_repository import MappingRepository
from services import customer_service, delivery_service, order_service, product_service
from services.excel_service import ImportAnalysis
from utils.decimal_utils import round_money, to_decimal128
from utils.errors import DataValidationError
from utils.logger import get_logger
from utils.validator import format_date


_batches = BatchRepository()
_mappings = MappingRepository()


@dataclass
class ImportCommitResult:
    batch_id: str
    import_type: str
    total_rows: int
    success_rows: int
    failed_rows: int
    status: str
    details: list[dict[str, Any]] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)


def new_batch_id() -> str:
    return f"BATCH-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"


def find_duplicate_batches(db: Database, file_hash: str, import_type: str, tenant_id: str = "default") -> list[dict[str, Any]]:
    return _batches.find_by_hash(db, file_hash, import_type, tenant_id)


def list_batches(db: Database, **filters) -> list[dict[str, Any]]:
    return _batches.list(db, **filters)


def count_batches(db: Database, **filters) -> int:
    return _batches.count_list(db, **filters)


def get_batch(db: Database, batch_id: str) -> dict[str, Any] | None:
    return _batches.get(db, batch_id)


def batch_dataframe(batches: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for item in batches:
        rows.append(
            {
                "批次编号": item.get("batch_id", ""),
                "导入类型": item.get("import_type_label", item.get("import_type", "")),
                "文件名": item.get("filename", ""),
                "Sheet": item.get("sheet_name", ""),
                "总行数": item.get("total_rows", 0),
                "成功行数": item.get("success_rows", 0),
                "失败行数": item.get("failed_rows", 0),
                "状态": item.get("status", ""),
                "导入时间": item.get("created_at", ""),
            }
        )
    return pd.DataFrame(rows, columns=["批次编号", "导入类型", "文件名", "Sheet", "总行数", "成功行数", "失败行数", "状态", "导入时间"])


def save_mapping_config(db: Database, import_type: str, name: str, mapping: dict[str, str], tenant_id: str = "default") -> None:
    _mappings.upsert(db, tenant_id, import_type, name or "默认映射", mapping)


def list_mapping_configs(db: Database, import_type: str = "", tenant_id: str = "default") -> list[dict[str, Any]]:
    return _mappings.list(db, tenant_id, import_type)


def delete_mapping_config(db: Database, config_id: str) -> bool:
    return _mappings.delete(db, config_id)


def _payment_import(db: Database, record: dict[str, Any], batch_id: str, tenant_id: str) -> tuple[str, str]:
    payment_no = str(record.get("payment_no") or "").strip()
    if not payment_no:
        return "skipped", "回款单号为空"
    existing = db["payment_records"].find_one({"tenant_id": tenant_id, "payment_no": payment_no})
    if existing:
        return "duplicate", "回款单号已存在，已跳过"
    doc = {
        "tenant_id": tenant_id,
        "payment_no": payment_no,
        "customer_code": str(record.get("customer_code") or "").strip(),
        "payment_date": format_date(record.get("payment_date")),
        "amount": to_decimal128(round_money(record.get("amount"))),
        "remark": str(record.get("remark") or "").strip(),
        "import_batch_id": batch_id,
        "raw_data": record.get("__raw__", ""),
        "is_demo": bool(record.get("is_demo", False)),
        "created_at": datetime.now(timezone.utc),
    }
    db["payment_records"].insert_one(doc)
    return "inserted", payment_no


def commit_import(
    db: Database,
    analysis: ImportAnalysis,
    *,
    tenant_id: str = "default",
    duplicate_file_action: str = "reimport",
    update_existing: bool = False,
    save_mapping: bool = True,
    mapping_name: str = "默认映射",
    is_demo: bool = False,
) -> ImportCommitResult:
    """正式写入数据库。duplicate_file_action: skip/reimport/cancel。"""

    if duplicate_file_action == "cancel":
        raise DataValidationError("已取消导入。")
    if duplicate_file_action == "skip" and analysis.duplicate_batches:
        return ImportCommitResult(
            batch_id="",
            import_type=analysis.import_type,
            total_rows=analysis.validation.total_rows,
            success_rows=0,
            failed_rows=0,
            status="已跳过",
            messages=["该文件曾导入过，已按用户选择跳过。"],
        )

    from utils.field_definitions import IMPORT_SCHEMAS

    schema = IMPORT_SCHEMAS[analysis.import_type]
    batch_id = new_batch_id()
    created_at = datetime.now(timezone.utc)
    batch_doc = {
        "batch_id": batch_id,
        "tenant_id": tenant_id,
        "import_type": analysis.import_type,
        "import_type_label": schema.label,
        "filename": analysis.filename,
        "sheet_name": analysis.sheet_name,
        "file_hash": analysis.file_hash,
        "mapping": analysis.mapping,
        "total_rows": analysis.validation.total_rows,
        "success_rows": 0,
        "failed_rows": 0,
        "status": "处理中",
        "is_reimport": bool(analysis.duplicate_batches),
        "is_demo": is_demo,
        "created_at": created_at,
        "updated_at": created_at,
        "errors": [],
    }
    _batches.create(db, batch_doc)

    details: list[dict[str, Any]] = []
    success = 0
    failed = analysis.validation.error_count
    messages: list[str] = []
    valid_rows = analysis.valid_rows

    try:
        if analysis.import_type == "customer":
            for record in valid_rows:
                status, message = customer_service.import_customer_document(
                    db, record, batch_id=batch_id, tenant_id=tenant_id, update_existing=update_existing
                )
                details.append({"status": status, "message": message, "row_no": record.get("__row_no__")})
                if status in {"inserted", "updated"}:
                    success += 1
                else:
                    failed += 1
        elif analysis.import_type == "product":
            for record in valid_rows:
                status, message = product_service.import_product_document(
                    db, record, batch_id=batch_id, tenant_id=tenant_id, update_existing=update_existing
                )
                details.append({"status": status, "message": message, "row_no": record.get("__row_no__")})
                if status in {"inserted", "updated"}:
                    success += 1
                else:
                    failed += 1
        elif analysis.import_type == "order":
            failed = 0
            invalid_order_nos = {
                str(row.get("order_no") or "")
                for row in analysis.validation.invalid_rows
                if row.get("order_no")
            }
            grouped = order_service.group_records_by_order(valid_rows)
            for row in analysis.validation.invalid_rows:
                if row.get("order_no") and str(row["order_no"]) in grouped:
                    invalid_order_nos.add(str(row["order_no"]))
            # 先统计无法归属到任何有效订单的错误行
            failed += len([
                row for row in analysis.validation.invalid_rows
                if not row.get("order_no") or str(row.get("order_no")) not in grouped
            ])
            for order_no, records in grouped.items():
                if order_no in invalid_order_nos:
                    details.append({"status": "skipped", "message": f"订单 {order_no} 存在错误行，整单未导入", "order_no": order_no})
                    invalid_count = len([
                        row for row in analysis.validation.invalid_rows if str(row.get("order_no") or "") == order_no
                    ])
                    failed += len(records) + invalid_count
                    continue
                result = order_service.build_order_from_records(db, records, batch_id=batch_id, tenant_id=tenant_id)
                details.append(result)
                if result.get("status") == "inserted":
                    success += len(records)
                else:
                    failed += len(records)
        elif analysis.import_type == "delivery":
            for record in valid_rows:
                status, message = delivery_service.import_delivery_record(
                    db, record, batch_id=batch_id, tenant_id=tenant_id
                )
                details.append({"status": status, "message": message, "row_no": record.get("__row_no__")})
                if status == "inserted":
                    success += 1
                else:
                    failed += 1
        elif analysis.import_type == "payment":
            for record in valid_rows:
                status, message = _payment_import(db, record, batch_id, tenant_id)
                details.append({"status": status, "message": message, "row_no": record.get("__row_no__")})
                if status == "inserted":
                    success += 1
                else:
                    failed += 1
        else:
            raise DataValidationError("未知的导入类型。")
    except Exception as exc:
        get_logger().exception("导入批次 %s 执行失败", batch_id)
        _batches.update(
            db,
            batch_id,
            {"status": "失败", "failed_rows": max(failed, len(valid_rows)), "updated_at": datetime.now(timezone.utc)},
        )
        raise

    status = "已完成"
    if success == 0:
        status = "失败"
    elif failed > 0:
        status = "部分完成"
    errors = analysis.error_dataframe.to_dict("records")[:2000]
    _batches.update(
        db,
        batch_id,
        {
            "success_rows": success,
            "failed_rows": failed,
            "status": status,
            "errors": errors,
            "updated_at": datetime.now(timezone.utc),
        },
    )
    _batches.add_log(
        db,
        {
            "tenant_id": tenant_id,
            "batch_id": batch_id,
            "log_type": "batch_summary",
            "success_rows": success,
            "failed_rows": failed,
            "status": status,
            "detail": {"details": details[:500]},
            "created_at": datetime.now(timezone.utc),
        },
    )
    if errors:
        docs = [
            {
                "tenant_id": tenant_id,
                "error_type": "import_error",
                "batch_id": batch_id,
                "row_no": error.get("行号"),
                "field": error.get("字段"),
                "message": error.get("错误原因"),
                "raw": error.get("原始数据"),
                "created_at": datetime.now(timezone.utc),
            }
            for error in errors[:2000]
        ]
        if docs:
            db["error_logs"].insert_many(docs)
    if save_mapping and analysis.mapping:
        save_mapping_config(db, analysis.import_type, mapping_name, analysis.mapping, tenant_id)
    messages.append(f"批次 {batch_id} 已处理完成。")
    return ImportCommitResult(
        batch_id=batch_id,
        import_type=analysis.import_type,
        total_rows=analysis.validation.total_rows,
        success_rows=success,
        failed_rows=failed,
        status=status,
        details=details,
        messages=messages,
    )


def import_error_dataframe(db: Database, batch_id: str = "", tenant_id: str = "default") -> pd.DataFrame:
    query: dict[str, Any] = {"tenant_id": tenant_id, "error_type": "import_error"}
    if batch_id:
        query["batch_id"] = batch_id
    docs = list(db["error_logs"].find(query).sort("created_at", -1).limit(5000))
    rows = [
        {"批次编号": doc.get("batch_id", ""), "行号": doc.get("row_no", ""), "字段": doc.get("field", ""), "错误原因": doc.get("message", ""), "原始数据": doc.get("raw", "")}
        for doc in docs
    ]
    return pd.DataFrame(rows, columns=["批次编号", "行号", "字段", "错误原因", "原始数据"])

