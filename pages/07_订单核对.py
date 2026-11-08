"""订单核对：订单数量与发货数量按商品汇总比较。"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import delivery_service, order_service
from utils.excel_utils import workbook_to_bytes
from utils.ui import (
    database_page,
    empty_state,
    metric_row,
    page_header,
    paginated_table,
    show_error,
    setup_page,
)


setup_page("订单核对", "⚖️")
page_header("订单核对", "按订单编号与商品编码汇总发货数量，再与订单数量比较；支持一个订单多次发货。")


with database_page() as db:
    tenant_id = "default"
    first_date, last_date = order_service.order_date_range(db, tenant_id)
    today = date.today()
    default_start = first_date or today.replace(month=1, day=1)
    default_end = last_date or today
    col1, col2, col3 = st.columns([2, 1, 1])
    date_range = col1.date_input("订单日期范围", value=(default_start, default_end), key="recon_date_range")
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
    elif isinstance(date_range, tuple) and len(date_range) == 1:
        start_date = end_date = date_range[0]
    else:
        start_date = end_date = date_range
    order_no = col2.text_input("指定订单编号（可选）", key="recon_order_no")
    auto = col3.checkbox("页面加载时自动核对", value=True, key="recon_auto")

    run = st.button("执行核对", type="primary", key="recon_run") or auto
    if run:
        if start_date > end_date:
            start_date, end_date = end_date, start_date
        try:
            with st.spinner("正在核对订单与发货数据…"):
                detail, summary, order_level = delivery_service.reconcile(
                    db, tenant_id=tenant_id, start_date=start_date, end_date=end_date, order_no=order_no
                )
            st.session_state["recon_result"] = (detail, summary, order_level, start_date, end_date)
        except Exception as exc:
            show_error(exc, context="订单核对")

    result = st.session_state.get("recon_result")
    if not result:
        empty_state("点击“执行核对”开始检查。", "⚖️")
    else:
        detail, summary, order_level, used_start, used_end = result
        st.caption(f"核对范围：{used_start} 至 {used_end}")
        metric_row(
            [
                ("已全部发货", summary.get("已全部发货", 0), None),
                ("部分发货", summary.get("部分发货", 0), None),
                ("超量发货", summary.get("超量发货", 0), None),
                ("未发货 / 异常", summary.get("未发货", 0) + summary.get("异常", 0), None),
            ]
        )
        if detail.empty:
            empty_state("该范围内没有订单明细可核对。")
        else:
            status_filter = st.multiselect(
                "核对结果筛选",
                ["已全部发货", "部分发货", "超量发货", "未发货", "订单不存在", "商品不匹配", "客户不匹配", "数据异常"],
                default=["部分发货", "超量发货", "未发货", "订单不存在", "商品不匹配", "客户不匹配", "数据异常"],
                key="recon_status_filter",
            )
            shown = detail[detail["核对结果"].isin(status_filter)] if status_filter else detail
            tab_detail, tab_order = st.tabs(["商品级核对", "订单级汇总"])
            with tab_detail:
                paginated_table(
                    shown,
                    key="recon_detail_table",
                    page_size=20,
                    search_columns=["订单编号", "客户编码", "商品编码", "商品名称", "核对结果", "说明"],
                    search_label="搜索核对结果",
                )
            with tab_order:
                st.dataframe(order_level, use_container_width=True, hide_index=True)
            try:
                content = workbook_to_bytes(
                    [
                        ("核对汇总", pd.DataFrame([{"核对结果": key, "数量": value} for key, value in summary.items()])),
                        ("商品级核对", detail),
                        ("订单级核对", order_level),
                    ],
                    title="食链通订单发货核对报表",
                )
                st.download_button(
                    "下载核对报表 Excel",
                    data=content,
                    file_name=f"食链通_订单发货核对_{used_start}_{used_end}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="download_recon",
                )
            except Exception as exc:
                show_error(exc, context="导出核对报表")

        duplicates = delivery_service.duplicate_deliveries_dataframe(db, tenant_id)
        with st.expander("重复发货单检查", expanded=False):
            if duplicates.empty:
                st.success("没有发现重复发货单号。")
            else:
                st.dataframe(duplicates, use_container_width=True, hide_index=True)

