"""客户匹配优先级、多候选、模糊建议和数据异常测试。"""

from __future__ import annotations

import unittest

from services import customer_service, matching_service
from tests.helpers import MongoTestCase


class CustomerMatchingTests(MongoTestCase):
    def _create(self, code: str, name: str, phone: str = ""):
        return customer_service.create_customer(
            self.db,
            {"customer_code": code, "customer_name": name, "phone": phone, "region": "华东"},
        )

    def test_code_exact_match_priority(self):
        self._create("KH001", "测试客户甲", "13800000001")
        result = matching_service.match_customer(self.db, customer_code="KH001", customer_name="完全不相关")
        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["match_method"], "code_exact")

    def test_duplicate_phone_multiple_candidates(self):
        self._create("KH001", "测试客户甲", "13900000001")
        self._create("KH002", "测试客户乙", "13900000001")
        result = matching_service.match_customer(self.db, phone="13900000001")
        self.assertEqual(result["status"], "multiple")
        self.assertEqual(len(result["candidates"]), 2)
        self.assertIsNone(result["matched"])

    def test_fuzzy_name_suggestion_only(self):
        self._create("KH001", "华东食品贸易有限公司")
        result = matching_service.match_customer(self.db, customer_name="华东食品贸易公司")
        self.assertEqual(result["status"], "unmatched")
        self.assertEqual(result["match_method"], "fuzzy_suggestion")
        self.assertTrue(result["candidates"])
        self.assertIsNone(result["matched"])

    def test_missing_all_fields_is_abnormal(self):
        result = matching_service.match_customer(self.db)
        self.assertEqual(result["status"], "abnormal")

    def test_duplicate_customer_records_detected(self):
        self._create("KH001", "客户甲")
        self.db["customers"].insert_one(
            {
                "tenant_id": "default",
                "customer_code": "KH001",
                "customer_code_key": "KH001",
                "customer_name": "客户甲重复",
                "customer_name_key": "客户甲重复",
                "phone": "",
                "is_deleted": False,
            }
        )
        result = matching_service.match_customer(self.db, customer_code="KH001")
        self.assertEqual(result["status"], "duplicate")


if __name__ == "__main__":
    unittest.main()

