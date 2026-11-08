"""数据库备份命令行工具。

用法：
    python scripts/backup_database.py
    python scripts/backup_database.py --output backups/
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database.connection import get_db
from services.backup_service import create_backup
from utils.config import get_settings
from utils.errors import friendly_error


def main() -> int:
    parser = argparse.ArgumentParser(description="食链通数据库备份")
    parser.add_argument("--output", default=None, help="备份目录，默认使用 settings.backup_dir")
    args = parser.parse_args()
    settings = get_settings()
    try:
        db = get_db()
        path = create_backup(db, args.output or settings.backup_dir)
        print(f"备份完成：{path}")
        return 0
    except Exception as exc:
        print(f"备份失败：{friendly_error(exc)}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

