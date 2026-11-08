"""销售分析：趋势、排行榜、增长与异常。"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Iterable

import pandas as pd
from pymongo.database import Database

from database.repositories.customer_repository import CustomerRepository
from database.repositories.order_repository import OrderRepository
from database.repositories.product_repository import ProductRepository
from services import order_service
from utils.decimal_utils import ZERO, round_money, round_qty, to_decimal


_orders = OrderRepository()
_customers = CustomerRepository()
_products = ProductRepository()


def _date_text(value: Any) -> str:
    return value.isoformat() if isinstance(value, date) else str(value or "")


def load_sales_rows(
    db: Database,
    *,
    tenant_id: str = "default",
    start_date: date | None = None,
    end_date: date | None = None,
    customer_ids: Iterable[str] | None = None,
    product_ids: Iterable[str] | None = None,
    region: str = "",
) -> pd.DataFrame:
    customers = {item["id"]: item for item in _customers.all_active(db, tenant_id)}
    products = {item["id"]: item for item in _products.all_active(db, tenant_id)}
    customer_filter = set(customer_ids or [])
    product_filter = set(product_ids or [])
    orders = _orders.all_orders(
        db,
        tenant_id=tenant_id,
        start_date=start_date,
        end_date=end_date,
    )
    rows: list[dict[str, Any]] = []
    for order in orders:
        customer = customers.get(order.get("customer_id", ""), {})
        order_region = customer.get("region", "") or "未填写区域"
        if customer_filter and order.get("customer_id") not in customer_filter:
            continue
        if region and order_region != region:
            continue
        for item in _orders.get_items(db, order["id"]):
            if product_filter and item.get("product_id") not in product_filter:
                continue
            product = products.get(item.get("product_id", ""), {})
            rows.append(
                {
                    "order_no": order.get("order_no", ""),
                    "order_date": order.get("order_date", ""),
                    "month": str(order.get("order_date", ""))[:7],
                    "customer_id": order.get("customer_id", ""),
                    "customer_code": order.get("customer_code", ""),
                    "customer_name": order.get("customer_name", ""),
                    "region": order_region,
                    "product_id": item.get("product_id", ""),
                    "product_code": item.get("product_code", ""),
                    "product_name": item.get("product_name", ""),
                    "specification": item.get("specification", ""),
                    "category": product.get("category", "") or "未分类",
                    "quantity": to_decimal(item.get("quantity")),
                    "amount": to_decimal(item.get("amount")),
                }
            )
    return pd.DataFrame(
        rows,
        columns=["order_no", "order_date", "month", "customer_id", "customer_code", "customer_name",
                 "region", "product_id", "product_code", "product_name", "specification",
                 "category", "quantity", "amount"],
    )


def monthly_sales(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty:
        return pd.DataFrame(columns=["月份", "销售额", "订单数"])
    grouped: dict[str, dict[str, Any]] = {}
    for _, row in rows.iterrows():
        month = str(row.get("month", ""))
        item = grouped.setdefault(month, {"amount": ZERO, "orders": set()})
        item["amount"] += to_decimal(row.get("amount"))
        item["orders"].add(str(row.get("order_no", "")))
    result = [{"月份": month, "销售额": float(round_money(item["amount"])), "订单数": len(item["orders"])} for month, item in grouped.items()]
    return pd.DataFrame(result).sort_values("月份").reset_index(drop=True)


def customer_ranking(rows: pd.DataFrame, limit: int = 20) -> pd.DataFrame:
    if rows.empty:
        return pd.DataFrame(columns=["客户编码", "客户名称", "区域", "销售额", "订单数", "商品数量"])
    grouped: dict[str, dict[str, Any]] = {}
    for _, row in rows.iterrows():
        key = str(row.get("customer_id") or row.get("customer_name") or "未匹配客户")
        item = grouped.setdefault(
            key,
            {"code": row.get("customer_code", ""), "name": row.get("customer_name", "") or "未匹配客户",
             "region": row.get("region", ""), "amount": ZERO, "orders": set(), "quantity": ZERO},
        )
        item["amount"] += to_decimal(row.get("amount"))
        item["orders"].add(str(row.get("order_no", "")))
        item["quantity"] += to_decimal(row.get("quantity"))
    result = [
        {"客户编码": item["code"], "客户名称": item["name"], "区域": item["region"],
         "销售额": float(round_money(item["amount"])), "订单数": len(item["orders"]),
         "商品数量": float(round_qty(item["quantity"])), "客户ID": key}
        for key, item in grouped.items()
    ]
    df = pd.DataFrame(result)
    return df.sort_values("销售额", ascending=False).head(limit).reset_index(drop=True)


def product_ranking(rows: pd.DataFrame, limit: int = 20) -> pd.DataFrame:
    if rows.empty:
        return pd.DataFrame(columns=["商品编码", "商品名称", "商品规格", "分类", "销售额", "销售数量"])
    grouped: dict[str, dict[str, Any]] = {}
    for _, row in rows.iterrows():
        key = str(row.get("product_id") or row.get("product_name") or "未匹配商品")
        item = grouped.setdefault(
            key,
            {"code": row.get("product_code", ""), "name": row.get("product_name", "") or "未匹配商品",
             "spec": row.get("specification", ""), "category": row.get("category", ""),
             "amount": ZERO, "quantity": ZERO},
        )
        item["amount"] += to_decimal(row.get("amount"))
        item["quantity"] += to_decimal(row.get("quantity"))
    result = [
        {"商品编码": item["code"], "商品名称": item["name"], "商品规格": item["spec"],
         "分类": item["category"], "销售额": float(round_money(item["amount"])),
         "销售数量": float(round_qty(item["quantity"])), "商品ID": key}
        for key, item in grouped.items()
    ]
    df = pd.DataFrame(result)
    return df.sort_values("销售额", ascending=False).head(limit).reset_index(drop=True)


def region_ranking(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty:
        return pd.DataFrame(columns=["区域", "销售额", "订单数"])
    grouped: dict[str, dict[str, Any]] = {}
    for _, row in rows.iterrows():
        key = str(row.get("region") or "未填写区域")
        item = grouped.setdefault(key, {"amount": ZERO, "orders": set()})
        item["amount"] += to_decimal(row.get("amount"))
        item["orders"].add(str(row.get("order_no", "")))
    result = [{"区域": key, "销售额": float(round_money(item["amount"])), "订单数": len(item["orders"])} for key, item in grouped.items()]
    return pd.DataFrame(result).sort_values("销售额", ascending=False).reset_index(drop=True)


def customer_detail(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty:
        return pd.DataFrame(columns=["月份", "客户编码", "客户名称", "区域", "销售额", "订单数"])
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for _, row in rows.iterrows():
        key = (str(row.get("month", "")), str(row.get("customer_id") or row.get("customer_name")))
        item = grouped.setdefault(
            key,
            {"month": key[0], "code": row.get("customer_code", ""), "name": row.get("customer_name", ""),
             "region": row.get("region", ""), "amount": ZERO, "orders": set()},
        )
        item["amount"] += to_decimal(row.get("amount"))
        item["orders"].add(str(row.get("order_no", "")))
    result = [
        {"月份": item["month"], "客户编码": item["code"], "客户名称": item["name"], "区域": item["region"],
         "销售额": float(round_money(item["amount"])), "订单数": len(item["orders"])}
        for item in grouped.values()
    ]
    return pd.DataFrame(result).sort_values(["月份", "销售额"], ascending=[True, False]).reset_index(drop=True)


def product_detail(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty:
        return pd.DataFrame(columns=["月份", "商品编码", "商品名称", "商品规格", "销售额", "销售数量"])
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for _, row in rows.iterrows():
        key = (str(row.get("month", "")), str(row.get("product_id") or row.get("product_name")))
        item = grouped.setdefault(
            key,
            {"month": key[0], "code": row.get("product_code", ""), "name": row.get("product_name", ""),
             "spec": row.get("specification", ""), "amount": ZERO, "quantity": ZERO},
        )
        item["amount"] += to_decimal(row.get("amount"))
        item["quantity"] += to_decimal(row.get("quantity"))
    result = [
        {"月份": item["month"], "商品编码": item["code"], "商品名称": item["name"], "商品规格": item["spec"],
         "销售额": float(round_money(item["amount"])), "销售数量": float(round_qty(item["quantity"]))}
        for item in grouped.values()
    ]
    return pd.DataFrame(result).sort_values(["月份", "销售额"], ascending=[True, False]).reset_index(drop=True)


def overview(rows: pd.DataFrame) -> dict[str, Any]:
    if rows.empty:
        return {"销售额": 0.0, "订单数": 0, "客户数": 0, "商品数": 0, "数量": 0.0, "客单价": 0.0}
    total_amount = sum((to_decimal(value) for value in rows["amount"].tolist()), ZERO)
    total_qty = sum((to_decimal(value) for value in rows["quantity"].tolist()), ZERO)
    order_count = rows["order_no"].nunique()
    customer_count = rows["customer_id"].replace("", pd.NA).dropna().nunique()
    product_count = rows["product_id"].replace("", pd.NA).dropna().nunique()
    average = total_amount / order_count if order_count else ZERO
    return {
        "销售额": float(round_money(total_amount)),
        "订单数": int(order_count),
        "客户数": int(customer_count),
        "商品数": int(product_count),
        "数量": float(round_qty(total_qty)),
        "客单价": float(round_money(average)),
    }


def growth_analysis(
    db: Database,
    *,
    tenant_id: str = "default",
    start_date: date,
    end_date: date,
    customer_ids: Iterable[str] | None = None,
    product_ids: Iterable[str] | None = None,
    region: str = "",
) -> dict[str, Any]:
    current = load_sales_rows(
        db, tenant_id=tenant_id, start_date=start_date, end_date=end_date,
        customer_ids=customer_ids, product_ids=product_ids, region=region,
    )
    days = max(1, (end_date - start_date).days + 1)
    previous_end = start_date - timedelta(days=1)
    previous_start = previous_end - timedelta(days=days - 1)
    previous = load_sales_rows(
        db, tenant_id=tenant_id, start_date=previous_start, end_date=previous_end,
        customer_ids=customer_ids, product_ids=product_ids, region=region,
    )
    current_total = sum((to_decimal(value) for value in current["amount"].tolist()), ZERO) if not current.empty else ZERO
    previous_total = sum((to_decimal(value) for value in previous["amount"].tolist()), ZERO) if not previous.empty else ZERO
    change = current_total - previous_total
    rate = (change / previous_total * 100) if previous_total else (Decimal("100") if current_total else ZERO)
    return {
        "本期开始": start_date,
        "本期结束": end_date,
        "上期开始": previous_start,
        "上期结束": previous_end,
        "本期销售额": round_money(current_total),
        "上期销售额": round_money(previous_total),
        "增长额": round_money(change),
        "增长率": round(float(rate), 2),
        "本期订单数": int(current["order_no"].nunique()) if not current.empty else 0,
        "上期订单数": int(previous["order_no"].nunique()) if not previous.empty else 0,
    }


def sales_anomalies(db: Database, rows: pd.DataFrame, tenant_id: str = "default") -> pd.DataFrame:
    anomalies = order_service.detect_anomalies(db, tenant_id)
    if anomalies.empty or rows.empty:
        return anomalies
    order_nos = set(rows["order_no"].astype(str).tolist())
    return anomalies[anomalies["订单编号"].astype(str).isin(order_nos)].reset_index(drop=True)

