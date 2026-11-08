"""Excel 报表生成与下载。"""

from __future__ import annotations

from datetime import date
from typing import Any, Iterable

import pandas as pd
from pymongo.database import Database

from services import analysis_service, customer_service, delivery_service, import_service, matching_service, order_service, product_service
from utils.excel_utils import dataframe_to_excel_bytes, workbook_to_bytes


REPORT_TYPES: dict[str, str] = {
    "客户资料报表": "customer",
    "商品资料报表": "product",
    "订单明细报表": "order_detail",
    "销售汇总报表": "sales_summary",
    "客户销售排行榜": "customer_rank",
    "商品销售排行榜": "product_rank",
    "订单发货核对报表": "reconciliation",
    "未匹配客户报表": "unmatched_customer",
    "未匹配商品报表": "unmatched_product",
    "数据异常报表": "anomalies",
    "导入错误报告": "import_errors",
}


def _customer_report(db: Database, tenant_id: str) -> pd.DataFrame:
    customers = customer_service.customer_options(db, tenant_id)
    return customer_service.customer_dataframe(customers)


def _product_report(db: Database, tenant_id: str) -> pd.DataFrame:
    products = product_service.product_options(db, tenant_id)
    return product_service.product_dataframe(products)


def _sales_rows(db: Database, tenant_id: str, filters: dict[str, Any]) -> pd.DataFrame:
    return analysis_service.load_sales_rows(
        db,
        tenant_id=tenant_id,
        start_date=filters.get("start_date"),
        end_date=filters.get("end_date"),
        customer_ids=filters.get("customer_ids"),
        product_ids=filters.get("product_ids"),
        region=filters.get("region", ""),
    )


def build_report(db: Database, report_key: str, *, tenant_id: str = "default", filters: dict[str, Any] | None = None) -> list[tuple[str, pd.DataFrame]]:
    filters = filters or {}
    if report_key == "customer":
        return [("客户资料", _customer_report(db, tenant_id))]
    if report_key == "product":
        return [("商品资料", _product_report(db, tenant_id))]
    if report_key == "order_detail":
        orders = order_service.list_orders(
            db,
            tenant_id=tenant_id,
            start_date=filters.get("start_date"),
            end_date=filters.get("end_date"),
            limit=100000,
        )
        return [("订单明细", order_service.all_order_details_dataframe(db, tenant_id, orders=orders))]
    if report_key == "sales_summary":
        rows = _sales_rows(db, tenant_id, filters)
        monthly = analysis_service.monthly_sales(rows)
        region = analysis_service.region_ranking(rows)
        summary = pd.DataFrame(
            [analysis_service.overview(rows)]
        ).rename(columns={"销售额": "销售额合计", "订单数": "订单数量", "客户数": "客户数量", "商品数": "商品数量", "数量": "销售数量", "客单价": "平均订单金额"})
        return [("销售总览", summary), ("月度趋势", monthly), ("区域销售", region)]
    if report_key == "customer_rank":
        rows = _sales_rows(db, tenant_id, filters)
        return [("客户销售排行榜", analysis_service.customer_ranking(rows, limit=1000))]
    if report_key == "product_rank":
        rows = _sales_rows(db, tenant_id, filters)
        return [("商品销售排行榜", analysis_service.product_ranking(rows, limit=1000))]
    if report_key == "reconciliation":
        detail, summary, orders = delivery_service.reconcile(
            db,
            tenant_id=tenant_id,
            start_date=filters.get("start_date"),
            end_date=filters.get("end_date"),
        )
        summary_df = pd.DataFrame([{"核对结果": key, "数量": value} for key, value in summary.items()])
        return [("核对汇总", summary_df), ("明细核对", detail), ("订单核对", orders)]
    if report_key in {"unmatched_customer", "unmatched_product"}:
        entity = "customer" if report_key == "unmatched_customer" else "product"
        logs = matching_service.list_matching_logs(
            db,
            entity_type=entity,
            status="",
            tenant_id=tenant_id,
            limit=5000,
        )
        logs = [item for item in logs if not item.get("resolved") and item.get("status") != "ignored"]
        df = matching_service.log_to_dataframe(logs)
        return [("未匹配客户" if entity == "customer" else "未匹配商品", df)]
    if report_key == "anomalies":
        orders = order_service.detect_anomalies(db, tenant_id)
        detail, _, _ = delivery_service.reconcile(
            db,
            tenant_id=tenant_id,
            start_date=filters.get("start_date"),
            end_date=filters.get("end_date"),
        )
        delivery_issues = detail[detail["核对结果"].isin(["订单不存在", "商品不匹配", "客户不匹配", "数据异常"])].copy() if not detail.empty else detail
        delivery_issues = delivery_issues.rename(columns={"核对结果": "异常类型", "说明": "说明"})
        return [("订单异常", orders), ("发货异常", delivery_issues)]
    if report_key == "import_errors":
        return [("导入错误", import_service.import_error_dataframe(db, tenant_id=tenant_id))]
    raise ValueError("未知的报表类型")


def export_report_bytes(db: Database, report_key: str, *, tenant_id: str = "default", filters: dict[str, Any] | None = None) -> tuple[bytes, str]:
    sheets = build_report(db, report_key, tenant_id=tenant_id, filters=filters)
    label = next((name for name, key in REPORT_TYPES.items() if key == report_key), report_key)
    content = workbook_to_bytes(sheets, title=f"食链通 {label}")
    filename = f"{label}_{date.today().strftime('%Y%m%d')}.xlsx"
    return content, filename


def preview_report(db: Database, report_key: str, *, tenant_id: str = "default", filters: dict[str, Any] | None = None) -> tuple[list[str], pd.DataFrame]:
    sheets = build_report(db, report_key, tenant_id=tenant_id, filters=filters)
    names = [name for name, _ in sheets]
    return names, (sheets[0][1] if sheets else pd.DataFrame())

