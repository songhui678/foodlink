"""订单管理、金额汇总与异常检测。"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

import pandas as pd
from pymongo.database import Database

from database.repositories.customer_repository import CustomerRepository
from database.repositories.log_repository import LogRepository
from database.repositories.order_repository import OrderRepository
from database.repositories.product_repository import ProductRepository
from services import matching_service
from utils.decimal_utils import (
    ZERO,
    amounts_equal,
    from_db_decimal,
    round_money,
    round_qty,
    to_decimal,
    to_decimal128,
)
from utils.errors import DataValidationError
from utils.validator import format_date


_orders = OrderRepository()
_customers = CustomerRepository()
_products = ProductRepository()
_logs = LogRepository()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _customer_identity(record: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(record.get("customer_code") or "").strip(),
        str(record.get("customer_name") or "").strip(),
        format_date(record.get("order_date")),
    )


def build_order_from_records(
    db: Database,
    records: list[dict[str, Any]],
    *,
    batch_id: str,
    tenant_id: str = "default",
) -> dict[str, Any]:
    """把同一订单编号的多行明细合并成一张订单并写入数据库。"""

    if not records:
        return {"status": "skipped", "message": "没有订单明细"}
    order_no = str(records[0].get("order_no") or "").strip()
    if not order_no:
        return {"status": "skipped", "message": "订单编号为空"}

    existing = _orders.find_by_order_no(db, order_no, tenant_id)
    if existing:
        return {
            "status": "duplicate",
            "order_no": order_no,
            "message": f"订单编号“{order_no}”已存在 {len(existing)} 条记录，已跳过，未覆盖原数据。",
        }

    identities = {_customer_identity(record) for record in records}
    customer_codes = {item[0] for item in identities if item[0]}
    customer_names = {item[1] for item in identities if item[1]}
    dates = {item[2] for item in identities if item[2]}
    identity_conflict = len(customer_codes) > 1 or len(customer_names) > 1 or len(dates) > 1
    first = records[0]
    order_date = format_date(first.get("order_date"))
    customer_code = str(first.get("customer_code") or "").strip()
    customer_name = str(first.get("customer_name") or "").strip()

    customer_outcome = matching_service.match_customer(
        db, customer_code=customer_code, customer_name=customer_name, tenant_id=tenant_id
    )
    customer = customer_outcome.get("matched") if customer_outcome.get("status") == "matched" else None
    if customer_outcome.get("status") in {"unmatched", "multiple", "duplicate", "abnormal"}:
        matching_service.record_customer_match(
            db,
            customer_code=customer_code,
            customer_name=customer_name,
            source_type="order_import",
            source_ref=order_no,
            order_no=order_no,
            tenant_id=tenant_id,
        )

    item_docs: list[dict[str, Any]] = []
    total_quantity = ZERO
    total_amount = ZERO
    line_anomaly = False
    for record in records:
        product_code = str(record.get("product_code") or "").strip()
        product_name = str(record.get("product_name") or "").strip()
        specification = str(record.get("specification") or "").strip()
        product_outcome = matching_service.match_product(
            db,
            product_code=product_code,
            product_name=product_name,
            specification=specification,
            tenant_id=tenant_id,
        )
        product = product_outcome.get("matched") if product_outcome.get("status") == "matched" else None
        if product_outcome.get("status") in {"unmatched", "multiple", "duplicate", "abnormal"}:
            source_ref = f"{order_no}#{product_code or product_name or record.get('__row_no__')}"
            matching_service.record_product_match(
                db,
                product_code=product_code,
                product_name=product_name,
                specification=specification,
                source_type="order_import",
                source_ref=source_ref,
                order_no=order_no,
                tenant_id=tenant_id,
            )

        quantity = round_qty(record.get("quantity"))
        unit_price = round_money(record.get("unit_price"))
        amount = round_money(record.get("amount"))
        if amount == ZERO and quantity and unit_price:
            amount = round_money(quantity * unit_price)
        if unit_price == ZERO and amount and quantity:
            unit_price = round_money(amount / quantity)
        mismatch = bool(record.get("__amount_mismatch__")) or not amounts_equal(amount, quantity * unit_price)
        line_anomaly = line_anomaly or mismatch
        total_quantity += quantity
        total_amount += amount
        item_docs.append(
            {
                "order_no": order_no,
                "product_id": product.get("id") if product else "",
                "product_code": product_code or (product.get("product_code", "") if product else ""),
                "product_name": product_name or (product.get("product_name", "") if product else ""),
                "specification": specification or (product.get("specification", "") if product else ""),
                "unit": str(record.get("unit") or (product.get("unit", "") if product else "")),
                "quantity": to_decimal128(quantity),
                "unit_price": to_decimal128(unit_price),
                "amount": to_decimal128(amount),
                "amount_mismatch": mismatch,
                "import_batch_id": batch_id,
                "raw_data": record.get("__raw__", ""),
                "is_demo": bool(record.get("is_demo", False)),
                "tenant_id": tenant_id,
                "created_at": _now(),
            }
        )

    missing_product = any(not item.get("product_id") for item in item_docs)
    status = "正常"
    if not customer or missing_product:
        status = "待匹配"
    if identity_conflict:
        status = "数据异常"
        line_anomaly = True
    elif line_anomaly:
        status = "金额异常"

    order_doc = {
        "tenant_id": tenant_id,
        "order_no": order_no,
        "customer_id": customer.get("id") if customer else "",
        "customer_code": customer.get("customer_code", "") if customer else customer_code,
        "customer_name": customer.get("customer_name", "") if customer else customer_name,
        "order_date": order_date,
        "total_quantity": to_decimal128(total_quantity),
        "total_amount": to_decimal128(round_money(total_amount)),
        "status": status,
        "amount_mismatch": line_anomaly,
        "identity_conflict": identity_conflict,
        "import_batch_id": batch_id,
        "raw_data": records[0].get("__raw__", ""),
        "is_demo": bool(records[0].get("is_demo", False)),
        "created_at": _now(),
        "updated_at": _now(),
    }
    order_id = _orders.insert_order(db, order_doc, item_docs)
    if status in {"数据异常", "金额异常"}:
        _logs.add_error_log(
            db,
            {
                "tenant_id": tenant_id,
                "error_type": "order_anomaly",
                "batch_id": batch_id,
                "order_no": order_no,
                "message": "同一订单的客户/日期不一致" if identity_conflict else "订单明细金额与数量×单价不一致",
                "detail": {
                    "total_quantity": str(total_quantity),
                    "total_amount": str(total_amount),
                    "status": status,
                },
                "created_at": _now(),
            },
        )
    return {
        "status": "inserted",
        "order_id": order_id,
        "order_no": order_no,
        "order_status": status,
        "customer_matched": bool(customer),
        "message": "订单已导入" if status == "正常" else f"订单已导入，状态：{status}",
    }


def group_records_by_order(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[str(record.get("order_no") or "").strip()].append(record)
    grouped.pop("", None)
    return dict(grouped)


def list_orders(db: Database, **filters) -> list[dict[str, Any]]:
    return _orders.list(db, **filters)


def count_orders(db: Database, **filters) -> int:
    return _orders.count_list(db, **filters)


def get_order_detail(db: Database, order_id: str) -> dict[str, Any] | None:
    order = _orders.get(db, order_id)
    if not order:
        return None
    order["items"] = _orders.get_items(db, order_id)
    return order


def find_orders_by_no(db: Database, order_no: str, tenant_id: str = "default") -> list[dict[str, Any]]:
    return _orders.find_by_order_no(db, order_no, tenant_id)


def orders_for_product(db: Database, product_id: str, tenant_id: str = "default") -> list[str]:
    return _orders.order_nos_for_product(db, product_id, tenant_id)


def order_dataframe(orders: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for order in orders:
        rows.append(
            {
                "订单编号": order.get("order_no", ""),
                "客户编码": order.get("customer_code", ""),
                "客户名称": order.get("customer_name", ""),
                "订单日期": order.get("order_date", ""),
                "总数量": round_qty(order.get("total_quantity")),
                "总金额": round_money(order.get("total_amount")),
                "状态": order.get("status", ""),
                "导入批次": order.get("import_batch_id", ""),
                "创建时间": order.get("created_at", ""),
            }
        )
    return pd.DataFrame(
        rows,
        columns=["订单编号", "客户编码", "客户名称", "订单日期", "总数量", "总金额", "状态", "导入批次", "创建时间"],
    )


def order_detail_dataframe(order: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for item in order.get("items", []):
        rows.append(
            {
                "订单编号": order.get("order_no", ""),
                "客户名称": order.get("customer_name", ""),
                "商品编码": item.get("product_code", ""),
                "商品名称": item.get("product_name", ""),
                "商品规格": item.get("specification", ""),
                "单位": item.get("unit", ""),
                "数量": round_qty(item.get("quantity")),
                "单价": round_money(item.get("unit_price")),
                "金额": round_money(item.get("amount")),
                "金额异常": "是" if item.get("amount_mismatch") else "否",
            }
        )
    return pd.DataFrame(rows, columns=["订单编号", "客户名称", "商品编码", "商品名称", "商品规格", "单位", "数量", "单价", "金额", "金额异常"])


def all_order_details_dataframe(db: Database, tenant_id: str = "default", *, start_date: date | str | None = None, end_date: date | str | None = None, orders: list[dict[str, Any]] | None = None) -> pd.DataFrame:
    orders = orders if orders is not None else _orders.all_orders(db, tenant_id=tenant_id, start_date=start_date, end_date=end_date)
    rows = []
    for order in orders:
        items = _orders.get_items(db, order["id"])
        for item in items:
            rows.append(
                {
                    "订单编号": order.get("order_no", ""),
                    "订单日期": order.get("order_date", ""),
                    "客户编码": order.get("customer_code", ""),
                    "客户名称": order.get("customer_name", ""),
                    "商品编码": item.get("product_code", ""),
                    "商品名称": item.get("product_name", ""),
                    "商品规格": item.get("specification", ""),
                    "单位": item.get("unit", ""),
                    "数量": round_qty(item.get("quantity")),
                    "单价": round_money(item.get("unit_price")),
                    "金额": round_money(item.get("amount")),
                }
            )
    return pd.DataFrame(
        rows,
        columns=["订单编号", "订单日期", "客户编码", "客户名称", "商品编码", "商品名称", "商品规格", "单位", "数量", "单价", "金额"],
    )


def duplicate_orders_dataframe(db: Database, tenant_id: str = "default") -> pd.DataFrame:
    duplicates = _orders.duplicate_order_nos(db, tenant_id)
    rows = []
    for item in duplicates:
        order_no = item.get("_id", "")
        docs = _orders.find_by_order_no(db, order_no, tenant_id)
        rows.append(
            {
                "订单编号": order_no,
                "记录数": item.get("count", 0),
                "客户": "；".join(str(doc.get("customer_name", "")) for doc in docs),
                "总金额": "；".join(str(round_money(doc.get("total_amount"))) for doc in docs),
                "处理建议": "请人工确认保留哪一条，系统不会自动覆盖",
            }
        )
    return pd.DataFrame(rows, columns=["订单编号", "记录数", "客户", "总金额", "处理建议"])


def detect_anomalies(db: Database, tenant_id: str = "default") -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    orders = _orders.all_orders(db, tenant_id=tenant_id)
    counts: dict[str, int] = defaultdict(int)
    for order in orders:
        counts[str(order.get("order_no", ""))] += 1

    deliveries_by_order: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for delivery in db["delivery_records"].find({"tenant_id": tenant_id}):
        deliveries_by_order[str(delivery.get("order_no", ""))].append(delivery)

    for order in orders:
        order_no = str(order.get("order_no", ""))
        items = _orders.get_items(db, order["id"])
        if counts[order_no] > 1:
            rows.append({"异常类型": "重复订单", "订单编号": order_no, "商品": "", "说明": f"订单编号出现 {counts[order_no]} 次", "建议": "人工确认保留一条"})
        if not order.get("customer_id"):
            rows.append({"异常类型": "客户未匹配", "订单编号": order_no, "商品": "", "说明": order.get("customer_name", ""), "建议": "到客户匹配页处理"})
        if not order.get("order_date"):
            rows.append({"异常类型": "日期异常", "订单编号": order_no, "商品": "", "说明": "订单日期为空", "建议": "补录订单日期"})
        if not items:
            rows.append({"异常类型": "订单无明细", "订单编号": order_no, "商品": "", "说明": "未找到订单明细", "建议": "检查导入文件"})
        item_total = ZERO
        for item in items:
            item_total += to_decimal(item.get("amount"))
            if not item.get("product_id"):
                rows.append({"异常类型": "商品未匹配", "订单编号": order_no, "商品": item.get("product_name", ""), "说明": item.get("specification", ""), "建议": "到商品匹配页处理"})
            if item.get("amount_mismatch"):
                rows.append({"异常类型": "明细金额异常", "订单编号": order_no, "商品": item.get("product_name", ""), "说明": "金额 ≠ 数量 × 单价", "建议": "核对原始 Excel"})
            quantity = to_decimal(item.get("quantity"))
            amount = to_decimal(item.get("amount"))
            if quantity <= 0:
                rows.append({"异常类型": "数量异常", "订单编号": order_no, "商品": item.get("product_name", ""), "说明": "数量小于等于 0", "建议": "核对原始 Excel"})
            if amount < 0:
                rows.append({"异常类型": "金额异常", "订单编号": order_no, "商品": item.get("product_name", ""), "说明": "金额为负数", "建议": "核对原始 Excel"})
        if not amounts_equal(item_total, order.get("total_amount"), tolerance="0.01"):
            rows.append({"异常类型": "订单总额不一致", "订单编号": order_no, "商品": "", "说明": f"明细合计 {round_money(item_total)}，订单总额 {round_money(order.get('total_amount'))}", "建议": "重新计算或人工修正"})
        if order.get("amount_mismatch"):
            rows.append({"异常类型": "订单金额异常", "订单编号": order_no, "商品": "", "说明": "导入时存在金额不一致", "建议": "核对原始 Excel"})
        if order.get("identity_conflict"):
            rows.append({"异常类型": "订单信息冲突", "订单编号": order_no, "商品": "", "说明": "同一订单的客户或日期不一致", "建议": "拆分或修正原始数据"})

    for delivery in db["delivery_records"].find({"tenant_id": tenant_id}):
        order_no = str(delivery.get("order_no", ""))
        if not _orders.find_by_order_no(db, order_no, tenant_id):
            rows.append({"异常类型": "发货无对应订单", "订单编号": order_no, "商品": delivery.get("product_code", ""), "说明": f"发货单 {delivery.get('delivery_no','')}", "建议": "补录订单或核对发货单号"})

    return pd.DataFrame(rows, columns=["异常类型", "订单编号", "商品", "说明", "建议"])


def count_order_anomalies(db: Database, tenant_id: str = "default") -> int:
    anomalies = detect_anomalies(db, tenant_id)
    return int(len(anomalies))


def month_sales(db: Database, tenant_id: str = "default", *, today: date | None = None) -> tuple[Decimal, int]:
    today = today or date.today()
    start = today.replace(day=1).isoformat()
    end = today.isoformat()
    orders = _orders.all_orders(db, tenant_id=tenant_id, start_date=start, end_date=end)
    total = ZERO
    for order in orders:
        total += to_decimal(order.get("total_amount"))
    return round_money(total), len(orders)


def order_count(db: Database, tenant_id: str = "default") -> int:
    return _orders.count(db, tenant_id)


def order_date_range(db: Database, tenant_id: str = "default") -> tuple[date | None, date | None]:
    docs = list(db["sales_orders"].find({"tenant_id": tenant_id, "order_date": {"$ne": ""}}, {"order_date": 1}).sort("order_date", 1).limit(1))
    last = list(db["sales_orders"].find({"tenant_id": tenant_id, "order_date": {"$ne": ""}}, {"order_date": 1}).sort("order_date", -1).limit(1))
    first_date = None
    last_date = None
    try:
        if docs:
            from utils.validator import parse_date

            first_date = parse_date(docs[0].get("order_date"))
        if last:
            from utils.validator import parse_date

            last_date = parse_date(last[0].get("order_date"))
    except Exception:
        pass
    return first_date, last_date

