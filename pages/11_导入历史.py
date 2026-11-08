"""导入历史：批次、错误报告和导入日志。"""

from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import import_service
from utils.excel_utils import dataframe_to_excel_bytes
from utils.field_definitions import IMPORT_TYPE_LABELS
from utils.ui import database_page, empty_state, page_header, paginated_table, show_error, setup_page


setup_page("导入历史", "🗂️")
page_header("导入历史", "查看每次导入的文件、Sheet、成功/失败行数、错误报告和审计日志。")


with database_page() as db:
    tenant_id = "default"
    col1, col2, col3 = st.columns([2, 1, 1])
    search = col1.text_input("搜索文件名 / 批次编号 / Sheet", key="history_search")
    type_label = col2.selectbox("导入类型", ["全部", *IMPORT_TYPE_LABELS.values()], key="history_type")
    status = col3.selectbox("状态", ["全部", "已完成", "部分完成", "失败", "已跳过", "处理中"], key="history_status")
    type_key = next((key for key, value in IMPORT_TYPE_LABELS.items() if value == type_label), "")
    batches = import_service.list_batches(
        db,
        tenant_id=tenant_id,
        import_type=type_key,
        status="" if status == "全部" else status,
        search=search,
        skip=0,
        limit=5000,
    )
    st.caption(f"共 {len(batches)} 个导入批次。")
    if batches:
        paginated_table(
            import_service.batch_dataframe(batches),
            key="history_table",
            page_size=20,
            search_columns=["批次编号", "导入类型", "文件名", "Sheet", "状态"],
            search_label="在当前结果中筛选",
        )
    else:
        empty_state("暂无导入记录。请先到“数据导入”上传文件。")

    if batches:
        st.divider()
        st.subheader("批次详情")
        options = {item["batch_id"]: item for item in batches}
        selected = st.selectbox(
            "选择批次",
            list(options.keys()),
            format_func=lambda value: f"{value}｜{options[value].get('filename')}｜{options[value].get('status')}",
            key="history_batch_select",
        )
        batch = options[selected]
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("总行数", batch.get("total_rows", 0))
        m2.metric("成功行数", batch.get("success_rows", 0))
        m3.metric("失败行数", batch.get("failed_rows", 0))
        m4.metric("状态", batch.get("status", ""))
        st.write(
            {
                "批次编号": batch.get("batch_id"),
                "导入类型": batch.get("import_type_label", batch.get("import_type")),
                "文件名": batch.get("filename"),
                "Sheet": batch.get("sheet_name"),
                "导入时间": batch.get("created_at"),
                "是否重新导入": "是" if batch.get("is_reimport") else "否",
                "字段映射": batch.get("mapping", {}),
            }
        )
        errors = batch.get("errors", []) or []
        st.markdown("**错误报告**")
        if errors:
            error_df = pd.DataFrame(errors)
            st.dataframe(error_df, use_container_width=True, hide_index=True)
            st.download_button(
                "下载该批次错误报告",
                data=dataframe_to_excel_bytes(error_df, sheet_name="错误报告", title=f"导入错误报告 {selected}"),
                file_name=f"导入错误报告_{selected}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="history_error_download",
            )
        else:
            st.success("该批次没有错误行。")

        with st.expander("查看批次日志", expanded=False):
            logs = import_service._batches.list_batch_logs(db, selected)
            if logs:
                st.dataframe(pd.DataFrame(logs), use_container_width=True, hide_index=True)
            else:
                empty_state("暂无日志。")

    with st.expander("导出全部导入批次", expanded=False):
        all_batches = import_service.list_batches(db, tenant_id=tenant_id, limit=5000)
        if all_batches:
            df = import_service.batch_dataframe(all_batches)
            st.download_button(
                "下载导入历史 Excel",
                data=dataframe_to_excel_bytes(df, sheet_name="导入历史", title="食链通导入历史"),
                file_name="食链通_导入历史.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="history_all_download",
            )

