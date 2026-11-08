"""发货管理与订单发货核对。"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

import pandas as pd
from pymongo.database import Database

from database.repositories.delivery_repository import DeliveryRepository
from database.repositories.order_repository import OrderRepository
from utils.decimal_utils import ZERO, amounts_equal, round_qty, to_decimal, to_decimal128


_deliveries = DeliveryRepository()
_orders = OrderRepository()


RECON_LABELS = {
    "full": "已全部发货",
    "partial": "部分发货",
    "over": "超量发货",
    "none": "未发货",
    "order_missing": "订单不存在",
    "product_mismatch": "商品不匹配",
    "customer_mismatch": "客户不匹配",
    "abnormal": "数据异常",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def import_delivery_record(
    db: Database,
    record: dict[str, Any],
    *,
    batch_id: str,
    tenant_id: str = "default",
) -> tuple[str, str]:
    delivery_no = str(record.get("delivery_no") or "").strip()
    if not delivery_no:
        return "skipped", "发货单号为空"
    if to_decimal(record.get("quantity")) <= 0:
        return "skipped", "发货数量必须大于 0"
    existing = _deliveries.find_by_delivery_no(db, delivery_no, tenant_id)
    if existing:
        return "duplicate", f"发货单号“{delivery_no}”已存在，已跳过"
    doc = {
        "tenant_id": tenant_id,
        "delivery_no": delivery_no,
        "order_no": str(record.get("order_no") or "").strip(),
        "customer_code": str(record.get("customer_code") or "").strip(),
        "product_code": str(record.get("product_code") or "").strip(),
        "delivery_date": record.get("delivery_date").isoformat() if hasattr(record.get("delivery_date"), "isoformat") else str(record.get("delivery_date") or ""),
        "quantity": to_decimal128(round_qty(record.get("quantity"))),
        "import_batch_id": batch_id,
        "raw_data": record.get("__raw__", ""),
        "is_demo": bool(record.get("is_demo", False)),
        "created_at": _now(),
    }
    _deliveries.insert_one(db, doc)
    return "inserted", str(delivery_no)


def list_deliveries(db: Database, **filters) -> list[dict[str, Any]]:
    return _deliveries.list(db, **filters)


def count_deliveries(db: Database, **filters) -> int:
    return _deliveries.count_list(db, **filters)


def delivery_dataframe(deliveries: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for item in deliveries:
        rows.append(
            {
                "发货单号": item.get("delivery_no", ""),
                "订单编号": item.get("order_no", ""),
                "客户编码": item.get("customer_code", ""),
                "商品编码": item.get("product_code", ""),
                "发货日期": item.get("delivery_date", ""),
                "发货数量": round_qty(item.get("quantity")),
                "导入批次": item.get("import_batch_id", ""),
                "创建时间": item.get("created_at", ""),
            }
        )
    return pd.DataFrame(rows, columns=["发货单号", "订单编号", "客户编码", "商品编码", "发货日期", "发货数量", "导入批次", "创建时间"])


def reconcile(
    db: Database,
    *,
    tenant_id: str = "default",
    start_date: date | str | None = None,
    end_date: date | str | None = None,
    order_no: str = "",
) -> tuple[pd.DataFrame, dict[str, int], pd.DataFrame]:
    """返回 (明细核对表, 汇总统计, 订单级核对表)。"""

    orders = _orders.all_orders(db, tenant_id=tenant_id, start_date=start_date, end_date=end_date)
    if order_no:
        orders = [item for item in orders if item.get("order_no") == order_no]
    order_nos = {str(item.get("order_no")) for item in orders}
    all_deliveries = _deliveries.all_records(db, tenant_id)
    all_order_nos = {str(item.get("order_no")) for item in _orders.all_orders(db, tenant_id=tenant_id)}
    if order_no:
        deliveries = [item for item in all_deliveries if str(item.get("order_no")) == order_no]
    elif start_date or end_date:
        # 日期筛选只用于选择订单；仍保留“订单不存在”的发货记录用于异常核对
        deliveries = [
            item
            for item in all_deliveries
            if str(item.get("order_no")) in order_nos or str(item.get("order_no")) not in all_order_nos
        ]
    else:
        deliveries = all_deliveries

    duplicate_delivery_nos: set[str] = set()
    delivery_no_counts: dict[str, int] = defaultdict(int)
    for item in all_deliveries:
        delivery_no_counts[str(item.get("delivery_no", ""))] += 1
    duplicate_delivery_nos = {key for key, count in delivery_no_counts.items() if count > 1}

    order_map: dict[str, dict[str, Any]] = {}
    items_by_order: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for order in orders:
        order_map[str(order.get("order_no"))] = order
        items_by_order[str(order.get("order_no"))].extend(_orders.get_items(db, order["id"]))

    delivered: dict[tuple[str, str], Decimal] = defaultdict(lambda: ZERO)
    delivery_count: dict[tuple[str, str], int] = defaultdict(int)
    delivery_nos: dict[tuple[str, str], list[str]] = defaultdict(list)
    for item in deliveries:
        key = (str(item.get("order_no", "")), str(item.get("product_code", "")))
        delivered[key] += to_decimal(item.get("quantity"))
        delivery_count[key] += 1
        delivery_nos[key].append(str(item.get("delivery_no", "")))

    rows: list[dict[str, Any]] = []
    seen_order_products: set[tuple[str, str]] = set()
    for order in orders:
        order_no_value = str(order.get("order_no", ""))
        order_customer = str(order.get("customer_code", ""))
        order_items = items_by_order.get(order_no_value, [])
        if not order_items:
            rows.append(
                {
                    "订单编号": order_no_value,
                    "客户编码": order_customer,
                    "商品编码": "",
                    "商品名称": "",
                    "商品规格": "",
                    "订单日期": order.get("order_date", ""),
                    "订单数量": Decimal("0"),
                    "发货数量": Decimal("0"),
                    "差异数量": Decimal("0"),
                    "发货次数": 0,
                    "核对结果": "数据异常",
                    "说明": "订单没有明细数据",
                }
            )
            continue
        for item in order_items:
            product_code = str(item.get("product_code", ""))
            key = (order_no_value, product_code)
            seen_order_products.add(key)
            order_qty = to_decimal(item.get("quantity"))
            delivery_qty = to_decimal(delivered.get(key, ZERO))
            diff = delivery_qty - order_qty
            result = "已全部发货"
            message = ""
            if duplicate_delivery_nos & set(delivery_nos.get(key, [])):
                result = "数据异常"
                message = "存在重复发货单号"
            elif order_qty == delivery_qty:
                result = "已全部发货"
            elif delivery_qty == 0:
                result = "未发货"
            elif delivery_qty < order_qty:
                result = "部分发货"
            else:
                result = "超量发货"
            if delivery_count.get(key, 0) > 1:
                message = (message + "；" if message else "") + f"该订单商品分 {delivery_count[key]} 次发货"
            rows.append(
                {
                    "订单编号": order_no_value,
                    "客户编码": order_customer,
                    "商品编码": product_code,
                    "商品名称": item.get("product_name", ""),
                    "商品规格": item.get("specification", ""),
                    "订单日期": order.get("order_date", ""),
                    "订单数量": round_qty(order_qty),
                    "发货数量": round_qty(delivery_qty),
                    "差异数量": round_qty(diff),
                    "发货次数": delivery_count.get(key, 0),
                    "核对结果": result,
                    "说明": message,
                }
            )

    # 发货存在、订单不存在
    missing_order_deliveries = [item for item in deliveries if str(item.get("order_no")) not in order_map]
    for item in missing_order_deliveries:
        rows.append(
            {
                "订单编号": item.get("order_no", ""),
                "客户编码": item.get("customer_code", ""),
                "商品编码": item.get("product_code", ""),
                "商品名称": "",
                "商品规格": "",
                "订单日期": "",
                "订单数量": Decimal("0"),
                "发货数量": round_qty(item.get("quantity")),
                "差异数量": round_qty(item.get("quantity")),
                "发货次数": 1,
                "核对结果": "订单不存在",
                "说明": f"发货单 {item.get('delivery_no','')} 找不到对应订单",
            }
        )

    # 发货存在、商品不在订单中
    for item in deliveries:
        note = ""
        order = order_map.get(str(item.get("order_no", "")))
        if order is not None:
            key = (str(item.get("order_no", "")), str(item.get("product_code", "")))
            if key not in seen_order_products:
                note = f"商品 {item.get('product_code','')} 不在订单明细中"
            elif order.get("customer_code") and item.get("customer_code") and order.get("customer_code") != item.get("customer_code"):
                note = "发货客户编码与订单客户编码不一致"
        if note:
            rows.append(
                {
                    "订单编号": item.get("order_no", ""),
                    "客户编码": item.get("customer_code", ""),
                    "商品编码": item.get("product_code", ""),
                    "商品名称": "",
                    "商品规格": "",
                    "订单日期": order.get("order_date", "") if order else "",
                    "订单数量": Decimal("0"),
                    "发货数量": round_qty(item.get("quantity")),
                    "差异数量": round_qty(item.get("quantity")),
                    "发货次数": 1,
                    "核对结果": "商品不匹配" if "商品" in note else "客户不匹配",
                    "说明": note,
                }
            )

    detail_df = pd.DataFrame(
        rows,
        columns=["订单编号", "客户编码", "商品编码", "商品名称", "商品规格", "订单日期", "订单数量", "发货数量", "差异数量", "发货次数", "核对结果", "说明"],
    )
    summary = {
        "已全部发货": int((detail_df["核对结果"] == "已全部发货").sum()) if not detail_df.empty else 0,
        "部分发货": int((detail_df["核对结果"] == "部分发货").sum()) if not detail_df.empty else 0,
        "超量发货": int((detail_df["核对结果"] == "超量发货").sum()) if not detail_df.empty else 0,
        "未发货": int((detail_df["核对结果"] == "未发货").sum()) if not detail_df.empty else 0,
        "异常": int(detail_df["核对结果"].isin(["订单不存在", "商品不匹配", "客户不匹配", "数据异常"]).sum()) if not detail_df.empty else 0,
    }
    order_df = _order_level_reconciliation(detail_df)
    return detail_df, summary, order_df


def _order_level_reconciliation(detail_df: pd.DataFrame) -> pd.DataFrame:
    if detail_df.empty:
        return pd.DataFrame(columns=["订单编号", "客户编码", "订单日期", "明细数", "订单数量", "发货数量", "订单核对结果", "说明"])
    rows = []
    for order_no, group in detail_df.groupby("订单编号", dropna=False):
        results = set(group["核对结果"].tolist())
        if "订单不存在" in results:
            status = "订单不存在"
        elif "商品不匹配" in results or "客户不匹配" in results:
            status = "数据不匹配"
        elif "数据异常" in results:
            status = "数据异常"
        elif "超量发货" in results:
            status = "超量发货"
        elif "部分发货" in results or "未发货" in results:
            status = "部分发货"
        else:
            status = "已全部发货"
        rows.append(
            {
                "订单编号": order_no,
                "客户编码": group["客户编码"].iloc[0],
                "订单日期": group["订单日期"].iloc[0],
                "明细数": len(group),
                "订单数量": sum((to_decimal(value) for value in group["订单数量"]), ZERO),
                "发货数量": sum((to_decimal(value) for value in group["发货数量"]), ZERO),
                "订单核对结果": status,
                "说明": "；".join(sorted({str(item) for item in group["说明"].tolist() if item})),
            }
        )
    return pd.DataFrame(rows, columns=["订单编号", "客户编码", "订单日期", "明细数", "订单数量", "发货数量", "订单核对结果", "说明"])


def count_pending_delivery_issues(db: Database, tenant_id: str = "default") -> int:
    detail, _, _ = reconcile(db, tenant_id=tenant_id)
    if detail.empty:
        return 0
    return int((detail["核对结果"] != "已全部发货").sum())


def duplicate_deliveries_dataframe(db: Database, tenant_id: str = "default") -> pd.DataFrame:
    rows = []
    for item in _deliveries.duplicate_delivery_nos(db, tenant_id):
        rows.append({"发货单号": item.get("_id", ""), "记录数": item.get("count", 0), "订单编号": "；".join(item.get("order_nos", []))})
    return pd.DataFrame(rows, columns=["发货单号", "记录数", "订单编号"])

