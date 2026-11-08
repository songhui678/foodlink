"""订单发货核对：多次发货、部分/超量/未发货、订单不存在和客户不匹配。"""

from __future__ import annotations

from decimal import Decimal

import pandas as pd
import unittest

from services import customer_service, delivery_service, order_service, product_service
from tests.helpers import MongoTestCase, import_excel


class DeliveryTests(MongoTestCase):
    def setUp(self):
        super().setUp()
        customer_service.create_customer(self.db, {"customer_code": "KH001", "customer_name": "测试客户", "phone": "13800000001"})
        customer_service.create_customer(self.db, {"customer_code": "KH002", "customer_name": "另一客户", "phone": "13800000002"})
        product_service.create_product(self.db, {"product_code": "SP001", "product_name": "测试商品", "specification": "200g*24瓶", "price": "10.00"})
        self.order_df = pd.DataFrame(
            {
                "订单编号": ["DD001", "DD002", "DD003"],
                "客户编码": ["KH001", "KH001", "KH001"],
                "客户名称": ["测试客户", "测试客户", "测试客户"],
                "商品编码": ["SP001", "SP001", "SP001"],
                "商品名称": ["测试商品", "测试商品", "测试商品"],
                "商品规格": ["200g*24瓶", "200g*24瓶", "200g*24瓶"],
                "订单日期": ["2026-01-01", "2026-01-02", "2026-01-03"],
                "订单数量": [10, 5, 2],
                "单价": ["10.00", "10.00", "10.00"],
                "金额": ["100.00", "50.00", "20.00"],
            }
        )
        import_excel(self.db, {"订单": self.order_df}, "order")

    def _deliveries(self, rows):
        delivery_service.import_delivery_record
        batch_id = "TEST-BATCH"
        for row in rows:
            delivery_service.import_delivery_record(self.db, row, batch_id=batch_id)

    def test_one_order_multiple_deliveries(self):
        self._deliveries(
            [
                {"delivery_no": "FH001", "order_no": "DD001", "customer_code": "KH001", "product_code": "SP001", "delivery_date": "2026-01-05", "quantity": 4},
                {"delivery_no": "FH002", "order_no": "DD001", "customer_code": "KH001", "product_code": "SP001", "delivery_date": "2026-01-06", "quantity": 6},
            ]
        )
        detail, summary, _ = delivery_service.reconcile(self.db)
        row = detail[detail["订单编号"] == "DD001"].iloc[0]
        self.assertEqual(row["核对结果"], "已全部发货")
        self.assertEqual(row["发货次数"], 2)
        self.assertEqual(summary["已全部发货"], 1)

    def test_partial_over_and_missing_delivery(self):
        self._deliveries(
            [
                {"delivery_no": "FH003", "order_no": "DD002", "customer_code": "KH001", "product_code": "SP001", "delivery_date": "2026-01-07", "quantity": 2},
                {"delivery_no": "FH004", "order_no": "DD003", "customer_code": "KH001", "product_code": "SP001", "delivery_date": "2026-01-08", "quantity": 3},
            ]
        )
        detail, summary, _ = delivery_service.reconcile(self.db)
        self.assertEqual(detail[detail["订单编号"] == "DD002"].iloc[0]["核对结果"], "部分发货")
        self.assertEqual(detail[detail["订单编号"] == "DD003"].iloc[0]["核对结果"], "超量发货")
        self.assertGreaterEqual(summary["部分发货"], 1)
        self.assertGreaterEqual(summary["超量发货"], 1)

    def test_delivery_order_not_exists(self):
        self._deliveries(
            [{"delivery_no": "FH005", "order_no": "DD-NOT-FOUND", "customer_code": "KH001", "product_code": "SP001", "delivery_date": "2026-01-09", "quantity": 1}]
        )
        detail, summary, _ = delivery_service.reconcile(self.db)
        self.assertTrue((detail["核对结果"] == "订单不存在").any())
        self.assertGreaterEqual(summary["异常"], 1)

    def test_customer_mismatch(self):
        self._deliveries(
            [{"delivery_no": "FH006", "order_no": "DD001", "customer_code": "KH002", "product_code": "SP001", "delivery_date": "2026-01-10", "quantity": 10}]
        )
        detail, _, _ = delivery_service.reconcile(self.db)
        self.assertTrue((detail["核对结果"] == "客户不匹配").any())

    def test_duplicate_delivery_no(self):
        doc = {
            "tenant_id": "default",
            "delivery_no": "FH-DUP",
            "order_no": "DD001",
            "customer_code": "KH001",
            "product_code": "SP001",
            "delivery_date": "2026-01-11",
            "quantity": 1,
        }
        self.db["delivery_records"].insert_many([dict(doc), dict(doc)])
        detail, _, _ = delivery_service.reconcile(self.db)
        self.assertTrue((detail["核对结果"] == "数据异常").any())


if __name__ == "__main__":
    unittest.main()

