"""端到端：客户/商品/订单/发货/核对/分析/报表/备份。"""

from __future__ import annotations

import io
import unittest
import zipfile

import pandas as pd

from services import analysis_service, backup_service, customer_service, delivery_service, order_service, product_service, report_service
from tests.helpers import MongoTestCase, import_excel


class EndToEndTests(MongoTestCase):
    def test_full_demo_flow(self):
        customer_service.create_customer(self.db, {"customer_code": "E2E-KH001", "customer_name": "端到端客户", "phone": "13800000001", "region": "华东"})
        product_service.create_product(self.db, {"product_code": "E2E-SP001", "product_name": "端到端商品", "specification": "200g*24瓶", "price": "12.50"})
        order_df = pd.DataFrame(
            {
                "订单编号": ["E2E-DD001"],
                "客户编码": ["E2E-KH001"],
                "客户名称": ["端到端客户"],
                "商品编码": ["E2E-SP001"],
                "商品名称": ["端到端商品"],
                "商品规格": ["200g*24瓶"],
                "订单日期": ["2026-04-01"],
                "订单数量": [4],
                "单价": ["12.50"],
                "金额": ["50.00"],
            }
        )
        _, result = import_excel(self.db, {"订单": order_df}, "order")
        self.assertEqual(result.success_rows, 1)
        delivery_df = pd.DataFrame(
            {
                "发货单号": ["E2E-FH001"],
                "订单编号": ["E2E-DD001"],
                "客户编码": ["E2E-KH001"],
                "商品编码": ["E2E-SP001"],
                "发货日期": ["2026-04-02"],
                "发货数量": [4],
            }
        )
        _, delivery_result = import_excel(self.db, {"发货": delivery_df}, "delivery")
        self.assertEqual(delivery_result.success_rows, 1)
        detail, summary, _ = delivery_service.reconcile(self.db)
        self.assertEqual(detail.iloc[0]["核对结果"], "已全部发货")
        rows = analysis_service.load_sales_rows(self.db)
        overview = analysis_service.overview(rows)
        self.assertEqual(overview["销售额"], 50.0)
        self.assertEqual(overview["订单数"], 1)
        content, filename = report_service.export_report_bytes(self.db, "sales_summary")
        self.assertTrue(filename.endswith(".xlsx"))
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            self.assertIn("xl/workbook.xml", zf.namelist())

        backup_path = backup_service.create_backup(self.db)
        self.assertTrue(backup_path.exists())
        restored = backup_service.restore_backup(self.db, backup_path.read_bytes(), mode="merge")
        self.assertTrue(restored["ok"])


if __name__ == "__main__":
    unittest.main()

