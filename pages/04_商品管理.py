"""商品管理：列表、新增、编辑、软删除、规格重复检查与导出。"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import product_service
from utils.decimal_utils import money_str
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


setup_page("商品管理", "📦")
page_header("商品管理", "维护商品编码、名称、规格、单位、分类和价格。规格不同的商品不会被自动合并。")


with database_page() as db:
    tenant_id = "default"
    products = product_service.list_products(db, tenant_id=tenant_id, include_deleted=True, skip=0, limit=10000)
    active = [item for item in products if not item.get("is_deleted")]
    categories = product_service.list_categories(db, tenant_id)
    duplicate_df = product_service.duplicate_product_groups(db, tenant_id)

    metric_row(
        [
            ("商品总数", len(active), None),
            ("商品分类", len(categories), None),
            ("同名商品组", len(duplicate_df), None),
            ("已删除", len([item for item in products if item.get("is_deleted")]), None),
        ]
    )
    st.divider()

    tab_list, tab_add, tab_edit, tab_duplicate, tab_export = st.tabs(
        ["商品列表", "新增商品", "编辑 / 删除", "同名/重复检查", "导出"]
    )

    with tab_list:
        filter_col1, filter_col2 = st.columns([2, 1])
        category = filter_col1.selectbox("分类筛选", ["全部", *categories], key="product_category_filter")
        include_deleted = filter_col2.checkbox("包含已删除商品", key="product_include_deleted")
        shown = [
            item
            for item in products
            if (include_deleted or not item.get("is_deleted"))
            and (category == "全部" or item.get("category") == category)
        ]
        df = product_service.product_dataframe(shown)
        paginated_table(
            df,
            key="product_table",
            page_size=20,
            search_columns=["商品编码", "商品名称", "商品规格", "商品单位", "商品分类"],
            search_label="搜索商品",
        )

    with tab_add:
        st.caption("商品编码建议填写；如果两个商品名称相同但规格不同，请分别建档。")
        with st.form("add_product_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                product_code = st.text_input("商品编码", placeholder="例如 SP0001")
                product_name = st.text_input("商品名称 *", placeholder="例如 香辣牛肉酱")
                specification = st.text_input("商品规格", placeholder="例如 200g*24瓶")
            with col2:
                unit = st.text_input("商品单位", placeholder="箱")
                category = st.text_input("商品分类", placeholder="调味品")
                price = st.number_input("商品价格", min_value=0.0, value=0.0, step=0.01, format="%.2f")
            submitted = st.form_submit_button("保存商品", type="primary")
            if submitted:
                try:
                    product_service.create_product(
                        db,
                        {
                            "product_code": product_code,
                            "product_name": product_name,
                            "specification": specification,
                            "unit": unit,
                            "category": category,
                            "price": price,
                        },
                        tenant_id=tenant_id,
                    )
                    st.success("商品已新增。")
                    st.rerun()
                except Exception as exc:
                    show_error(exc, context="新增商品")

    with tab_edit:
        if not products:
            empty_state("暂无商品可编辑。")
        else:
            selected_id = st.selectbox(
                "选择商品",
                [item["id"] for item in products],
                format_func=lambda value: item_label(next(item for item in products if item["id"] == value), "product"),
                key="edit_product_select",
            )
            current = next(item for item in products if item["id"] == selected_id)
            with st.form("edit_product_form"):
                col1, col2 = st.columns(2)
                with col1:
                    product_code = st.text_input("商品编码", value=current.get("product_code", ""))
                    product_name = st.text_input("商品名称 *", value=current.get("product_name", ""))
                    specification = st.text_input("商品规格", value=current.get("specification", ""))
                with col2:
                    unit = st.text_input("商品单位", value=current.get("unit", ""))
                    category = st.text_input("商品分类", value=current.get("category", ""))
                    price = st.number_input(
                        "商品价格",
                        min_value=0.0,
                        value=float(current.get("price") or 0),
                        step=0.01,
                        format="%.2f",
                    )
                save = st.form_submit_button("保存修改", type="primary")
                if save:
                    try:
                        product_service.update_product(
                            db,
                            selected_id,
                            {
                                "product_code": product_code,
                                "product_name": product_name,
                                "specification": specification,
                                "unit": unit,
                                "category": category,
                                "price": price,
                            },
                            tenant_id=tenant_id,
                        )
                        st.success("商品资料已更新。")
                        st.rerun()
                    except Exception as exc:
                        show_error(exc, context="编辑商品")

            st.divider()
            if current.get("is_deleted"):
                if st.button("恢复此商品", key="restore_product_button"):
                    try:
                        product_service.restore_product(db, selected_id, tenant_id=tenant_id)
                        st.success("商品已恢复。")
                        st.rerun()
                    except Exception as exc:
                        show_error(exc, context="恢复商品")
            else:
                confirm = st.checkbox("我确认删除此商品（软删除，可在列表中恢复）", key="delete_product_confirm")
                if st.button("删除商品", type="secondary", disabled=not confirm, key="delete_product_button"):
                    try:
                        product_service.soft_delete_product(db, selected_id, tenant_id=tenant_id)
                        st.success("商品已软删除。")
                        st.rerun()
                    except Exception as exc:
                        show_error(exc, context="删除商品")

    with tab_duplicate:
        st.caption("同名但规格不同的商品会保留为不同商品，系统不会使用 drop_duplicates 自动合并。")
        if duplicate_df.empty:
            empty_state("没有发现同名或同编码商品分组。", "✅")
        else:
            st.dataframe(duplicate_df, use_container_width=True, hide_index=True)

    with tab_export:
        df = product_service.product_dataframe([item for item in products if not item.get("is_deleted")])
        download_dataframe_button(
            df,
            label="导出商品资料 Excel",
            filename="食链通_商品资料.xlsx",
            key="download_products",
            sheet_name="商品资料",
            title="食链通商品资料报表",
        )
        st.caption("金额列按 0.00 格式导出，编码按文本格式导出。")

