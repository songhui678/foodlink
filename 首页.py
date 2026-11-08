"""食链通 FoodLink V1.0 系统首页。"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database.repositories.batch_repository import BatchRepository
from services import customer_service, delivery_service, matching_service, order_service, product_service
from utils.decimal_utils import round_money
from utils.ui import (
    database_page,
    empty_state,
    home_hero,
    metric_row,
    render_nav_cards,
    section_header,
    setup_page,
)


setup_page("首页", "🏠")

home_hero()


with database_page() as db:
    tenant_id = "default"
    try:
        customer_count = customer_service.count_customers(db, tenant_id)
        product_count = product_service.count_products(db, tenant_id)
        order_count = order_service.order_count(db, tenant_id)
        month_sales_amount, month_order_count = order_service.month_sales(db, tenant_id)
        pending_matching = matching_service.pending_matching_count(db, tenant_id)
        pending_orders = order_service.count_order_anomalies(db, tenant_id)
        pending_delivery = delivery_service.count_pending_delivery_issues(db, tenant_id)
    except Exception as exc:
        from utils.ui import show_error

        show_error(exc, context="加载首页统计")
        st.stop()

    section_header("运营概览", "本月关键指标与待处理事项", "◈")
    metric_row(
        [
            ("客户总数", customer_count, None),
            ("商品总数", product_count, None),
            ("订单总数", order_count, None),
            ("本月销售额", f"¥ {round_money(month_sales_amount):,.2f}", None),
        ]
    )
    metric_row(
        [
            ("本月订单数量", month_order_count, None),
            ("待处理匹配异常", pending_matching, None),
            ("待处理订单异常", pending_orders, None),
            ("待处理发货差异", pending_delivery, None),
        ]
    )

    if customer_count == 0 and product_count == 0 and order_count == 0:
        st.info(
            "👋 欢迎使用食链通。建议按以下顺序开始：\n"
            "1. 到“数据导入”上传客户和商品 Excel；\n"
            "2. 到“客户匹配”“商品匹配”处理候选异常；\n"
            "3. 导入订单和发货记录；\n"
            "4. 到“订单核对”“销售分析”“报表导出”查看结果。\n\n"
            "如果想先体验，可到“系统设置 → 演示数据”一键生成带【测试数据】标识的演示数据。"
        )

    section_header("功能导航", "按业务流程进入各模块", "◈")
    render_nav_cards()

    section_header("最近导入", "最近 6 个导入批次", "◈")
    recent = BatchRepository().recent(db, tenant_id, limit=6)
    if recent:
        rows = [
            {
                "文件名": item.get("filename", ""),
                "类型": item.get("import_type_label", item.get("import_type", "")),
                "成功/失败": f"{item.get('success_rows', 0)} / {item.get('failed_rows', 0)}",
                "状态": item.get("status", ""),
                "时间": item.get("created_at", ""),
            }
            for item in recent
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        if st.button("查看全部导入历史", key="home_history_link"):
            st.switch_page("pages/11_导入历史.py")
    else:
        empty_state("还没有导入记录。", "🗂️")

    with st.expander("使用提示", expanded=False):
        st.markdown(
            """
            - 手机号、客户编码、商品编码和订单编号均按字符串处理，不会丢失前导零。
            - 订单金额使用 Decimal 计算，避免浮点误差。
            - 模糊匹配只提供候选建议，必须人工确认，不会自动合并。
            - 同名商品但规格不同会被视为不同商品。
            - MongoDB 连接失败时，页面只显示中文提示，详细堆栈写入 `logs/foodlink.log`。
            """
        )

    st.markdown(
        '<div class="fl-footer">食链通 FoodLink V1.0 · 本地部署 · 数据保存在您自己的电脑或服务器</div>',
        unsafe_allow_html=True,
    )

