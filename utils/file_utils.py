"""上传文件安全检查。"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from utils.config import get_settings
from utils.errors import DataValidationError
from utils.security import sanitize_filename


def validate_upload(filename: str, size: int) -> str:
    settings = get_settings()
    safe_name = sanitize_filename(filename)
    suffix = Path(safe_name).suffix.lower()
    if suffix not in settings.supported_extensions:
        allowed = "、".join(settings.supported_extensions)
        raise DataValidationError(f"不支持的文件类型“{suffix or '未知'}”，仅支持 {allowed}。")
    if size <= 0:
        raise DataValidationError("上传的文件为空，请重新选择。")
    if size > settings.max_file_size_bytes:
        raise DataValidationError(
            f"文件大小超过限制（{settings.max_file_size_mb}MB），请拆分后重新上传。"
        )
    return safe_name


def file_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def write_temp_upload(content: bytes, filename: str) -> Path:
    """把上传内容写入 uploads 临时目录，返回路径。调用方负责清理。"""

    settings = get_settings()
    path = Path(settings.upload_dir) / f"{uuid.uuid4().hex}_{sanitize_filename(filename)}"
    path.write_bytes(content)
    return path


def cleanup_uploads(older_than_hours: int | None = None) -> int:
    """清理临时上传文件，返回删除数量。"""

    import time

    settings = get_settings()
    hours = older_than_hours if older_than_hours is not None else settings.upload_cleanup_hours
    cutoff = time.time() - hours * 3600
    removed = 0
    for path in Path(settings.upload_dir).glob("*"):
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except OSError:
            continue
    return removed

