"""销售分析：趋势、排行、区域、增长与异常。"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import analysis_service, customer_service, order_service, product_service
from utils.ui import database_page, empty_state, metric_row, page_header, show_error, setup_page


setup_page("销售分析", "📈")
page_header("销售分析", "基于订单明细真实数据计算销售额、订单数、客户与商品排行，金额使用 Decimal 汇总。")


with database_page() as db:
    tenant_id = "default"
    first_date, last_date = order_service.order_date_range(db, tenant_id)
    today = date.today()
    default_start = first_date or today.replace(month=1, day=1)
    default_end = last_date or today

    customers = customer_service.customer_options(db, tenant_id)
    products = product_service.product_options(db, tenant_id)
    regions = customer_service.list_regions(db, tenant_id)
    customer_labels = {item["id"]: f"{item.get('customer_name')}（{item.get('customer_code') or '无编码'}）" for item in customers}
    product_labels = {item["id"]: f"{item.get('product_name')} / {item.get('specification') or '无规格'}" for item in products}

    with st.expander("分析筛选条件", expanded=True):
        col1, col2 = st.columns([2, 2])
        date_range = col1.date_input("销售日期范围", value=(default_start, default_end), key="analysis_date_range")
        region = col2.selectbox("区域", ["全部", *regions], key="analysis_region")
        col3, col4 = st.columns(2)
        customer_ids = col3.multiselect(
            "客户（可多选）", list(customer_labels.keys()), format_func=lambda value: customer_labels[value], key="analysis_customers"
        )
        product_ids = col4.multiselect(
            "商品（可多选）", list(product_labels.keys()), format_func=lambda value: product_labels[value], key="analysis_products"
        )
        apply = st.button("应用筛选", type="primary", key="analysis_apply")

    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
    elif isinstance(date_range, tuple) and len(date_range) == 1:
        start_date = end_date = date_range[0]
    else:
        start_date = end_date = date_range
    if start_date > end_date:
        start_date, end_date = end_date, start_date

    try:
        rows = analysis_service.load_sales_rows(
            db,
            tenant_id=tenant_id,
            start_date=start_date,
            end_date=end_date,
            customer_ids=customer_ids,
            product_ids=product_ids,
            region="" if region == "全部" else region,
        )
    except Exception as exc:
        show_error(exc, context="加载销售分析数据")
        st.stop()

    overview = analysis_service.overview(rows)
    metric_row(
        [
            ("销售额", f"¥ {overview['销售额']:,.2f}", None),
            ("订单数", overview["订单数"], None),
            ("销售数量", f"{overview['数量']:,.2f}", None),
            ("客单价", f"¥ {overview['客单价']:,.2f}", None),
            ("客户数", overview["客户数"], None),
        ]
    )

    if rows.empty:
        empty_state("当前筛选条件下没有销售数据。请调整日期范围或先导入订单。", "📈")
        st.stop()

    monthly = analysis_service.monthly_sales(rows)
    region_df = analysis_service.region_ranking(rows)
    customer_rank = analysis_service.customer_ranking(rows, limit=20)
    product_rank = analysis_service.product_ranking(rows, limit=20)

    chart1, chart2 = st.columns(2)
    with chart1:
        st.subheader("月度销售额趋势")
        if not monthly.empty:
            fig = px.bar(monthly, x="月份", y="销售额", text="销售额", color_discrete_sequence=["#1f4e78"])
            fig.update_traces(texttemplate="%{text:,.0f}", textposition="outside")
            fig.update_layout(margin=dict(l=10, r=10, t=20, b=10), yaxis_title="销售额（元）")
            st.plotly_chart(fig, use_container_width=True)
    with chart2:
        st.subheader("月度订单数量趋势")
        if not monthly.empty:
            fig = px.line(monthly, x="月份", y="订单数", markers=True, color_discrete_sequence=["#2e86de"])
            fig.update_layout(margin=dict(l=10, r=10, t=20, b=10), yaxis_title="订单数")
            st.plotly_chart(fig, use_container_width=True)

    chart3, chart4 = st.columns(2)
    with chart3:
        st.subheader("客户销售排行榜 Top 20")
        if not customer_rank.empty:
            fig = px.bar(
                customer_rank.head(10).iloc[::-1],
                x="销售额",
                y="客户名称",
                orientation="h",
                color_discrete_sequence=["#1f4e78"],
            )
            fig.update_layout(margin=dict(l=10, r=10, t=20, b=10), yaxis_title="")
            st.plotly_chart(fig, use_container_width=True)
    with chart4:
        st.subheader("区域销售排行")
        if not region_df.empty:
            fig = px.pie(region_df, names="区域", values="销售额", hole=0.35)
            fig.update_layout(margin=dict(l=10, r=10, t=20, b=10))
            st.plotly_chart(fig, use_container_width=True)

    tab_customer, tab_product, tab_detail, tab_growth, tab_anomaly = st.tabs(
        ["客户排行", "商品排行", "明细数据", "销售增长", "销售异常"]
    )
    with tab_customer:
        st.dataframe(customer_rank.drop(columns=["客户ID"], errors="ignore"), use_container_width=True, hide_index=True)
        customer_detail = analysis_service.customer_detail(rows)
        st.markdown("**客户月度销售明细**")
        st.dataframe(customer_detail, use_container_width=True, hide_index=True)
    with tab_product:
        st.dataframe(product_rank.drop(columns=["商品ID"], errors="ignore"), use_container_width=True, hide_index=True)
        product_detail = analysis_service.product_detail(rows)
        st.markdown("**商品月度销售明细**")
        st.dataframe(product_detail, use_container_width=True, hide_index=True)
    with tab_detail:
        detail_df = pd.DataFrame(
            [
                {
                    "订单编号": item.get("order_no"),
                    "订单日期": item.get("order_date"),
                    "客户名称": item.get("customer_name"),
                    "区域": item.get("region"),
                    "商品名称": item.get("product_name"),
                    "规格": item.get("specification"),
                    "数量": item.get("quantity"),
                    "金额": item.get("amount"),
                }
                for _, item in rows.iterrows()
            ]
        )
        st.dataframe(detail_df, use_container_width=True, hide_index=True)
    with tab_growth:
        try:
            growth = analysis_service.growth_analysis(
                db,
                tenant_id=tenant_id,
                start_date=start_date,
                end_date=end_date,
                customer_ids=customer_ids,
                product_ids=product_ids,
                region="" if region == "全部" else region,
            )
            col_a, col_b, col_c = st.columns(3)
            col_a.metric("本期销售额", f"¥ {growth['本期销售额']:,.2f}")
            col_b.metric("上期销售额", f"¥ {growth['上期销售额']:,.2f}")
            col_c.metric("增长率", f"{growth['增长率']:.2f}%", delta=f"¥ {growth['增长额']:,.2f}")
            st.caption(
                f"本期：{growth['本期开始']} 至 {growth['本期结束']}；"
                f"上期：{growth['上期开始']} 至 {growth['上期结束']}。"
            )
            st.write({"本期订单数": growth["本期订单数"], "上期订单数": growth["上期订单数"]})
        except Exception as exc:
            show_error(exc, context="销售增长分析")
    with tab_anomaly:
        try:
            anomaly_df = analysis_service.sales_anomalies(db, rows, tenant_id)
            if anomaly_df.empty:
                st.success("当前筛选范围内没有销售异常。")
            else:
                st.dataframe(anomaly_df, use_container_width=True, hide_index=True)
        except Exception as exc:
            show_error(exc, context="销售异常分析")

