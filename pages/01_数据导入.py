"""数据导入：多文件、多 Sheet、字段映射、校验与批次导入。"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import excel_service, import_service
from utils.config import get_settings
from utils.excel_utils import dataframe_to_excel_bytes, export_errors_to_bytes, read_dataframe
from utils.field_definitions import IMPORT_SCHEMAS, IMPORT_TYPE_LABELS, auto_map_columns, schema_for
from utils.ui import (
    database_page,
    download_dataframe_button,
    empty_state,
    page_header,
    show_error,
    setup_page,
)


setup_page("数据导入", "📥")
page_header("数据导入", "上传 Excel/CSV，选择 Sheet，检查字段映射和错误数据，确认后再写入数据库。")


@st.cache_data(show_spinner=False, max_entries=50)
def _cached_sheets(content: bytes, filename: str):
    return excel_service.list_file_sheets(content, filename)


@st.cache_data(show_spinner=False, max_entries=50)
def _cached_dataframe(content: bytes, filename: str, sheet_name: str, import_type: str):
    return read_dataframe(content, filename, sheet_name=sheet_name, import_type=import_type)


def _type_by_label(label: str) -> str:
    return next((key for key, value in IMPORT_TYPE_LABELS.items() if value == label), "customer")


def _render_template_downloads() -> None:
    with st.expander("下载 Excel 导入模板", expanded=False):
        st.caption("模板包含系统推荐的中文列名，可直接填写；也可以使用企业现有表格并手动映射。")
        columns = st.columns(len(IMPORT_SCHEMAS))
        for column, (key, schema) in zip(columns, IMPORT_SCHEMAS.items()):
            template = excel_service.template_dataframe(key)
            content = dataframe_to_excel_bytes(template, sheet_name=schema.label, title=f"{schema.label}导入模板")
            column.download_button(
                f"{schema.label}模板",
                data=content,
                file_name=f"食链通_{schema.label}导入模板.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"template_{key}",
                use_container_width=True,
            )


def _render_import_result(result) -> None:
    if result.status == "已跳过":
        st.warning("该文件已按选择跳过，没有写入新数据。")
        return
    if result.status == "失败":
        st.error(f"批次 {result.batch_id} 导入失败：成功 0 行，失败 {result.failed_rows} 行。")
    elif result.status == "部分完成":
        st.warning(f"批次 {result.batch_id} 部分完成：成功 {result.success_rows} 行，失败 {result.failed_rows} 行。")
    else:
        st.success(f"批次 {result.batch_id} 导入完成：成功 {result.success_rows} 行，失败 {result.failed_rows} 行。")
    if result.details:
        with st.expander("查看导入明细", expanded=result.status != "已完成"):
            st.dataframe(pd.DataFrame(result.details), use_container_width=True, hide_index=True)


with database_page() as db:
    settings = get_settings()
    st.session_state.setdefault("uploaded_bytes", {})
    st.session_state.setdefault("analyses", {})
    st.session_state.setdefault("mapping_presets", {})

    if st.session_state.get("last_import_results"):
        st.subheader("最近导入结果")
        for item in st.session_state["last_import_results"]:
            _render_import_result(item)
        if st.button("清除导入结果提示", key="clear_import_results"):
            st.session_state["last_import_results"] = []
            st.rerun()

    _render_template_downloads()
    st.divider()

    uploaded_files = st.file_uploader(
        "上传 Excel 或 CSV 文件（可多选）",
        type=["xlsx", "xls", "csv"],
        accept_multiple_files=True,
        help=f"支持 .xlsx、.xls、.csv；单文件默认不超过 {settings.max_file_size_mb}MB。",
        key="foodlink_uploader",
    )

    if uploaded_files:
        current_names = {item.name for item in uploaded_files}
        st.session_state["uploaded_bytes"] = {
            name: content for name, content in st.session_state["uploaded_bytes"].items() if name in current_names
        }
        for uploaded in uploaded_files:
            st.session_state["uploaded_bytes"][uploaded.name] = uploaded.getvalue()

    if not st.session_state["uploaded_bytes"]:
        empty_state("尚未上传文件。请先选择 Excel 或 CSV 文件。", "📄")
        st.stop()

    st.subheader("文件与 Sheet")
    for filename, content in list(st.session_state["uploaded_bytes"].items()):
        with st.container(border=True):
            st.markdown(f"#### 📄 {filename}")
            try:
                sheets = _cached_sheets(content, filename)
            except Exception as exc:
                show_error(exc, context=f"读取文件 {filename}")
                continue
            if not sheets:
                st.warning("该文件没有可读取的 Sheet。")
                continue
            sheet_labels = [f"{name}（{rows} 行 × {cols} 列）" for name, rows, cols in sheets]
            sheet_name = st.selectbox(
                "选择 Sheet", [item[0] for item in sheets], format_func=lambda name: next(
                    (label for label, item in zip(sheet_labels, sheets) if item[0] == name), name
                ), key=f"sheet_{filename}"
            )
            type_label = st.selectbox(
                "导入数据类型",
                list(IMPORT_TYPE_LABELS.values()),
                key=f"type_{filename}",
                help="同一个文件的不同 Sheet 可以分别导入。",
            )
            import_type = _type_by_label(type_label)
            schema = schema_for(import_type)

            try:
                df = _cached_dataframe(content, filename, sheet_name, import_type)
            except Exception as exc:
                show_error(exc, context=f"读取 {filename} / {sheet_name}")
                continue
            if df.empty:
                st.warning("该 Sheet 没有数据。")
                continue

            st.caption(f"数据行数：{len(df)} 行，列数：{len(df.columns)}。下面显示前 20 行预览。")
            st.dataframe(df.head(20), use_container_width=True, hide_index=True)

            preset = st.session_state["mapping_presets"].get(import_type, {})
            saved_configs = import_service.list_mapping_configs(db, import_type=import_type)
            if saved_configs:
                config_names = [item.get("name", "") for item in saved_configs]
                config_col, apply_col = st.columns([3, 1])
                chosen_config = config_col.selectbox(
                    "已保存的映射方案", ["（不使用）", *config_names], key=f"saved_map_{filename}_{sheet_name}_{import_type}"
                )
                if apply_col.button("应用映射", key=f"apply_map_{filename}_{sheet_name}_{import_type}") and chosen_config != "（不使用）":
                    config = next((item for item in saved_configs if item.get("name") == chosen_config), None)
                    if config:
                        st.session_state["mapping_presets"][import_type] = config.get("mapping", {})
                        for field_key, column in config.get("mapping", {}).items():
                            widget_key = f"map_{filename}_{sheet_name}_{import_type}_{field_key}"
                            if column in df.columns:
                                st.session_state[widget_key] = column
                        st.rerun()
            detected = {**auto_map_columns(list(df.columns), import_type), **preset}
            st.markdown("**字段映射**（企业列名不同时请手动选择）")
            mapping: dict[str, str] = {}
            mapping_columns = st.columns(2)
            for index, field in enumerate(schema.fields):
                options = ["（不映射）", *[str(column) for column in df.columns]]
                default_column = detected.get(field.key)
                default_index = options.index(default_column) if default_column in options else 0
                with mapping_columns[index % 2]:
                    selected = st.selectbox(
                        f"{field.label}{' *' if field.required else ''}",
                        options,
                        index=default_index,
                        key=f"map_{filename}_{sheet_name}_{import_type}_{field.key}",
                        help=f"字段代码：{field.key}",
                    )
                    if selected != "（不映射）":
                        mapping[field.key] = selected

            missing_required = [field.label for field in schema.required_fields if field.key not in mapping]
            if missing_required:
                st.warning("尚未映射必填字段：" + "、".join(missing_required))

            analysis_key = f"{filename}|{sheet_name}|{import_type}"
            previous = st.session_state["analyses"].get(analysis_key)
            if previous and previous.mapping != mapping:
                previous = None
                st.session_state["analyses"].pop(analysis_key, None)

            check_col, import_col, clear_col = st.columns([1, 1, 1])
            if check_col.button("检查此文件", key=f"check_{analysis_key}", type="primary"):
                try:
                    analysis = excel_service.analyze_file(
                        db,
                        content,
                        filename,
                        import_type,
                        sheet_name=sheet_name,
                        mapping=mapping,
                    )
                    st.session_state["analyses"][analysis_key] = analysis
                    previous = analysis
                except Exception as exc:
                    show_error(exc, context=f"校验 {filename}")
            if clear_col.button("清除此文件分析", key=f"clear_{analysis_key}"):
                st.session_state["analyses"].pop(analysis_key, None)
                st.rerun()

            analysis = st.session_state["analyses"].get(analysis_key)
            if analysis is None:
                st.caption("请先点击“检查此文件”，查看错误数据后再导入。")
                continue

            for warning in analysis.warnings:
                st.warning(warning)
            metric_columns = st.columns(4)
            metric_columns[0].metric("总行数", analysis.validation.total_rows)
            metric_columns[1].metric("可导入行数", analysis.validation.valid_count)
            metric_columns[2].metric("错误行数", analysis.validation.error_count)
            metric_columns[3].metric("数据库已存在", analysis.existing_count)

            if not analysis.error_dataframe.empty:
                st.error("发现错误数据，错误行不会导入。请修正 Excel 或调整字段映射。")
                st.dataframe(analysis.error_dataframe, use_container_width=True, hide_index=True)
                st.download_button(
                    "下载错误数据 Excel",
                    data=export_errors_to_bytes(analysis.error_dataframe),
                    file_name=f"{filename}_错误数据.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"errors_{analysis_key}",
                )
            else:
                st.success("数据校验通过，没有发现错误行。")

            duplicate_action = "reimport"
            if analysis.duplicate_batches:
                duplicate_action = st.radio(
                    "该文件曾导入过，请选择处理方式",
                    ["跳过", "重新导入", "取消"],
                    horizontal=True,
                    key=f"dup_{analysis_key}",
                )
                duplicate_action = {"跳过": "skip", "重新导入": "reimport", "取消": "cancel"}[duplicate_action]

            update_existing = False
            if import_type in {"customer", "product"}:
                update_existing = st.checkbox(
                    "按编码更新已存在的客户/商品（默认跳过，避免覆盖）",
                    key=f"update_{analysis_key}",
                )
            save_mapping = st.checkbox("保存本次字段映射，方便下次使用", value=True, key=f"save_map_{analysis_key}")
            mapping_name = "默认映射"
            if save_mapping:
                mapping_name = st.text_input("映射方案名称", value="默认映射", key=f"map_name_{analysis_key}")
            confirmed = st.checkbox(
                f"我已核对以上数据，确认导入 {analysis.validation.valid_count} 行",
                key=f"confirm_{analysis_key}",
            )
            if import_col.button(
                "确认导入此文件",
                key=f"import_{analysis_key}",
                type="primary",
                disabled=not confirmed or analysis.validation.valid_count == 0,
            ):
                try:
                    with st.spinner("正在写入数据库，请稍候…"):
                        result = import_service.commit_import(
                            db,
                            analysis,
                            duplicate_file_action=duplicate_action,
                            update_existing=update_existing,
                            save_mapping=save_mapping,
                            mapping_name=mapping_name,
                        )
                    st.session_state.setdefault("last_import_results", []).append(result)
                    st.session_state["analyses"].pop(analysis_key, None)
                    st.rerun()
                except Exception as exc:
                    show_error(exc, context=f"导入 {filename}")

    # 批量导入所有已检查文件
    if st.session_state["analyses"]:
        st.divider()
        st.subheader("批量导入")
        st.caption(f"当前有 {len(st.session_state['analyses'])} 个已检查文件。批量导入会使用各文件当前的校验结果和默认处理选项。")
        batch_confirm = st.checkbox("我确认批量导入所有已检查文件（重复文件默认跳过）", key="batch_confirm")
        if st.button("导入所有已检查文件", type="primary", disabled=not batch_confirm, key="batch_import"):
            results = []
            for key, analysis in list(st.session_state["analyses"].items()):
                try:
                    result = import_service.commit_import(
                        db,
                        analysis,
                        duplicate_file_action="skip" if analysis.duplicate_batches else "reimport",
                        save_mapping=True,
                    )
                    results.append(result)
                    st.session_state["analyses"].pop(key, None)
                except Exception as exc:
                    show_error(exc, context=f"批量导入 {analysis.filename}")
            st.session_state["last_import_results"] = st.session_state.get("last_import_results", []) + results
            st.rerun()

