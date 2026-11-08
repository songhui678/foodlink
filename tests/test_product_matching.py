"""商品编码、名称+规格、同名不同规格测试。"""

from __future__ import annotations

import unittest

from services import matching_service, product_service
from tests.helpers import MongoTestCase


class ProductMatchingTests(MongoTestCase):
    def _create(self, code: str, name: str, spec: str):
        return product_service.create_product(
            self.db,
            {"product_code": code, "product_name": name, "specification": spec, "unit": "箱", "category": "调味品", "price": "10.00"},
        )

    def test_code_exact_match(self):
        self._create("SP001", "香辣牛肉酱", "200g*24瓶")
        result = matching_service.match_product(self.db, product_code="SP001", product_name="任意名称")
        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["match_method"], "code_exact")

    def test_name_and_spec_exact_match(self):
        self._create("SP001", "香辣牛肉酱", "200g*24瓶")
        result = matching_service.match_product(
            self.db, product_name="香辣牛肉酱", specification="200g*24瓶"
        )
        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["match_method"], "name_spec_exact")

    def test_spec_difference_not_auto_merged(self):
        self._create("SP001", "香辣牛肉酱", "200g*24瓶")
        self._create("SP002", "香辣牛肉酱", "500g*12瓶")
        result = matching_service.match_product(
            self.db, product_name="香辣牛肉酱", specification="350g*10瓶"
        )
        self.assertEqual(result["status"], "multiple")
        self.assertIsNone(result["matched"])
        self.assertEqual(len(result["candidates"]), 2)

    def test_name_only_with_different_spec_is_candidate(self):
        self._create("SP001", "香辣牛肉酱", "200g*24瓶")
        self._create("SP002", "香辣牛肉酱", "500g*12瓶")
        result = matching_service.match_product(self.db, product_name="香辣牛肉酱", specification="")
        self.assertEqual(result["status"], "multiple")
        self.assertIsNone(result["matched"])

    def test_missing_product_identity_is_abnormal(self):
        result = matching_service.match_product(self.db, product_name="", product_code="")
        self.assertEqual(result["status"], "abnormal")


if __name__ == "__main__":
    unittest.main()

