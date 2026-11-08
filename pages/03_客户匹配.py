"""客户匹配：未匹配、多候选、重复客户的候选建议与人工确认。"""

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


setup_page("客户匹配", "🔗")
page_header("客户匹配", "按编码、手机号、名称优先级匹配；模糊结果仅作建议，必须人工确认。")


with database_page() as db:
    tenant_id = "default"
    top1, top2, top3 = st.columns([1, 1, 2])
    if top1.button("刷新匹配日志", type="primary", key="refresh_customer_matching"):
        try:
            created = matching_service.refresh_matching_logs(db, tenant_id=tenant_id)
            st.success(f"已检查订单数据，新增 {created} 条待处理匹配日志。")
        except Exception as exc:
            show_error(exc, context="刷新客户匹配日志")
    if top2.button("仅查看待处理", key="customer_pending_only"):
        st.session_state["customer_matching_pending_only"] = True
    pending_only = st.session_state.get("customer_matching_pending_only", False)
    if top3.checkbox("只显示未解决记录", value=pending_only, key="customer_pending_checkbox"):
        pending_only = True
    else:
        pending_only = False

    all_logs = matching_service.list_matching_logs(db, entity_type="customer", tenant_id=tenant_id, limit=3000)
    unresolved = [item for item in all_logs if not item.get("resolved")]
    counts = {status: len([item for item in unresolved if item.get("status") == status]) for status in ["unmatched", "multiple", "duplicate", "abnormal"]}
    metric_row(
        [
            ("未匹配", counts["unmatched"], None),
            ("多条候选", counts["multiple"], None),
            ("重复客户", counts["duplicate"], None),
            ("数据异常", counts["abnormal"], None),
        ]
    )

    logs = unresolved if pending_only else all_logs
    status_filter = st.selectbox(
        "状态筛选",
        ["全部", "未匹配", "多条候选", "重复记录", "数据异常", "已匹配", "已忽略"],
        key="customer_match_status_filter",
    )
    status_map = {v: k for k, v in matching_service.STATUS_LABELS.items()}
    if status_filter != "全部":
        logs = [item for item in logs if item.get("status") == status_map.get(status_filter, "")]

    if logs:
        display_df = matching_service.log_to_dataframe(logs)
        paginated_table(display_df, key="customer_matching_table", page_size=15, search_columns=["输入编码", "输入名称", "匹配结果", "说明"])

        st.divider()
        st.subheader("人工确认匹配")
        options = {item["id"]: item for item in logs}
        selected_log_id = st.selectbox(
            "选择一条匹配记录",
            list(options.keys()),
            format_func=lambda value: f"{options[value].get('input_name') or options[value].get('input_code') or '空'}｜"
            f"{matching_service.STATUS_LABELS.get(options[value].get('status'), '')}｜"
            f"订单 {options[value].get('order_no', '')}",
            key="customer_log_select",
        )
        log = options[selected_log_id]
        col1, col2, col3 = st.columns(3)
        col1.write({"输入编码": log.get("input_code", ""), "输入名称": log.get("input_name", "")})
        col2.write({"手机号": log.get("input_phone", ""), "状态": matching_service.STATUS_LABELS.get(log.get("status"), "")})
        col3.write({"关联订单": log.get("order_no", ""), "说明": log.get("message", "")})

        candidates = log.get("candidates", []) or []
        if candidates:
            st.markdown("**系统候选（模糊建议不会自动确认）**")
            st.dataframe(pd.DataFrame(candidates), use_container_width=True, hide_index=True)

        st.markdown("**从客户库中人工选择**")
        search = st.text_input("搜索客户库", key=f"customer_candidate_search_{selected_log_id}")
        library = matching_service.candidate_customers(db, search=search, tenant_id=tenant_id, limit=200)
        combined: dict[str, dict] = {item.get("id"): item for item in candidates if item.get("id")}
        for item in library:
            combined.setdefault(item["id"], item)
        if not combined:
            empty_state("客户库中没有可选客户。请先到客户管理新增客户。", "👥")
        else:
            target_id = st.selectbox(
                "选择要关联的客户",
                list(combined.keys()),
                format_func=lambda value: item_label(combined[value], "customer"),
                key=f"customer_target_select_{selected_log_id}",
            )
            apply_all = st.checkbox("同时应用到相同客户编码/名称的其他订单", key=f"customer_apply_all_{selected_log_id}")
            col_a, col_b = st.columns([1, 1])
            if col_a.button("确认匹配", type="primary", key=f"customer_resolve_{selected_log_id}"):
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
                    show_error(exc, context="确认客户匹配")
            if col_b.button("忽略此异常", key=f"customer_ignore_{selected_log_id}"):
                try:
                    matching_service.ignore_matching_log(db, log_id=selected_log_id)
                    st.success("已忽略此匹配异常。")
                    st.rerun()
                except Exception as exc:
                    show_error(exc, context="忽略客户匹配")
    else:
        empty_state("当前没有待处理客户匹配记录。", "✅")

    with st.expander("查看全部匹配历史", expanded=False):
        history = matching_service.list_matching_logs(db, entity_type="customer", tenant_id=tenant_id, limit=1000)
        if history:
            st.dataframe(matching_service.log_to_dataframe(history), use_container_width=True, hide_index=True)
        else:
            empty_state("暂无匹配历史。")

