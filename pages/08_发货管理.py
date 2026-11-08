"""发货管理：发货记录查询、手工补录、重复发货检查与导出。"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import delivery_service, order_service
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


setup_page("发货管理", "🚚")
page_header("发货管理", "查询发货记录，一个订单可对应多张发货单。")


with database_page() as db:
    tenant_id = "default"
    first_date, last_date = order_service.order_date_range(db, tenant_id)
    today = date.today()
    default_start = first_date or today.replace(month=1, day=1)
    default_end = last_date or today

    col1, col2, col3 = st.columns([2, 2, 1])
    search = col1.text_input("搜索发货单号 / 订单编号 / 客户编码 / 商品编码", key="delivery_search")
    date_range = col2.date_input("发货日期范围", value=(default_start, default_end), key="delivery_date_range")
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
    elif isinstance(date_range, tuple) and len(date_range) == 1:
        start_date = end_date = date_range[0]
    else:
        start_date = end_date = date_range
    order_no_filter = col3.text_input("订单编号", key="delivery_order_filter")

    deliveries = delivery_service.list_deliveries(
        db,
        tenant_id=tenant_id,
        search=search,
        order_no=order_no_filter,
        start_date=start_date,
        end_date=end_date,
        skip=0,
        limit=10000,
    )
    metric_row(
        [
            ("发货记录", len(deliveries), None),
            ("涉及订单", len({item.get("order_no") for item in deliveries}), None),
            ("涉及客户", len({item.get("customer_code") for item in deliveries if item.get("customer_code")}), None),
            ("发货总数量", sum(float(item.get("quantity") or 0) for item in deliveries), None),
        ]
    )
    st.divider()

    tab_list, tab_add, tab_export = st.tabs(["发货记录", "手工补录", "导出与检查"])
    with tab_list:
        paginated_table(
            delivery_service.delivery_dataframe(deliveries),
            key="delivery_table",
            page_size=20,
            search_columns=["发货单号", "订单编号", "客户编码", "商品编码"],
            search_label="在当前结果中筛选",
        )
    with tab_add:
        st.caption("手工补录仅用于少量漏录数据；批量发货请使用“数据导入”。")
        with st.form("add_delivery_form", clear_on_submit=True):
            a, b, c = st.columns(3)
            delivery_no = a.text_input("发货单号 *")
            order_no = b.text_input("订单编号 *")
            customer_code = c.text_input("客户编码")
            product_code = a.text_input("商品编码 *")
            delivery_date = b.date_input("发货日期", value=date.today())
            quantity = c.number_input("发货数量 *", min_value=0.0, value=1.0, step=1.0)
            submitted = st.form_submit_button("保存发货记录", type="primary")
            if submitted:
                try:
                    status, message = delivery_service.import_delivery_record(
                        db,
                        {
                            "delivery_no": delivery_no,
                            "order_no": order_no,
                            "customer_code": customer_code,
                            "product_code": product_code,
                            "delivery_date": delivery_date,
                            "quantity": quantity,
                        },
                        batch_id="MANUAL",
                        tenant_id=tenant_id,
                    )
                    if status == "inserted":
                        st.success("发货记录已保存。")
                        st.rerun()
                    else:
                        st.warning(message)
                except Exception as exc:
                    show_error(exc, context="手工补录发货")
    with tab_export:
        df = delivery_service.delivery_dataframe(deliveries)
        download_dataframe_button(
            df,
            label="导出发货记录 Excel",
            filename="食链通_发货记录.xlsx",
            key="download_deliveries",
            sheet_name="发货记录",
            title="食链通发货记录报表",
        )
        duplicates = delivery_service.duplicate_deliveries_dataframe(db, tenant_id)
        st.markdown("**重复发货单号**")
        if duplicates.empty:
            st.success("没有发现重复发货单号。")
        else:
            st.dataframe(duplicates, use_container_width=True, hide_index=True)

