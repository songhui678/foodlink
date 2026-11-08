"""全部 11 类报表导出测试（包含带时区时间字段的客户/商品资料）。"""

from __future__ import annotations

import io
import unittest
import zipfile

from scripts.generate_demo_data import generate_demo_data
from services import report_service
from tests.helpers import MongoTestCase


class ReportTests(MongoTestCase):
    def test_all_report_types_export(self):
        generate_demo_data(self.db)
        for label, key in report_service.REPORT_TYPES.items():
            with self.subTest(report=label):
                content, filename = report_service.export_report_bytes(self.db, key)
                self.assertTrue(filename.endswith(".xlsx"))
                self.assertGreater(len(content), 1000)
                with zipfile.ZipFile(io.BytesIO(content)) as zf:
                    self.assertIn("xl/workbook.xml", zf.namelist())


if __name__ == "__main__":
    unittest.main()

