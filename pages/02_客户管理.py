"""客户管理：列表、详情、新增、编辑、软删除、重复检查与导出。"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import customer_service
from utils.ui import (
    database_page,
    download_dataframe_button,
    empty_state,
    item_label,
    metric_row,
    page_header,
    paginated_table,
    show_error,
    setup_page,
)


setup_page("客户管理", "👥")
page_header("客户管理", "维护客户资料，支持搜索、区域筛选、软删除和重复客户检查。")


with database_page() as db:
    tenant_id = "default"
    customers = customer_service.list_customers(
        db, tenant_id=tenant_id, include_deleted=True, skip=0, limit=10000
    )
    active = [item for item in customers if not item.get("is_deleted")]
    regions = customer_service.list_regions(db, tenant_id)
    duplicate_df = customer_service.duplicate_customer_groups(db, tenant_id)

    metric_row(
        [
            ("客户总数", len(active), None),
            ("覆盖区域", len(regions), None),
            ("重复客户组", len(duplicate_df), None),
            ("已删除", len([item for item in customers if item.get("is_deleted")]), None),
        ]
    )
    st.divider()

    tab_list, tab_add, tab_edit, tab_duplicate, tab_export = st.tabs(
        ["客户列表", "新增客户", "编辑 / 删除", "重复客户检查", "导出"]
    )

    with tab_list:
        filter_col1, filter_col2, filter_col3 = st.columns([2, 1, 1])
        region = filter_col1.selectbox("区域筛选", ["全部", *regions], key="customer_region_filter")
        include_deleted = filter_col2.checkbox("包含已删除客户", key="customer_include_deleted")
        detail_search = filter_col3.text_input("按编码/名称/手机号查找详情", key="customer_detail_search")
        shown = [
            item
            for item in customers
            if (include_deleted or not item.get("is_deleted"))
            and (region == "全部" or item.get("region") == region)
        ]
        df = customer_service.customer_dataframe(shown)
        paginated_table(
            df,
            key="customer_table",
            page_size=20,
            search_columns=["客户编码", "客户名称", "联系人", "手机号", "所属区域", "详细地址"],
            search_label="搜索客户",
        )
        if detail_search:
            matched = [
                item
                for item in shown
                if detail_search.lower() in str(item.get("customer_code", "")).lower()
                or detail_search.lower() in str(item.get("customer_name", "")).lower()
                or detail_search in str(item.get("phone", ""))
            ]
            for item in matched[:5]:
                with st.expander(item_label(item, "customer")):
                    st.write(
                        {
                            "客户编码": item.get("customer_code", ""),
                            "客户名称": item.get("customer_name", ""),
                            "联系人": item.get("contact", ""),
                            "手机号": item.get("phone", ""),
                            "所属区域": item.get("region", ""),
                            "详细地址": item.get("address", ""),
                            "来源": item.get("source", ""),
                            "创建时间": item.get("created_at", ""),
                        }
                    )

    with tab_add:
        st.caption("客户编码、手机号按字符串保存，不会丢失前导零。客户名称必填。")
        with st.form("add_customer_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                customer_code = st.text_input("客户编码", placeholder="例如 KH0001")
                customer_name = st.text_input("客户名称 *", placeholder="例如 华东食品贸易有限公司")
                contact = st.text_input("联系人")
            with col2:
                phone = st.text_input("手机号", placeholder="13800138000")
                region = st.text_input("所属区域", placeholder="华东")
                address = st.text_area("详细地址", height=100)
            submitted = st.form_submit_button("保存客户", type="primary")
            if submitted:
                try:
                    customer_service.create_customer(
                        db,
                        {
                            "customer_code": customer_code,
                            "customer_name": customer_name,
                            "contact": contact,
                            "phone": phone,
                            "region": region,
                            "address": address,
                        },
                        tenant_id=tenant_id,
                    )
                    st.success("客户已新增。")
                    st.rerun()
                except Exception as exc:
                    show_error(exc, context="新增客户")

    with tab_edit:
        if not customers:
            empty_state("暂无客户可编辑。")
        else:
            selected_id = st.selectbox(
                "选择客户",
                [item["id"] for item in customers],
                format_func=lambda value: item_label(next(item for item in customers if item["id"] == value), "customer"),
                key="edit_customer_select",
            )
            current = next(item for item in customers if item["id"] == selected_id)
            with st.form("edit_customer_form"):
                col1, col2 = st.columns(2)
                with col1:
                    customer_code = st.text_input("客户编码", value=current.get("customer_code", ""))
                    customer_name = st.text_input("客户名称 *", value=current.get("customer_name", ""))
                    contact = st.text_input("联系人", value=current.get("contact", ""))
                with col2:
                    phone = st.text_input("手机号", value=current.get("phone", ""))
                    region = st.text_input("所属区域", value=current.get("region", ""))
                    address = st.text_area("详细地址", value=current.get("address", ""), height=100)
                save = st.form_submit_button("保存修改", type="primary")
                if save:
                    try:
                        customer_service.update_customer(
                            db,
                            selected_id,
                            {
                                "customer_code": customer_code,
                                "customer_name": customer_name,
                                "contact": contact,
                                "phone": phone,
                                "region": region,
                                "address": address,
                            },
                            tenant_id=tenant_id,
                        )
                        st.success("客户资料已更新。")
                        st.rerun()
                    except Exception as exc:
                        show_error(exc, context="编辑客户")

            st.divider()
            if current.get("is_deleted"):
                if st.button("恢复此客户", key="restore_customer_button"):
                    try:
                        customer_service.restore_customer(db, selected_id, tenant_id=tenant_id)
                        st.success("客户已恢复。")
                        st.rerun()
                    except Exception as exc:
                        show_error(exc, context="恢复客户")
            else:
                confirm = st.checkbox("我确认删除此客户（软删除，可在列表中恢复）", key="delete_customer_confirm")
                if st.button("删除客户", type="secondary", disabled=not confirm, key="delete_customer_button"):
                    try:
                        customer_service.soft_delete_customer(db, selected_id, tenant_id=tenant_id)
                        st.success("客户已软删除。数据仍保留，可在“包含已删除客户”中恢复。")
                        st.rerun()
                    except Exception as exc:
                        show_error(exc, context="删除客户")

    with tab_duplicate:
        st.caption("系统不会自动合并重复客户。以下分组仅用于人工核对。")
        if duplicate_df.empty:
            empty_state("没有发现重复客户分组。", "✅")
        else:
            st.dataframe(duplicate_df, use_container_width=True, hide_index=True)

    with tab_export:
        df = customer_service.customer_dataframe(
            [item for item in customers if not item.get("is_deleted")]
        )
        download_dataframe_button(
            df,
            label="导出客户资料 Excel",
            filename="食链通_客户资料.xlsx",
            key="download_customers",
            sheet_name="客户资料",
            title="食链通客户资料报表",
        )
        st.caption("导出时客户编码和手机号会按文本格式写入，不会变成科学计数法。")

