"""订单导入、重复订单、金额精度与异常测试。"""

from __future__ import annotations

from decimal import Decimal

import pandas as pd
import unittest

from services import customer_service, order_service, product_service
from tests.helpers import MongoTestCase, import_excel
from utils.decimal_utils import to_decimal


class OrderTests(MongoTestCase):
    def setUp(self):
        super().setUp()
        customer_service.create_customer(self.db, {"customer_code": "KH001", "customer_name": "测试客户", "phone": "13800000001"})
        product_service.create_product(self.db, {"product_code": "SP001", "product_name": "测试商品", "specification": "200g*24瓶", "price": "10.00"})
        product_service.create_product(self.db, {"product_code": "SP002", "product_name": "测试商品二", "specification": "500g*12瓶", "price": "0.20"})

    def _order_df(self, amount: str = "30.00"):
        return pd.DataFrame(
            {
                "订单编号": ["DD001"],
                "客户编码": ["KH001"],
                "客户名称": ["测试客户"],
                "商品编码": ["SP001"],
                "商品名称": ["测试商品"],
                "商品规格": ["200g*24瓶"],
                "订单日期": ["2026-01-15"],
                "订单数量": [3],
                "单价": ["10.00"],
                "金额": [amount],
            }
        )

    def test_import_order_and_precision(self):
        _, result = import_excel(self.db, {"订单": self._order_df()}, "order")
        self.assertEqual(result.success_rows, 1)
        orders = order_service.find_orders_by_no(self.db, "DD001")
        self.assertEqual(len(orders), 1)
        self.assertEqual(to_decimal(orders[0]["total_amount"]), Decimal("30.00"))
        self.assertEqual(to_decimal(orders[0]["total_quantity"]), Decimal("3"))

    def test_duplicate_order_not_overwritten(self):
        import_excel(self.db, {"订单": self._order_df()}, "order")
        _, result = import_excel(self.db, {"订单": self._order_df()}, "order", filename="第二次.xlsx")
        self.assertEqual(result.success_rows, 0)
        self.assertEqual(len(order_service.find_orders_by_no(self.db, "DD001")), 1)
        self.assertGreaterEqual(result.failed_rows, 1)

    def test_amount_mismatch_creates_anomaly(self):
        import_excel(self.db, {"订单": self._order_df("99.00")}, "order")
        orders = order_service.find_orders_by_no(self.db, "DD001")
        self.assertEqual(orders[0]["status"], "金额异常")
        anomalies = order_service.detect_anomalies(self.db)
        self.assertTrue((anomalies["异常类型"] == "明细金额异常").any())

    def test_multi_item_order_total(self):
        df = pd.DataFrame(
            {
                "订单编号": ["DD002", "DD002"],
                "客户编码": ["KH001", "KH001"],
                "客户名称": ["测试客户", "测试客户"],
                "商品编码": ["SP001", "SP002"],
                "商品名称": ["测试商品", "测试商品二"],
                "商品规格": ["200g*24瓶", "500g*12瓶"],
                "订单日期": ["2026-02-01", "2026-02-01"],
                "订单数量": [1, 7],
                "单价": ["10.00", "0.20"],
                "金额": ["10.00", "1.40"],
            }
        )
        _, result = import_excel(self.db, {"订单": df}, "order", filename="多明细.xlsx")
        self.assertEqual(result.success_rows, 2)
        orders = order_service.find_orders_by_no(self.db, "DD002")
        self.assertEqual(to_decimal(orders[0]["total_amount"]), Decimal("11.40"))


if __name__ == "__main__":
    unittest.main()

