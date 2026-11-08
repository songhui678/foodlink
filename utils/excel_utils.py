"""Excel/CSV 读取、预览与中文样式导出。"""

from __future__ import annotations

import io
import math
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Sequence

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from utils.config import get_settings
from utils.decimal_utils import to_decimal
from utils.errors import DataValidationError, ExportError
from utils.file_utils import validate_upload
from utils.phone_utils import to_text
from utils.string_utils import normalize_header


SUPPORTED_EXTENSIONS = {".xlsx", ".xls", ".csv"}


def _excel_engine(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".xls":
        return "xlrd"
    if suffix == ".xlsx":
        return "openpyxl"
    return ""


def _read_csv(content: bytes) -> pd.DataFrame:
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "gb18030", "gbk", "utf-8"):
        try:
            return pd.read_csv(
                io.BytesIO(content),
                dtype=object,
                encoding=encoding,
                keep_default_na=False,
                na_filter=False,
            )
        except Exception as exc:  # 尝试下一种编码
            last_error = exc
    raise DataValidationError(
        "CSV 文件读取失败，请确认文件编码为 UTF-8 或 GBK。",
        detail=str(last_error) if last_error else None,
    )


def _detect_header_row(raw: pd.DataFrame, import_type: str) -> int:
    """在前 20 行中寻找最像表头的一行，避免标题行导致字段识别失败。"""

    from utils.field_definitions import IMPORT_SCHEMAS

    aliases: dict[str, str] = {}
    schemas = [IMPORT_SCHEMAS[import_type]] if import_type in IMPORT_SCHEMAS else list(IMPORT_SCHEMAS.values())
    for schema in schemas:
        aliases.update(schema.alias_lookup())
    best_row = 0
    best_score = -1
    for index in range(min(20, len(raw))):
        values = [normalize_header(value) for value in raw.iloc[index].tolist()]
        non_empty = sum(1 for value in values if value)
        matches = sum(1 for value in values if value in aliases)
        score = matches * 10 + non_empty
        if matches >= 2 and score > best_score:
            best_row = index
            best_score = score
    return best_row


def read_dataframe(
    content: bytes,
    filename: str,
    *,
    sheet_name: str | int | None = None,
    import_type: str | None = None,
    header_row: int | None = None,
) -> pd.DataFrame:
    """读取 Excel/CSV 为 DataFrame，全部保留为 object，避免编号丢前导零。"""

    validate_upload(filename, len(content))
    suffix = Path(filename).suffix.lower()
    if suffix == ".csv":
        df = _read_csv(content)
    else:
        engine = _excel_engine(filename)
        try:
            raw = pd.read_excel(
                io.BytesIO(content),
                sheet_name=sheet_name if sheet_name is not None else 0,
                header=None,
                dtype=object,
                engine=engine,
                keep_default_na=False,
                na_filter=False,
            )
        except Exception as exc:
            raise DataValidationError(
                "Excel 文件读取失败，请确认文件未损坏且格式正确。", detail=str(exc)
            ) from exc
        row = header_row if header_row is not None else _detect_header_row(raw, import_type or "customer")
        df = raw.iloc[row + 1 :].copy()
        df.columns = [to_text(value) for value in raw.iloc[row].tolist()]

    df = df.copy()
    cleaned_columns: list[str] = []
    seen: dict[str, int] = {}
    for index, column in enumerate(df.columns):
        name = to_text(column)
        if not name or name.lower().startswith("unnamed:"):
            name = f"未命名列{index + 1}"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 0
        cleaned_columns.append(name)
    df.columns = cleaned_columns
    df = df.dropna(how="all")
    if df.empty:
        return df
    mask = df.apply(lambda row: any(not _is_empty(value) for value in row.tolist()), axis=1)
    return df.loc[mask].reset_index(drop=True)


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return to_text(value) == ""


def list_sheets(content: bytes, filename: str) -> list[tuple[str, int, int]]:
    """返回 [(Sheet名称, 行数, 列数)]。"""

    validate_upload(filename, len(content))
    suffix = Path(filename).suffix.lower()
    if suffix == ".csv":
        df = _read_csv(content)
        return [("CSV数据", len(df), len(df.columns))]

    engine = _excel_engine(filename)
    try:
        excel_file = pd.ExcelFile(io.BytesIO(content), engine=engine)
    except Exception as exc:
        raise DataValidationError("无法读取 Excel Sheet 列表，请检查文件是否损坏。", detail=str(exc)) from exc
    result: list[tuple[str, int, int]] = []
    for name in excel_file.sheet_names:
        try:
            df = pd.read_excel(
                excel_file,
                sheet_name=name,
                header=None,
                dtype=object,
                keep_default_na=False,
                na_filter=False,
            )
            result.append((str(name), int(len(df)), int(df.shape[1])))
        except Exception:
            result.append((str(name), 0, 0))
    return result


