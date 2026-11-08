"""系统设置：连接检测、初始化、备份恢复、演示数据与清理。"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database.connection import check_connection, database_summary
from database.indexes import ensure_indexes
from services import backup_service, settings_service
from utils.config import get_settings
from utils.file_utils import cleanup_uploads
from utils.security import mask_mongodb_uri
from utils.ui import database_page, empty_state, page_header, show_error, setup_page


setup_page("系统设置", "⚙️")
page_header("系统设置", "检查数据库连接、初始化索引、备份恢复和演示数据管理。")


with database_page() as db:
    settings = get_settings()
    tenant_id = "default"
    tab_conn, tab_settings, tab_backup, tab_demo, tab_about = st.tabs(
        ["数据库连接", "业务设置", "备份与恢复", "演示数据", "关于系统"]
    )

    with tab_conn:
        status = check_connection()
        if status.ok:
            st.success(f"{status.message}（{status.database}，{status.latency_ms} ms）")
        else:
            st.error(status.message)
        st.code(f"MONGODB_URI={mask_mongodb_uri(settings.mongodb_uri)}\nMONGODB_DATABASE={settings.mongodb_database}", language="bash")
        st.caption("MongoDB 密码不会在页面中显示；详细信息写入 logs/foodlink.log。")
        col1, col2 = st.columns(2)
        if col1.button("重新检测连接", key="settings_test_connection"):
            st.session_state.pop("_connection_cache", None)
            st.rerun()
        if col2.button("初始化数据库与索引", type="primary", key="settings_init_db"):
            try:
                result = settings_service.initialize_database(db, tenant_id)
                st.success(f"数据库 {result['database']} 初始化完成，共创建/确认 {len(result['indexes'])} 个索引。")
            except Exception as exc:
                show_error(exc, context="初始化数据库")
        with st.expander("查看集合文档数", expanded=False):
            st.dataframe(pd.DataFrame(database_summary(db)), use_container_width=True, hide_index=True)

    with tab_settings:
        company_name = st.text_input("企业名称", value=settings_service.get_setting(db, "company_name", "本地食品企业", tenant_id), key="settings_company_name")
        max_size = st.number_input(
            "单文件大小限制（MB，修改后需同步 .env 中的 MAX_FILE_SIZE_MB）",
            min_value=1,
            max_value=500,
            value=int(settings_service.get_setting(db, "max_file_size_mb", settings.max_file_size_mb, tenant_id)),
            step=1,
            key="settings_max_size",
        )
        if st.button("保存业务设置", type="primary", key="settings_save"):
            try:
                settings_service.set_setting(db, "company_name", company_name, tenant_id=tenant_id, description="企业名称")
                settings_service.set_setting(db, "max_file_size_mb", int(max_size), tenant_id=tenant_id, description="单文件大小限制")
                st.success("设置已保存。文件大小限制的实际生效值仍以 .env 的 MAX_FILE_SIZE_MB 为准。")
            except Exception as exc:
                show_error(exc, context="保存业务设置")
        st.divider()
        st.caption("临时上传文件清理")
        if st.button("立即清理过期上传文件", key="cleanup_uploads"):
            removed = cleanup_uploads(settings.upload_cleanup_hours)
            st.success(f"已清理 {removed} 个过期临时文件。")

    with tab_backup:
        st.markdown("**创建备份**")
        st.caption("备份采用 BSON JSON 打包 zip，包含 12 个业务集合，不依赖 mongodump。")
        if st.button("立即备份数据库", type="primary", key="create_backup"):
            try:
                path = backup_service.create_backup(db)
                st.success(f"备份已创建：{path.name}")
                st.session_state["last_backup_path"] = str(path)
            except Exception as exc:
                show_error(exc, context="创建数据库备份")
        last_path = st.session_state.get("last_backup_path")
        if last_path and Path(last_path).exists():
            st.download_button(
                f"下载刚才的备份 {Path(last_path).name}",
                data=backup_service.backup_file_bytes(last_path),
                file_name=Path(last_path).name,
                mime="application/zip",
                key="download_last_backup",
            )
        backups = backup_service.list_backups()
        st.markdown("**已有备份**")
        if backups:
            backup_df = pd.DataFrame(backups)
            st.dataframe(backup_df, use_container_width=True, hide_index=True)
            backup_name = st.selectbox("选择要下载的备份", [item["文件名"] for item in backups], key="backup_select")
            path = Path(settings.backup_dir) / backup_name
            st.download_button(
                "下载所选备份",
                data=backup_service.backup_file_bytes(path),
                file_name=backup_name,
                mime="application/zip",
                key="download_selected_backup",
            )
        else:
            empty_state("暂无备份文件。")

        st.divider()
        st.markdown("**恢复备份**")
        st.warning("恢复会写入当前数据库。建议先创建备份；“覆盖恢复”会先清空业务集合，请谨慎操作。")
        uploaded = st.file_uploader("上传食链通备份 zip", type=["zip"], key="restore_uploader")
        mode_label = st.radio("恢复模式", ["合并（保留现有数据）", "覆盖（先清空业务集合）"], key="restore_mode")
        mode = "merge" if mode_label.startswith("合并") else "replace"
        confirm_text = st.text_input("覆盖恢复请输入“确认覆盖”", key="restore_confirm_text") if mode == "replace" else ""
        final_confirm = st.checkbox("我确认执行恢复操作", key="restore_final_confirm")
        if st.button("执行恢复", type="secondary", disabled=not (uploaded and final_confirm), key="restore_button"):
            try:
                result = backup_service.restore_backup(
                    db, uploaded.getvalue(), mode=mode, confirm_text=confirm_text
                )
                st.success(result["message"] + f" 恢复集合数：{len(result['collections'])}")
                st.dataframe(pd.DataFrame([{"集合": k, "恢复文档数": v} for k, v in result["collections"].items()]), use_container_width=True, hide_index=True)
            except Exception as exc:
                show_error(exc, context="恢复数据库备份")

    with tab_demo:
        st.markdown("**演示数据**")
        st.caption("演示数据全部带有 is_demo=True 和“【测试数据】”标识，不会与正式业务数据混淆。")
        col1, col2 = st.columns(2)
        if col1.button("生成演示数据", type="primary", key="generate_demo"):
            try:
                from scripts.generate_demo_data import generate_demo_data

                result = generate_demo_data(db)
                st.success(
                    f"演示数据已生成：客户 {result.get('customers', 0)} 个、商品 {result.get('products', 0)} 个、"
                    f"订单 {result.get('orders', 0)} 个、发货记录 {result.get('deliveries', 0)} 条。"
                )
            except Exception as exc:
                show_error(exc, context="生成演示数据")
        if col2.button("清除全部演示数据", key="clear_demo"):
            try:
                result = settings_service.clear_demo_data(db, tenant_id)
                st.success("演示数据已清除：" + "；".join(f"{key} {value} 条" for key, value in result.items()))
            except Exception as exc:
                show_error(exc, context="清除演示数据")
        st.info("演示数据生成后，可在客户匹配、商品匹配、订单核对、销售分析、报表导出页面直接体验完整流程。")

    with tab_about:
        st.markdown("### 食链通 FoodLink V1.0")
        st.write("让食品企业的 Excel 数据自动关联、核对和分析。")
        st.write(
            {
                "版本": settings.version,
                "运行环境": f"Python 3.10-3.12 / Streamlit / MongoDB",
                "数据库": settings.mongodb_database,
                "模式": "本地单用户、单企业（结构预留 tenant_id）",
                "模糊匹配": "RapidFuzz（未安装时自动降级为 difflib）",
            }
        )
        st.caption("数据默认保存在本机 MongoDB，不上传第三方云端。")

