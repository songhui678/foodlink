"""初始化 MongoDB 数据库、集合索引和默认设置。

用法：python scripts/init_database.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database.connection import check_connection, database_summary, get_db
from services.settings_service import initialize_database
from utils.config import get_settings
from utils.errors import friendly_error


def main() -> int:
    settings = get_settings()
    status = check_connection()
    print(f"数据库连接：{status.message}")
    print(f"连接地址：{status.uri}")
    print(f"数据库名称：{status.database}")
    if not status.ok:
        print("请先启动 MongoDB，并检查 .env 中的 MONGODB_URI。")
        return 1
    try:
        db = get_db()
        result = initialize_database(db)
        print(f"初始化完成，数据库：{result['database']}")
        print(f"索引数量：{len(result['indexes'])}")
        for item in database_summary(db):
            print(f"  {item['集合']}：{item['文档数']} 条")
        return 0
    except Exception as exc:
        print(f"初始化失败：{friendly_error(exc)}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

