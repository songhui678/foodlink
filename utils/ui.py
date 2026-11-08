"""Streamlit 界面公共组件与中文提示。"""

from __future__ import annotations

import html
import time
from contextlib import contextmanager
from decimal import Decimal
from typing import Any, Iterable, Iterator, Sequence

import pandas as pd
import streamlit as st

from database.connection import check_connection, get_db
from utils.config import get_settings
from utils.decimal_utils import from_db_decimal, money_str
from utils.errors import DatabaseConnectionError, FoodLinkError, friendly_error
from utils.excel_utils import dataframe_to_excel_bytes
from utils.logger import get_logger


def _inject_css() -> None:
    st.markdown(
        """
        <style>
        :root {
            --fl-ink: #102a26;
            --fl-ink-2: #173b34;
            --fl-teal: #0f766e;
            --fl-teal-2: #14b8a6;
            --fl-gold: #c9a86a;
            --fl-gold-soft: #eadfc5;
            --fl-amber: #b45309;
            --fl-paper: #f6f7f2;
            --fl-card: #ffffff;
            --fl-line: #e2e8e2;
            --fl-muted: #6a7a74;
            --fl-shadow: 0 18px 45px rgba(15, 45, 39, .07);
        }
        html, body, [class*="css"] {
            font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB",
                         "Microsoft YaHei", "Noto Sans CJK SC", "Helvetica Neue", sans-serif;
        }
        .stApp {
            background:
                radial-gradient(1200px 600px at 88% -8%, rgba(20, 184, 166, .10), transparent 60%),
                radial-gradient(900px 520px at -8% 8%, rgba(201, 168, 106, .09), transparent 58%),
                var(--fl-paper);
        }
        [data-testid="stAppViewContainer"], [data-testid="stMain"] { background: transparent; }
        [data-testid="stHeader"] { background: transparent; }
        .block-container { padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1440px; }
        h1, h2, h3, h4 { color: var(--fl-ink); letter-spacing: -.02em; }

        /* ---------- 品牌与侧边栏 ---------- */
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #0a211d 0%, #0e2b26 55%, #0b2521 100%);
            border-right: 1px solid rgba(255, 255, 255, .06);
        }
        [data-testid="stSidebar"] > div { background: transparent; }
        [data-testid="stSidebar"] .block-container { padding-top: 1.35rem; }
        .fl-brand { display: flex; align-items: center; gap: 12px; padding: 6px 10px 18px; }
        .fl-brand-mark {
            width: 46px; height: 46px; border-radius: 14px; display: flex; align-items: center;
            justify-content: center; font-family: "Songti SC", "STSong", serif; font-size: 1.35rem;
            font-weight: 700; color: #0b211e; background: linear-gradient(135deg, #f1e2bc, #c9a86a);
            box-shadow: 0 10px 22px rgba(201, 168, 106, .28);
        }
        .fl-brand-name { color: #f6faf8; font-size: 1.06rem; font-weight: 700; line-height: 1.25; }
        .fl-brand-name span { color: var(--fl-gold); font-size: .84rem; font-weight: 600; }
        .fl-brand-sub { color: #8fb3aa; font-size: .6rem; letter-spacing: .18em; margin-top: 4px; }
        .fl-side-rule { height: 1px; background: linear-gradient(90deg, rgba(255, 255, 255, .18), transparent); margin: 4px 0 14px; }
        .fl-status {
            display: flex; align-items: center; gap: 9px; padding: 10px 12px; border-radius: 12px;
            background: rgba(255, 255, 255, .06); border: 1px solid rgba(255, 255, 255, .09);
            color: #ddeae5; font-size: .8rem; margin-bottom: 8px;
        }
        .fl-dot { width: 8px; height: 8px; border-radius: 50%; background: #34d399; box-shadow: 0 0 0 4px rgba(52, 211, 153, .16); }
        .fl-dot.is-off { background: #f87171; box-shadow: 0 0 0 4px rgba(248, 113, 113, .16); }
        .fl-side-meta { color: #8fb3aa; font-size: .72rem; line-height: 1.9; padding: 2px 4px; }
        .fl-side-meta strong { color: #cfe0da; font-weight: 600; }
        [data-testid="stSidebar"] [data-testid="stSidebarNav"] a {
            border-radius: 10px; color: #cfe0da; margin: 2px 6px; padding: .45rem .6rem;
            transition: background .16s ease, color .16s ease;
        }
        [data-testid="stSidebar"] [data-testid="stSidebarNav"] a:hover { background: rgba(255, 255, 255, .08); color: #fff; }
        [data-testid="stSidebar"] [data-testid="stSidebarNav"] a[aria-current="page"] {
            background: linear-gradient(90deg, rgba(20, 184, 166, .24), rgba(20, 184, 166, .06));
            color: #fff;
        }
        [data-testid="stSidebar"] [data-testid="stSidebarNav"] a span { color: inherit; }
        [data-testid="stSidebarCollapseButton"] button { color: #cfe0da; }
        [data-testid="collapsedControl"] { background: #0b2521; }
        [data-testid="stSidebar"] .stCaption,
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"],
        [data-testid="stSidebar"] p { color: #8fb3aa; }

        /* ---------- 首页英雄区 ---------- */
        .fl-hero {
            position: relative; overflow: hidden; border-radius: 26px; padding: 40px 44px;
            background: linear-gradient(135deg, #0a211d 0%, #103b34 55%, #0f5d53 100%);
            box-shadow: 0 30px 65px rgba(8, 32, 28, .24); margin-bottom: 26px;
        }
        .fl-hero::before {
            content: ""; position: absolute; inset: 0;
            background:
                radial-gradient(620px 320px at 82% -6%, rgba(20, 184, 166, .38), transparent 62%),
                radial-gradient(420px 260px at 102% 104%, rgba(201, 168, 106, .24), transparent 62%);
        }
        .fl-hero-copy { position: relative; z-index: 2; max-width: 780px; }
        .fl-eyebrow {
            display: inline-flex; align-items: center; gap: 9px; color: #bfe8df;
            font-size: .7rem; font-weight: 600; letter-spacing: .17em; text-transform: uppercase;
        }
        .fl-eyebrow::before { content: ""; width: 22px; height: 1px; background: var(--fl-gold); }
        .fl-hero h1 {
            color: #f8fbf9; font-size: clamp(2.15rem, 4vw, 3.35rem); line-height: 1.04;
            margin: .55rem 0 .6rem; font-weight: 750;
        }
        .fl-hero h1 .fl-grad {
            background: linear-gradient(90deg, #f4e8c8, #c9a86a 55%, #efe0b8);
            -webkit-background-clip: text; background-clip: text; color: transparent;
        }
        .fl-hero-sub { color: #cfe0da; font-size: 1.02rem; line-height: 1.75; max-width: 620px; margin: 0; }
        .fl-tags { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 22px; }
        .fl-tag {
            border: 1px solid rgba(255, 255, 255, .18); background: rgba(255, 255, 255, .06);
            color: #e6f0ec; padding: 6px 12px; border-radius: 999px; font-size: .76rem;
        }
        .fl-hero-art { position: absolute; right: 34px; top: 50%; transform: translateY(-50%); width: 270px; height: 270px; }
        .fl-ring { position: absolute; border-radius: 50%; border: 1px solid rgba(255, 255, 255, .16); }
        .fl-ring-1 { inset: 0; }
        .fl-ring-2 { inset: 32px; border-color: rgba(201, 168, 106, .38); }
        .fl-ring-3 { inset: 66px; border-color: rgba(20, 184, 166, .38); }
        .fl-monogram {
            position: absolute; inset: 94px; border-radius: 50%; display: flex; align-items: center;
            justify-content: center; color: #f3e7c8; font-size: 3rem; font-weight: 700;
            font-family: "Songti SC", "STSong", serif;
            background: radial-gradient(circle at 30% 20%, rgba(255, 255, 255, .2), rgba(255, 255, 255, .04));
            border: 1px solid rgba(255, 255, 255, .2);
        }
        .fl-art-caption {
            position: absolute; bottom: -2px; left: 50%; transform: translateX(-50%);
            color: #9fc4bb; font-size: .6rem; letter-spacing: .22em; white-space: nowrap;
        }

        /* ---------- 普通页面标题 ---------- */
        .fl-pagehead {
            display: flex; align-items: flex-end; justify-content: space-between; gap: 24px;
            padding: 2px 2px 18px; border-bottom: 1px solid var(--fl-line); margin-bottom: 22px;
        }
        .fl-pagehead .fl-eyebrow { color: var(--fl-teal); }
        .fl-pagehead h1 { font-size: 1.85rem; margin: .35rem 0 .3rem; color: var(--fl-ink); font-weight: 750; }
        .fl-page-sub { color: var(--fl-muted); font-size: .94rem; line-height: 1.7; margin: 0; max-width: 820px; }
        .fl-pagehead-mark {
            width: 46px; height: 46px; border-radius: 14px; flex: 0 0 auto; display: flex;
            align-items: center; justify-content: center; color: var(--fl-teal); font-weight: 700;
            font-family: "Songti SC", "STSong", serif; font-size: 1.1rem;
            background: linear-gradient(135deg, rgba(15, 118, 110, .10), rgba(201, 168, 106, .16));
            border: 1px solid rgba(15, 118, 110, .14);
        }

        /* ---------- 分区标题 ---------- */
        .fl-section { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; margin: 28px 0 13px; }
        .fl-section-title { display: flex; align-items: center; gap: 10px; color: var(--fl-ink); font-size: 1.06rem; font-weight: 700; }
        .fl-section-title::before {
            content: ""; width: 4px; height: 18px; border-radius: 3px;
            background: linear-gradient(180deg, var(--fl-teal), var(--fl-gold));
        }
        .fl-section-sub { color: var(--fl-muted); font-size: .78rem; }

        /* ---------- 指标卡 ---------- */
        .fl-metric {
            position: relative; overflow: hidden; min-height: 116px; padding: 18px 18px 16px;
            background: var(--fl-card); border: 1px solid var(--fl-line); border-radius: 18px;
            box-shadow: var(--fl-shadow); transition: transform .18s ease, box-shadow .18s ease;
        }
        .fl-metric:hover { transform: translateY(-2px); box-shadow: 0 24px 50px rgba(15, 45, 39, .10); }
        .fl-metric::after {
            content: ""; position: absolute; right: -34px; top: -38px; width: 108px; height: 108px;
            border-radius: 50%; background: radial-gradient(circle, rgba(20, 184, 166, .17), transparent 70%);
        }
        .fl-metric--gold::after { background: radial-gradient(circle, rgba(201, 168, 106, .24), transparent 70%); }
        .fl-metric--warn::after { background: radial-gradient(circle, rgba(180, 83, 9, .18), transparent 70%); }
        .fl-metric-label { display: flex; align-items: center; gap: 7px; color: var(--fl-muted); font-size: .78rem; font-weight: 600; }
        .fl-metric-label::before { content: ""; width: 6px; height: 6px; border-radius: 2px; background: var(--fl-teal); }
        .fl-metric--gold .fl-metric-label::before { background: var(--fl-gold); }
        .fl-metric--warn .fl-metric-label::before { background: var(--fl-amber); }
        .fl-metric-value {
            position: relative; z-index: 1; margin-top: 9px; color: var(--fl-ink); font-weight: 750;
            font-size: clamp(1.3rem, 2vw, 1.72rem); letter-spacing: -.035em; font-variant-numeric: tabular-nums;
        }
        .fl-metric-index {
            position: absolute; top: 15px; right: 16px; color: #bdc9c3; font-size: .64rem;
            font-weight: 700; letter-spacing: .13em;
        }
        .fl-metric-delta { margin-top: 6px; font-size: .74rem; color: var(--fl-teal); }
        .fl-metric-delta.is-neg { color: #b91c1c; }

        /* ---------- 导航卡 ---------- */
        [data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 18px !important; border: 1px solid var(--fl-line) !important;
            background: #fff; box-shadow: 0 10px 28px rgba(15, 45, 39, .055);
            transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease;
        }
        [data-testid="stVerticalBlockBorderWrapper"]:hover {
            transform: translateY(-3px); border-color: rgba(15, 118, 110, .34) !important;
            box-shadow: 0 22px 44px rgba(15, 45, 39, .11);
        }
        .fl-nav-icon {
            width: 42px; height: 42px; border-radius: 13px; display: flex; align-items: center;
            justify-content: center; font-size: 1.15rem; margin-bottom: 11px;
            background: linear-gradient(135deg, rgba(15, 118, 110, .10), rgba(201, 168, 106, .17));
            border: 1px solid rgba(15, 118, 110, .12);
        }
        .fl-nav-title { color: var(--fl-ink); font-size: .98rem; font-weight: 700; }
        .fl-nav-desc { color: var(--fl-muted); font-size: .76rem; line-height: 1.55; min-height: 36px; margin-top: 4px; }

        /* ---------- 按钮 / 表单 / 标签页 ---------- */
        .stButton > button, [data-testid^="stBaseButton"] {
            border-radius: 12px; border: 1px solid var(--fl-line); font-weight: 600;
            transition: all .18s ease;
        }
        .stButton > button:hover, [data-testid^="stBaseButton"]:hover {
            border-color: var(--fl-teal); color: var(--fl-teal); transform: translateY(-1px);
        }
        [data-testid="stBaseButton-primary"], button[kind="primary"] {
            background: linear-gradient(135deg, #0f766e, #0b5e57); border: none; color: #fff;
            box-shadow: 0 9px 22px rgba(15, 118, 110, .24);
        }
        [data-testid="stBaseButton-primary"]:hover, button[kind="primary"]:hover {
            color: #fff; box-shadow: 0 13px 28px rgba(15, 118, 110, .32);
        }
        [data-baseweb="input"] > div, [data-baseweb="select"] > div, [data-baseweb="textarea"] > div {
            border-radius: 12px !important; border-color: var(--fl-line) !important; background: #fff !important;
        }
        [data-baseweb="input"]:focus-within > div,
        [data-baseweb="select"]:focus-within > div,
        [data-baseweb="textarea"]:focus-within > div {
            border-color: var(--fl-teal) !important; box-shadow: 0 0 0 3px rgba(15, 118, 110, .10) !important;
        }
        [data-baseweb="tab-list"] { gap: 6px; background: #edf1ec; padding: 6px; border-radius: 14px; }
        button[data-baseweb="tab"] { border-radius: 10px; padding: 8px 16px; color: var(--fl-muted); font-weight: 600; }
        button[data-baseweb="tab"][aria-selected="true"] {
            background: #fff; color: var(--fl-teal); box-shadow: 0 4px 12px rgba(15, 45, 39, .08);
        }
        [data-baseweb="tab-highlight"], [data-baseweb="tab-border"] { display: none; }
        [data-testid="stExpander"] details {
            border: 1px solid var(--fl-line); border-radius: 16px; background: #fff;
            box-shadow: 0 8px 24px rgba(15, 45, 39, .05);
        }
        [data-testid="stExpander"] summary { font-weight: 600; color: var(--fl-ink); }

        /* ---------- 数据与提示 ---------- */
        [data-testid="stDataFrame"] {
            border: 1px solid var(--fl-line); border-radius: 16px; overflow: hidden;
            background: #fff; box-shadow: 0 12px 30px rgba(15, 45, 39, .06);
        }
        [data-testid="stDataFrame"] [role="columnheader"] {
            background: #f2f6f1 !important; color: var(--fl-ink) !important; font-weight: 600 !important;
        }
        [data-testid="stPageLink"] a { color: var(--fl-teal) !important; font-weight: 600; }
        [data-testid="stPageLink"] a:hover { color: var(--fl-ink-2) !important; }
        [data-testid="stAlert"] { border-radius: 14px; border: 1px solid var(--fl-line); }
        .fl-empty {
            display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px;
            padding: 30px 20px; border: 1px dashed #cbd8d2; border-radius: 16px;
            background: rgba(255, 255, 255, .68); color: var(--fl-muted); text-align: center;
        }
        .fl-empty-icon { font-size: 1.55rem; opacity: .82; }
        .fl-empty-text { font-size: .86rem; line-height: 1.6; }
        .fl-footer {
            margin-top: 30px; padding-top: 16px; border-top: 1px solid var(--fl-line);
            color: #93a19b; font-size: .72rem; letter-spacing: .04em; text-align: center;
        }
        code { background: #eef3ef; color: #0f5d53; border-radius: 6px; }
        ::-webkit-scrollbar { width: 8px; height: 8px; }
        ::-webkit-scrollbar-thumb { background: #cad6cf; border-radius: 8px; }

        @media (max-width: 900px) {
            .fl-hero-art { display: none; }
            .fl-hero { padding: 28px; }
            .fl-pagehead-mark { display: none; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def setup_page(title: str, icon: str = "🍎") -> None:
    settings = get_settings()
    st.set_page_config(
        page_title=f"{title} | {settings.app_name}",
        page_icon=icon,
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _inject_css()
    with st.sidebar:
        st.markdown(
            """
            <div class="fl-brand">
              <div class="fl-brand-mark">食</div>
              <div>
                <div class="fl-brand-name">食链通 <span>FoodLink</span></div>
                <div class="fl-brand-sub">FOOD DATA OPERATIONS</div>
              </div>
            </div>
            <div class="fl-side-rule"></div>
            """,
            unsafe_allow_html=True,
        )
        _sidebar_connection()
        st.markdown(
            f'<div class="fl-side-meta">数据库 <strong>{_escape(settings.mongodb_database)}</strong><br>'
            "本地部署 · 数据留在您的设备</div>",
            unsafe_allow_html=True,
        )


def _sidebar_connection() -> None:
    now = time.time()
    cached = st.session_state.get("_connection_cache")
    if not cached or now - cached.get("ts", 0) > 30:
        status = check_connection()
        st.session_state["_connection_cache"] = {
            "ts": now,
            "ok": status.ok,
            "message": status.message,
        }
        cached = st.session_state["_connection_cache"]
    ok = bool(cached.get("ok"))
    dot = "fl-dot" if ok else "fl-dot is-off"
    label = "数据库已连接" if ok else "数据库未连接"
    st.markdown(
        f'<div class="fl-status"><span class="{dot}"></span><span>{label}</span></div>',
        unsafe_allow_html=True,
    )
    if not ok and cached.get("message"):
        st.caption(cached["message"])


def page_header(title: str, subtitle: str = "", eyebrow: str = "FOODLINK · 数据工作台") -> None:
    subtitle_html = f'<p class="fl-page-sub">{_escape(subtitle)}</p>' if subtitle else ""
    st.markdown(
        f"""
        <div class="fl-pagehead">
          <div>
            <div class="fl-eyebrow">{_escape(eyebrow)}</div>
            <h1>{_escape(title)}</h1>
            {subtitle_html}
          </div>
          <div class="fl-pagehead-mark">FL</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def home_hero() -> None:
    st.markdown(
        """
        <section class="fl-hero">
          <div class="fl-hero-copy">
            <div class="fl-eyebrow">FoodLink · 食品企业数据中枢</div>
            <h1>食链通 <span class="fl-grad">FoodLink</span></h1>
            <p class="fl-hero-sub">让食品企业的 Excel 数据自动关联、核对和分析。</p>
            <div class="fl-tags">
              <span class="fl-tag">多文件导入</span>
              <span class="fl-tag">智能匹配</span>
              <span class="fl-tag">订单发货核对</span>
              <span class="fl-tag">销售分析</span>
              <span class="fl-tag">本地部署</span>
            </div>
          </div>
          <div class="fl-hero-art" aria-hidden="true">
            <div class="fl-ring fl-ring-1"></div>
            <div class="fl-ring fl-ring-2"></div>
            <div class="fl-ring fl-ring-3"></div>
            <div class="fl-monogram">食</div>
            <div class="fl-art-caption">V1.0 · LOCAL FIRST</div>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def section_header(title: str, subtitle: str = "", icon: str = "") -> None:
    icon_html = f"{_escape(icon)} " if icon else ""
    subtitle_html = f'<div class="fl-section-sub">{_escape(subtitle)}</div>' if subtitle else ""
    st.markdown(
        f"""
        <div class="fl-section">
          <div class="fl-section-title">{icon_html}{_escape(title)}</div>
          {subtitle_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


@contextmanager
def database_page() -> Iterator[Any]:
    try:
        db = get_db()
    except DatabaseConnectionError as exc:
        st.error(friendly_error(exc))
        st.info(
            "请先启动 MongoDB，再刷新页面。macOS 可执行：`brew services start mongodb-community`；"
            "也可以运行项目中的 `./run.sh`。如仍无法连接，请检查 `.env` 中的 `MONGODB_URI`。"
        )
        st.stop()
        raise
    except Exception as exc:
        get_logger().exception("页面数据库连接失败")
        st.error(friendly_error(exc))
        st.stop()
        raise
    yield db


def show_error(exc: BaseException, *, context: str = "") -> None:
    get_logger().exception("界面操作失败 | %s", context)
    st.error(friendly_error(exc))


def show_success(message: str) -> None:
    st.success(message)


def empty_state(message: str, icon: str = "📭") -> None:
    st.markdown(
        f'<div class="fl-empty"><div class="fl-empty-icon">{_escape(icon)}</div>'
        f'<div class="fl-empty-text">{_escape(message)}</div></div>',
        unsafe_allow_html=True,
    )


def money_text(value: Any) -> str:
    return f"¥ {money_str(value)}"


def metric_row(metrics: Sequence[tuple[str, Any, str | None]]) -> None:
    columns = st.columns(len(metrics)) if metrics else []
    for index, (column, item) in enumerate(zip(columns, metrics), start=1):
        label, value = item[0], item[1]
        delta = item[2] if len(item) > 2 else None
        accent = ""
        if any(word in label for word in ("异常", "差异", "待处理")):
            accent = " fl-metric--warn"
        elif any(word in label for word in ("销售额", "金额", "客单价")):
            accent = " fl-metric--gold"
        delta_html = ""
        if delta is not None:
            delta_class = " is-neg" if str(delta).strip().startswith("-") else ""
            delta_html = f'<div class="fl-metric-delta{delta_class}">{_escape(delta)}</div>'
        column.markdown(
            f'<div class="fl-metric{accent}">'
            f'<div class="fl-metric-index">{index:02d}</div>'
            f'<div class="fl-metric-label">{_escape(label)}</div>'
            f'<div class="fl-metric-value">{_escape(value)}</div>'
            f'{delta_html}</div>',
            unsafe_allow_html=True,
        )


def prepare_dataframe(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None:
        return pd.DataFrame()
    result = df.copy()
    for column in result.columns:
        result[column] = result[column].map(_prepare_value)
    return result


def _prepare_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "to_decimal") and type(value).__name__ == "Decimal128":
        try:
            return float(value.to_decimal())
        except Exception:
            return str(value)
    return value


def paginated_table(
    df: pd.DataFrame,
    *,
    key: str,
    page_size: int = 20,
    search_columns: Iterable[str] | None = None,
    search_label: str = "搜索",
    show_search: bool = True,
    height: int | None = None,
) -> pd.DataFrame:
    """带搜索与分页的表格，返回当前筛选后的完整数据。"""

    data = prepare_dataframe(df)
    if data.empty:
        empty_state("暂无数据。")
        return data

    if show_search:
        left, right = st.columns([2, 1])
        query = left.text_input(search_label, key=f"{key}_search", placeholder="输入关键字筛选")
        if query:
            columns = list(search_columns or data.columns)
            columns = [column for column in columns if column in data.columns]
            if columns:
                mask = data[columns].astype(str).apply(
                    lambda column: column.str.contains(query, case=False, na=False, regex=False)
                ).any(axis=1)
                data = data[mask]
        with right:
            st.caption(f"共 {len(data)} 条")

    state_key = f"{key}_page"
    if state_key not in st.session_state:
        st.session_state[state_key] = 0
    page_size = max(5, int(page_size))
    total_pages = max(1, (len(data) + page_size - 1) // page_size)
    if st.session_state[state_key] >= total_pages:
        st.session_state[state_key] = total_pages - 1

    col1, col2, col3 = st.columns([1, 2, 1])
    if col1.button("上一页", key=f"{key}_prev", disabled=st.session_state[state_key] <= 0):
        st.session_state[state_key] -= 1
        st.rerun()
    col2.markdown(
        f"<div style='text-align:center;color:#6b7280;padding-top:.4rem'>第 {st.session_state[state_key] + 1} / {total_pages} 页</div>",
        unsafe_allow_html=True,
    )
    if col3.button("下一页", key=f"{key}_next", disabled=st.session_state[state_key] >= total_pages - 1):
        st.session_state[state_key] += 1
        st.rerun()

    start = st.session_state[state_key] * page_size
    page = data.iloc[start : start + page_size]
    dataframe_options: dict[str, Any] = {"use_container_width": True, "hide_index": True}
    if height is not None and int(height) > 0:
        dataframe_options["height"] = int(height)
    st.dataframe(page, **dataframe_options)
    return data


def download_dataframe_button(
    df: pd.DataFrame,
    *,
    label: str,
    filename: str,
    key: str,
    sheet_name: str = "数据",
    title: str | None = None,
) -> None:
    try:
        content = dataframe_to_excel_bytes(df, sheet_name=sheet_name, title=title)
        st.download_button(
            label,
            data=content,
            file_name=filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=key,
            use_container_width=False,
        )
    except Exception as exc:
        show_error(exc, context="Excel 下载")


def confirm_checkbox(label: str, key: str) -> bool:
    return st.checkbox(label, key=key)


def item_label(item: dict[str, Any], entity: str = "customer") -> str:
    if entity == "customer":
        code = item.get("customer_code", "")
        name = item.get("customer_name", "")
        phone = item.get("phone", "")
        suffix = f" / {phone}" if phone else ""
        return f"{name}（{code or '无编码'}）{suffix}"
    code = item.get("product_code", "")
    name = item.get("product_name", "")
    spec = item.get("specification", "")
    return f"{name}（{code or '无编码'}）{(' / ' + spec) if spec else ''}"


def render_nav_cards() -> None:
    cards = [
        ("📥", "数据导入", "上传 Excel、预览、字段映射", "pages/01_数据导入.py"),
        ("👥", "客户管理", "客户资料与重复检查", "pages/02_客户管理.py"),
        ("🔗", "客户匹配", "处理未匹配与多候选客户", "pages/03_客户匹配.py"),
        ("📦", "商品管理", "商品资料与规格管理", "pages/04_商品管理.py"),
        ("🧩", "商品匹配", "处理商品名称/规格候选", "pages/05_商品匹配.py"),
        ("🧾", "订单管理", "查询订单与明细", "pages/06_订单管理.py"),
        ("⚖️", "订单核对", "订单与发货数量核对", "pages/07_订单核对.py"),
        ("🚚", "发货管理", "发货记录查询", "pages/08_发货管理.py"),
        ("📈", "销售分析", "趋势、排行与增长", "pages/09_销售分析.py"),
        ("📤", "报表导出", "11 类中文 Excel 报表", "pages/10_报表导出.py"),
        ("🗂️", "导入历史", "批次与错误报告", "pages/11_导入历史.py"),
        ("⚙️", "系统设置", "连接、备份与演示数据", "pages/12_系统设置.py"),
    ]
    for row_start in range(0, len(cards), 4):
        columns = st.columns(4)
        for column, (icon, title, desc, path) in zip(columns, cards[row_start : row_start + 4]):
            with column:
                with st.container(border=True):
                    st.markdown(
                        f'<div class="fl-nav-icon">{_escape(icon)}</div>'
                        f'<div class="fl-nav-title">{_escape(title)}</div>'
                        f'<div class="fl-nav-desc">{_escape(desc)}</div>',
                        unsafe_allow_html=True,
                    )
                    try:
                        st.page_link(path, label="打开模块 →")
                    except Exception:
                        st.caption(path)

