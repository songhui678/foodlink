"""订单管理：查询、筛选、明细、重复订单和异常检测。"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import customer_service, matching_service, order_service, product_service
from utils.decimal_utils import round_money, to_decimal
from utils.ui import (
    database_page,
    download_dataframe_button,
    empty_state,
    metric_row,
    page_header,
    paginated_table,
    show_error,
    setup_page,
)


setup_page("订单管理", "🧾")
page_header("订单管理", "按订单编号、客户、商品和日期查询订单，查看明细与异常。")


def _date_widget(label: str, key: str, start: date, end: date):
    value = st.date_input(label, value=(start, end), key=key)
    if isinstance(value, tuple) and len(value) == 2:
        return value[0], value[1]
    if isinstance(value, tuple) and len(value) == 1:
        return value[0], value[0]
    return value, value


with database_page() as db:
    tenant_id = "default"
    first_order_date, last_order_date = order_service.order_date_range(db, tenant_id)
    today = date.today()
    default_start = first_order_date or today.replace(month=1, day=1)
    default_end = last_order_date or today

    customers = customer_service.customer_options(db, tenant_id)
    products = product_service.product_options(db, tenant_id)
    customer_options = {item["customer_name"]: item["id"] for item in customers}
    product_options = {f"{item.get('product_name')} / {item.get('specification') or '无规格'}": item["id"] for item in products}

    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
    search = col1.text_input("搜索订单编号 / 客户编码 / 客户名称", key="order_search")
    status = col2.selectbox("订单状态", ["全部", "正常", "待匹配", "金额异常", "数据异常"], key="order_status_filter")
    customer_name = col3.selectbox("客户筛选", ["全部", *customer_options.keys()], key="order_customer_filter")
    product_label = col4.selectbox("商品筛选", ["全部", *product_options.keys()], key="order_product_filter")
    start_date, end_date = _date_widget("订单日期范围", "order_date_range", default_start, default_end)

    if start_date > end_date:
        st.warning("开始日期不能晚于结束日期，已自动交换。")
        start_date, end_date = end_date, start_date

    order_nos = None
    if product_label != "全部":
        order_nos = order_service.orders_for_product(db, product_options[product_label], tenant_id)
        if not order_nos:
            order_nos = ["__NO_MATCH__"]

    filters = {
        "tenant_id": tenant_id,
        "search": search,
        "start_date": start_date,
        "end_date": end_date,
        "status": "" if status == "全部" else status,
        "customer_id": customer_options.get(customer_name, ""),
        "order_nos": order_nos,
        "skip": 0,
        "limit": 10000,
    }
    orders = order_service.list_orders(db, **filters)
    total_amount = sum((to_decimal(item.get("total_amount")) for item in orders), to_decimal(0))
    metric_row(
        [
            ("订单数量", len(orders), None),
            ("订单总金额", f"¥ {round_money(total_amount):,.2f}", None),
            ("待匹配", len([item for item in orders if item.get("status") == "待匹配"]), None),
            ("异常订单", len([item for item in orders if item.get("status") in {"金额异常", "数据异常"}]), None),
        ]
    )
    st.divider()

    tab_list, tab_detail, tab_anomaly = st.tabs(["订单列表", "订单详情", "重复订单与异常"])

    with tab_list:
        df = order_service.order_dataframe(orders)
        paginated_table(
            df,
            key="order_table",
            page_size=20,
            search_columns=["订单编号", "客户编码", "客户名称", "状态"],
            search_label="在当前结果中筛选",
        )

    with tab_detail:
        if not orders:
            empty_state("当前筛选条件下没有订单。")
        else:
            order_map = {item["id"]: item for item in orders}
            selected_id = st.selectbox(
                "选择订单",
                list(order_map.keys()),
                format_func=lambda value: f"{order_map[value].get('order_no')}｜{order_map[value].get('customer_name')}｜¥{round_money(order_map[value].get('total_amount')):,.2f}",
                key="order_detail_select",
            )
            detail = order_service.get_order_detail(db, selected_id)
            if not detail:
                empty_state("订单不存在。")
            else:
                info1, info2, info3 = st.columns(3)
                info1.write({"订单编号": detail.get("order_no"), "订单日期": detail.get("order_date"), "状态": detail.get("status")})
                info2.write({"客户编码": detail.get("customer_code"), "客户名称": detail.get("customer_name"), "客户ID": detail.get("customer_id") or "未匹配"})
                info3.write({"总数量": detail.get("total_quantity"), "总金额": round_money(detail.get("total_amount")), "导入批次": detail.get("import_batch_id")})
                detail_df = order_service.order_detail_dataframe(detail)
                st.dataframe(detail_df, use_container_width=True, hide_index=True)
                download_dataframe_button(
                    detail_df,
                    label="导出该订单明细",
                    filename=f"订单_{detail.get('order_no')}.xlsx",
                    key="download_order_detail",
                    sheet_name="订单明细",
                    title=f"订单 {detail.get('order_no')} 明细",
                )
                if detail.get("status") == "待匹配":
                    st.info("该订单存在未匹配的客户或商品，请到“客户匹配”或“商品匹配”页面人工确认。")
                    if st.button("刷新匹配日志", key="order_refresh_matching"):
                        created = matching_service.refresh_matching_logs(db, tenant_id=tenant_id)
                        st.success(f"已新增 {created} 条匹配日志。")

    with tab_anomaly:
        duplicates = order_service.duplicate_orders_dataframe(db, tenant_id)
        st.markdown("**重复订单编号**")
        if duplicates.empty:
            st.success("没有发现重复订单编号。")
        else:
            st.dataframe(duplicates, use_container_width=True, hide_index=True)
        st.markdown("**异常数据检测**")
        if st.button("重新检测异常", key="detect_order_anomalies"):
            st.session_state["order_anomalies"] = order_service.detect_anomalies(db, tenant_id)
        if "order_anomalies" not in st.session_state:
            st.session_state["order_anomalies"] = order_service.detect_anomalies(db, tenant_id)
        anomaly_df = st.session_state["order_anomalies"]
        if anomaly_df.empty:
            st.success("没有发现订单异常。")
        else:
            st.dataframe(anomaly_df, use_container_width=True, hide_index=True)
            download_dataframe_button(
                anomaly_df,
                label="导出异常订单 Excel",
                filename="食链通_订单异常.xlsx",
                key="download_order_anomalies",
                sheet_name="订单异常",
                title="食链通订单异常报表",
            )