def preview_dataframe(df: pd.DataFrame, rows: int = 20) -> pd.DataFrame:
    preview = df.head(rows).copy()
    for column in preview.columns:
        preview[column] = preview[column].map(
            lambda value: to_text(value) if value is not None else ""
        )
    return preview


def build_empty_dataframe(columns: Sequence[str]) -> pd.DataFrame:
    return pd.DataFrame({column: pd.Series(dtype="object") for column in columns})


def _display_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    if isinstance(value, datetime) and value.tzinfo is not None:
        value = value.replace(tzinfo=None)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value
    return value


def _column_category(name: str) -> str:
    text = str(name)
    if re.search(r"手机号|电话|联系电话|联系方式", text):
        return "text"
    if re.search(r"编码|编号|单号|客户号|货号", text):
        return "text"
    if re.search(r"日期|时间", text):
        return "date"
    if re.search(r"金额|单价|价格|销售额|回款额|应收|合计|小计", text):
        return "money"
    if re.search(r"数量|件数|箱数|瓶数", text):
        return "number"
    return "auto"


def _style_sheet(ws, df: pd.DataFrame, title: str | None = None) -> None:
    header_fill = PatternFill("solid", fgColor="1F4E78")
    header_font = Font(color="FFFFFF", bold=True, size=11)
    thin = Side(style="thin", color="D9E2F3")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    start_row = 1
    if title:
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(1, len(df.columns)))
        cell = ws.cell(row=1, column=1, value=title)
        cell.font = Font(bold=True, size=14, color="1F4E78")
        cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[1].height = 26
        start_row = 2

    for col_index, column in enumerate(df.columns, start=1):
        cell = ws.cell(row=start_row, column=col_index, value=str(column))
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = border
    ws.row_dimensions[start_row].height = 24

    for row_index, (_, row) in enumerate(df.iterrows(), start=start_row + 1):
        for col_index, column in enumerate(df.columns, start=1):
            value = _display_value(row[column])
            cell = ws.cell(row=row_index, column=col_index, value=value)
            cell.border = border
            cell.alignment = Alignment(vertical="center")
            category = _column_category(column)
            if category == "text":
                cell.number_format = "@"
                if value not in ("", None):
                    cell.value = to_text(value)
            elif category == "money":
                cell.number_format = "#,##0.00"
                if value not in ("", None):
                    cell.value = float(to_decimal(value))
            elif category == "number":
                cell.number_format = "#,##0.####"
            elif category == "date":
                cell.number_format = "yyyy-mm-dd"

    ws.freeze_panes = ws.cell(row=start_row + 1, column=1)
    if len(df.columns) > 0:
        ws.auto_filter.ref = (
            f"A{start_row}:{get_column_letter(len(df.columns))}{max(start_row, start_row + len(df))}"
        )
    for col_index, column in enumerate(df.columns, start=1):
        max_length = len(str(column)) * 2
        for value in df[column].head(200).tolist():
            if value is not None and str(value) not in {"", "nan"}:
                max_length = max(max_length, len(str(value)) + 2)
        ws.column_dimensions[get_column_letter(col_index)].width = min(max(10, max_length), 42)


def dataframe_to_excel_bytes(
    df: pd.DataFrame,
    *,
    sheet_name: str = "数据",
    title: str | None = None,
) -> bytes:
    return workbook_to_bytes([(sheet_name, df)], title=title)


def workbook_to_bytes(
    sheets: Sequence[tuple[str, pd.DataFrame]],
    *,
    title: str | None = None,
) -> bytes:
    if not sheets:
        raise ExportError("没有可导出的数据。")
    try:
        wb = Workbook()
        wb.remove(wb.active)
        for name, df in sheets:
            safe_name = re.sub(r"[\\/*?:\[\]]", "_", str(name))[:31] or "数据"
            ws = wb.create_sheet(title=safe_name)
            _style_sheet(ws, df, title=title if len(sheets) == 1 else None)
        output = io.BytesIO()
        wb.save(output)
        return output.getvalue()
    except ExportError:
        raise
    except Exception as exc:
        raise ExportError("Excel 文件生成失败，请稍后重试。", detail=str(exc)) from exc


def export_errors_to_bytes(error_df: pd.DataFrame) -> bytes:
    if error_df is None or error_df.empty:
        error_df = pd.DataFrame(columns=["行号", "字段", "错误原因", "原始数据"])
    return dataframe_to_excel_bytes(error_df, sheet_name="错误数据", title="食链通导入错误报告")


def export_to_file(
    df: pd.DataFrame,
    filename: str,
    *,
    sheet_name: str = "数据",
    title: str | None = None,
) -> Path:
    settings = get_settings()
    path = Path(settings.export_dir) / filename
    path.write_bytes(dataframe_to_excel_bytes(df, sheet_name=sheet_name, title=title))
    return path

