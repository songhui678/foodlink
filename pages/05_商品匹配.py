"""商品匹配：同名不同规格、多候选与人工确认。"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import matching_service
from utils.ui import (
    database_page,
    empty_state,
    item_label,
    metric_row,
    page_header,
    paginated_table,
    show_error,
    setup_page,
)


setup_page("商品匹配", "🧩")
page_header("商品匹配", "商品编码优先；同名但规格不同时只提供候选，绝不能自动合并。")


with database_page() as db:
    tenant_id = "default"
    col1, col2 = st.columns([1, 3])
    if col1.button("刷新匹配日志", type="primary", key="refresh_product_matching"):
        try:
            created = matching_service.refresh_matching_logs(db, tenant_id=tenant_id)
            st.success(f"已检查订单明细，新增 {created} 条待处理匹配日志。")
        except Exception as exc:
            show_error(exc, context="刷新商品匹配日志")
    pending_only = col2.checkbox("只显示未解决记录", key="product_pending_checkbox")

    all_logs = matching_service.list_matching_logs(db, entity_type="product", tenant_id=tenant_id, limit=3000)
    unresolved = [item for item in all_logs if not item.get("resolved")]
    counts = {status: len([item for item in unresolved if item.get("status") == status]) for status in ["unmatched", "multiple", "duplicate", "abnormal"]}
    metric_row(
        [
            ("未匹配", counts["unmatched"], None),
            ("多条候选", counts["multiple"], None),
            ("重复商品", counts["duplicate"], None),
            ("数据异常", counts["abnormal"], None),
        ]
    )

    logs = unresolved if pending_only else all_logs
    status_filter = st.selectbox(
        "状态筛选",
        ["全部", "未匹配", "多条候选", "重复记录", "数据异常", "已匹配", "已忽略"],
        key="product_match_status_filter",
    )
    status_map = {v: k for k, v in matching_service.STATUS_LABELS.items()}
    if status_filter != "全部":
        logs = [item for item in logs if item.get("status") == status_map.get(status_filter, "")]

    if logs:
        paginated_table(
            matching_service.log_to_dataframe(logs),
            key="product_matching_table",
            page_size=15,
            search_columns=["输入编码", "输入名称", "匹配结果", "说明"],
        )
        st.divider()
        st.subheader("人工确认匹配")
        options = {item["id"]: item for item in logs}
        selected_log_id = st.selectbox(
            "选择一条匹配记录",
            list(options.keys()),
            format_func=lambda value: f"{options[value].get('input_name') or options[value].get('input_code') or '空'}"
            f"｜规格：{options[value].get('input_spec') or '空'}"
            f"｜{matching_service.STATUS_LABELS.get(options[value].get('status'), '')}",
            key="product_log_select",
        )
        log = options[selected_log_id]
        col_a, col_b = st.columns(2)
        col_a.write({"输入编码": log.get("input_code", ""), "输入名称": log.get("input_name", ""), "输入规格": log.get("input_spec", "")})
        col_b.write({"关联订单": log.get("order_no", ""), "状态": matching_service.STATUS_LABELS.get(log.get("status"), ""), "说明": log.get("message", "")})

        candidates = log.get("candidates", []) or []
        if candidates:
            st.markdown("**系统候选（请特别核对规格）**")
            st.dataframe(pd.DataFrame(candidates), use_container_width=True, hide_index=True)

        st.markdown("**从商品库中人工选择**")
        search = st.text_input("搜索商品库", key=f"product_candidate_search_{selected_log_id}")
        library = matching_service.candidate_products(db, search=search, tenant_id=tenant_id, limit=200)
        combined: dict[str, dict] = {item.get("id"): item for item in candidates if item.get("id")}
        for item in library:
            combined.setdefault(item["id"], item)
        if not combined:
            empty_state("商品库中没有可选商品。请先到商品管理新增商品。", "📦")
        else:
            target_id = st.selectbox(
                "选择要关联的商品",
                list(combined.keys()),
                format_func=lambda value: item_label(combined[value], "product"),
                key=f"product_target_select_{selected_log_id}",
            )
            apply_all = st.checkbox("同时应用到相同商品编码/名称的其他订单明细", key=f"product_apply_all_{selected_log_id}")
            button_col1, button_col2 = st.columns(2)
            if button_col1.button("确认匹配", type="primary", key=f"product_resolve_{selected_log_id}"):
                try:
                    result = matching_service.resolve_matching_log(
                        db, log_id=selected_log_id, target_id=target_id, apply_all=apply_all, tenant_id=tenant_id
                    )
                    if result.get("ok"):
                        st.success(result.get("message", "匹配已完成。"))
                        st.rerun()
                    else:
                        st.error(result.get("message", "匹配失败。"))
                except Exception as exc:
                    show_error(exc, context="确认商品匹配")
            if button_col2.button("忽略此异常", key=f"product_ignore_{selected_log_id}"):
                try:
                    matching_service.ignore_matching_log(db, log_id=selected_log_id)
                    st.success("已忽略此匹配异常。")
                    st.rerun()
                except Exception as exc:
                    show_error(exc, context="忽略商品匹配")
    else:
        empty_state("当前没有待处理商品匹配记录。", "✅")

    with st.expander("查看全部匹配历史", expanded=False):
        history = matching_service.list_matching_logs(db, entity_type="product", tenant_id=tenant_id, limit=1000)
        if history:
            st.dataframe(matching_service.log_to_dataframe(history), use_container_width=True, hide_index=True)
        else:
            empty_state("暂无匹配历史。")

