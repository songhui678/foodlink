"""测试辅助函数。"""

from __future__ import annotations

import io
import os
import sys
import unittest
from pathlib import Path
from typing import Iterable

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database.connection import get_db
from database.indexes import ensure_indexes


TEST_DB_NAME = os.getenv("MONGODB_TEST_DATABASE", "foodlink_test")
COLLECTIONS = [
    "customers", "products", "sales_orders", "sales_order_items", "delivery_records",
    "payment_records", "import_batches", "import_logs", "matching_logs", "error_logs",
    "field_mapping_configs", "system_settings",
]


def dataframe_to_xlsx_bytes(sheets: dict[str, pd.DataFrame]) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, index=False, sheet_name=name[:31])
    return output.getvalue()


class MongoTestCase(unittest.TestCase):
    """所有数据库测试只使用独立测试库，绝不影响 foodlink 正式库。"""

    db = None

    @classmethod
    def setUpClass(cls):
        if "test" not in TEST_DB_NAME.lower():
            raise unittest.SkipTest("测试数据库名称必须包含 test")
        try:
            cls.db = get_db(TEST_DB_NAME)
            cls.db.client.drop_database(TEST_DB_NAME)
            cls.db = get_db(TEST_DB_NAME)
            ensure_indexes(cls.db)
            cls.using_fake = False
        except Exception:
            # 沙箱/CI 无法访问 localhost 时，使用明确标注的进程内 MongoDB mock
            from tests.fake_mongo import FakeClient

            cls.db = FakeClient()[TEST_DB_NAME]
            cls.using_fake = True
            ensure_indexes(cls.db)

    def setUp(self):
        for name in COLLECTIONS:
            self.db[name].delete_many({})

    @classmethod
    def tearDownClass(cls):
        if cls.db is not None and "test" in cls.db.name.lower():
            cls.db.client.drop_database(cls.db.name)


def import_excel(
    db,
    sheets: dict[str, pd.DataFrame],
    import_type: str,
    *,
    sheet_name: str | None = None,
    filename: str | None = None,
    mapping: dict[str, str] | None = None,
):
    from services import excel_service, import_service

    content = dataframe_to_xlsx_bytes(sheets)
    name = filename or f"test_{import_type}.xlsx"
    sheet = sheet_name or list(sheets.keys())[0]
    analysis = excel_service.analyze_file(
        db, content, name, import_type, sheet_name=sheet, mapping=mapping
    )
    result = import_service.commit_import(db, analysis, duplicate_file_action="reimport")
    return analysis, result

