"""应用配置加载。

配置来源优先级：环境变量 > config.yaml > 代码默认值。
所有目录均在项目根目录内创建，避免依赖当前工作目录。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

try:  # python-dotenv 是可选运行依赖，未安装时仍可使用系统环境变量
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - 仅作为降级保护
    load_dotenv = None

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read_yaml(path: Path) -> dict[str, Any]:
    if yaml is None or not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class AppSettings:
    """集中管理应用配置。"""

    app_name: str = "食链通 FoodLink"
    version: str = "1.0.0"
    mongodb_uri: str = "mongodb://localhost:27017/"
    mongodb_database: str = "foodlink"
    mongodb_test_database: str = "foodlink_test"
    tenant_id: str = "default"
    max_file_size_mb: int = 50
    page_size: int = 20
    upload_cleanup_hours: int = 24
    log_level: str = "INFO"
    upload_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "uploads")
    export_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "exports")
    backup_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "backups")
    log_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "logs")
    demo_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "data" / "demo")
    supported_extensions: tuple[str, ...] = (".xlsx", ".xls", ".csv")

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024

    def ensure_directories(self) -> None:
        for directory in (
            self.upload_dir,
            self.export_dir,
            self.backup_dir,
            self.log_dir,
            self.demo_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def masked_uri(self) -> str:
        from utils.security import mask_mongodb_uri

        return mask_mongodb_uri(self.mongodb_uri)


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    if load_dotenv is not None:
        load_dotenv(PROJECT_ROOT / ".env", override=False)

    config = _read_yaml(PROJECT_ROOT / "config.yaml")
    app_cfg = config.get("app", {}) if isinstance(config.get("app"), dict) else {}
    limits = config.get("limits", {}) if isinstance(config.get("limits"), dict) else {}
    storage = config.get("storage", {}) if isinstance(config.get("storage"), dict) else {}

    settings = AppSettings(
        app_name=os.getenv("APP_NAME", app_cfg.get("name", "食链通 FoodLink")),
        version=os.getenv("APP_VERSION", app_cfg.get("version", "1.0.0")),
        mongodb_uri=os.getenv("MONGODB_URI", "mongodb://localhost:27017/"),
        mongodb_database=os.getenv("MONGODB_DATABASE", "foodlink"),
        mongodb_test_database=os.getenv(
            "MONGODB_TEST_DATABASE", config.get("testing", {}).get("database", "foodlink_test")
        ),
        tenant_id=os.getenv("TENANT_ID", "default"),
        max_file_size_mb=_as_int(
            os.getenv("MAX_FILE_SIZE_MB", limits.get("max_file_size_mb", 50)), 50
        ),
        page_size=_as_int(os.getenv("PAGE_SIZE", limits.get("page_size", 20)), 20),
        upload_cleanup_hours=_as_int(
            os.getenv("UPLOAD_CLEANUP_HOURS", storage.get("upload_cleanup_hours", 24)), 24
        ),
        log_level=os.getenv("LOG_LEVEL", config.get("logging", {}).get("level", "INFO")),
        upload_dir=Path(os.getenv("UPLOAD_DIR", str(PROJECT_ROOT / "uploads"))),
        export_dir=Path(os.getenv("EXPORT_DIR", str(PROJECT_ROOT / "exports"))),
        backup_dir=Path(os.getenv("BACKUP_DIR", str(PROJECT_ROOT / "backups"))),
        log_dir=Path(os.getenv("LOG_DIR", str(PROJECT_ROOT / "logs"))),
        demo_dir=Path(os.getenv("DEMO_DIR", str(PROJECT_ROOT / "data" / "demo"))),
    )
    settings.ensure_directories()
    return settings


def reload_settings() -> AppSettings:
    """清空配置缓存，主要用于测试。"""

    get_settings.cache_clear()
    return get_settings()

