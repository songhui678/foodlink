"""报表导出：11 类中文 Excel 报表。"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import customer_service, order_service, product_service, report_service
from utils.ui import database_page, empty_state, page_header, show_error, setup_page


setup_page("报表导出", "📤")
page_header("报表导出", "生成客户、商品、订单、销售、核对、异常等 11 类中文 Excel 报表。")


with database_page() as db:
    tenant_id = "default"
    reports = list(report_service.REPORT_TYPES.keys())
    report_label = st.selectbox("选择报表", reports, key="report_select")
    report_key = report_service.REPORT_TYPES[report_label]

    with st.expander("报表筛选条件", expanded=True):
        col1, col2 = st.columns(2)
        first_date, last_date = order_service.order_date_range(db, tenant_id)
        today = date.today()
        date_range = col1.date_input(
            "日期范围（订单/核对/销售类报表）",
            value=(first_date or today.replace(month=1, day=1), last_date or today),
            key="report_date_range",
        )
        region = col2.selectbox("区域", ["全部", *customer_service.list_regions(db, tenant_id)], key="report_region")
        customers = customer_service.customer_options(db, tenant_id)
        products = product_service.product_options(db, tenant_id)
        customer_labels = {item["id"]: item.get("customer_name", "") for item in customers}
        product_labels = {item["id"]: f"{item.get('product_name')} / {item.get('specification') or '无规格'}" for item in products}
        col3, col4 = st.columns(2)
        customer_ids = col3.multiselect("客户", list(customer_labels.keys()), format_func=lambda value: customer_labels[value], key="report_customers")
        product_ids = col4.multiselect("商品", list(product_labels.keys()), format_func=lambda value: product_labels[value], key="report_products")

    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
    elif isinstance(date_range, tuple) and len(date_range) == 1:
        start_date = end_date = date_range[0]
    else:
        start_date = end_date = date_range
    filters = {
        "start_date": start_date,
        "end_date": end_date,
        "customer_ids": customer_ids,
        "product_ids": product_ids,
        "region": "" if region == "全部" else region,
    }

    if st.button("生成报表预览", type="primary", key="report_generate"):
        try:
            with st.spinner("正在生成报表…"):
                sheet_names, preview = report_service.preview_report(db, report_key, tenant_id=tenant_id, filters=filters)
                content, filename = report_service.export_report_bytes(db, report_key, tenant_id=tenant_id, filters=filters)
            st.session_state["report_preview"] = (sheet_names, preview, content, filename)
        except Exception as exc:
            show_error(exc, context="生成报表")

    preview_data = st.session_state.get("report_preview")
    if not preview_data:
        empty_state("选择报表并点击“生成报表预览”。", "📤")
    else:
        sheet_names, preview, content, filename = preview_data
        st.success(f"报表已生成，共 {len(sheet_names)} 个工作表：{'、'.join(sheet_names)}。")
        if preview.empty:
            empty_state("报表没有数据，但仍可下载空白模板。")
        else:
            st.dataframe(preview.head(200), use_container_width=True, hide_index=True)
            st.caption(f"预览最多显示 200 行；下载文件为完整数据。")
        st.download_button(
            "下载 Excel 报表",
            data=content,
            file_name=filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="report_download",
            type="primary",
        )

    with st.expander("报表说明", expanded=False):
        st.markdown(
            """
            - **客户资料报表 / 商品资料报表**：导出当前有效基础资料。
            - **订单明细报表**：按订单明细展开，包含客户、商品、数量、单价、金额。
            - **销售汇总报表**：包含销售总览、月度趋势和区域销售。
            - **客户/商品销售排行榜**：按销售额降序。
            - **订单发货核对报表**：包含核对汇总、商品级核对和订单级核对。
            - **未匹配客户/商品报表**：列出尚未人工确认的匹配日志。
            - **数据异常报表**：包含订单异常与发货异常。
            - **导入错误报告**：所有导入批次的错误行记录。
            """
        )

