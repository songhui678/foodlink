"""安全相关工具：连接串脱敏、文件名检查。"""

from __future__ import annotations

import re
from pathlib import Path


def mask_mongodb_uri(uri: str) -> str:
    if not uri:
        return ""
    return re.sub(r"(mongodb(?:\+srv)?://[^:/@\s]+:)([^@\s]+)(@)", r"\1****\3", uri)


def sanitize_filename(filename: str) -> str:
    """只保留文件名本身，防止路径穿越。"""

    name = Path(filename or "").name
    name = name.replace("\\", "_").replace("/", "_").strip()
    name = re.sub(r"[\x00-\x1f]", "", name)
    if not name or name in {".", ".."}:
        return "unnamed"
    return name


def is_within_directory(path: Path, directory: Path) -> bool:
    try:
        path.resolve().relative_to(directory.resolve())
        return True
    except ValueError:
        return False

