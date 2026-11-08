"""Excel 读取、字段映射、前导零、空数据和错误导出测试。"""

from __future__ import annotations

import io
import zipfile
from decimal import Decimal

import pandas as pd
import unittest

from tests.helpers import dataframe_to_xlsx_bytes
from utils.excel_utils import export_errors_to_bytes, list_sheets, read_dataframe
from utils.field_definitions import auto_map_columns
from utils.phone_utils import normalize_phone, to_text
from utils.validator import validate_dataframe


class ExcelImportTests(unittest.TestCase):
    def test_normal_excel_read(self):
        df = pd.DataFrame({"客户编码": ["KH001"], "客户名称": ["测试客户"], "订单数量": [2]})
        content = dataframe_to_xlsx_bytes({"客户": df})
        loaded = read_dataframe(content, "客户.xlsx", sheet_name="客户", import_type="customer")
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded.iloc[0]["客户名称"], "测试客户")

    def test_multi_sheet_read(self):
        content = dataframe_to_xlsx_bytes(
            {"客户": pd.DataFrame({"客户名称": ["A"]}), "商品": pd.DataFrame({"商品名称": ["B"]})}
        )
        sheets = list_sheets(content, "多Sheet.xlsx")
        names = [item[0] for item in sheets]
        self.assertEqual(names, ["客户", "商品"])
        self.assertEqual(len(sheets), 2)

    def test_field_mapping_auto_detection(self):
        mapping = auto_map_columns(["客户编号", "经销商名称", "联系电话", "区域"], "customer")
        self.assertEqual(mapping.get("customer_code"), "客户编号")
        self.assertEqual(mapping.get("customer_name"), "经销商名称")
        self.assertEqual(mapping.get("phone"), "联系电话")
        self.assertEqual(mapping.get("region"), "区域")

    def test_phone_leading_zero_preserved(self):
        df = pd.DataFrame({"客户编码": ["000123"], "客户名称": ["测试"], "手机号": ["013800138000"]})
        content = dataframe_to_xlsx_bytes({"客户": df})
        loaded = read_dataframe(content, "客户.xlsx", sheet_name="客户", import_type="customer")
        self.assertEqual(to_text(loaded.iloc[0]["手机号"]), "013800138000")
        self.assertEqual(normalize_phone(loaded.iloc[0]["手机号"]), "013800138000")

    def test_customer_code_leading_zero_preserved(self):
        df = pd.DataFrame({"客户编码": ["000987"], "客户名称": ["测试"]})
        content = dataframe_to_xlsx_bytes({"客户": df})
        loaded = read_dataframe(content, "客户.xlsx", sheet_name="客户", import_type="customer")
        self.assertEqual(to_text(loaded.iloc[0]["客户编码"]), "000987")

    def test_empty_data_handling(self):
        df = pd.DataFrame({"客户编码": [], "客户名称": []})
        result = validate_dataframe(df, "customer", {"customer_code": "客户编码", "customer_name": "客户名称"})
        self.assertEqual(result.total_rows, 0)
        self.assertEqual(result.valid_count, 0)
        self.assertTrue(result.error_dataframe.empty)

    def test_error_data_export(self):
        df = pd.DataFrame({"客户编码": ["001"], "客户名称": [""]})
        result = validate_dataframe(df, "customer", {"customer_code": "客户编码", "customer_name": "客户名称"})
        content = export_errors_to_bytes(result.error_dataframe)
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            self.assertTrue(any(name.startswith("xl/") for name in zf.namelist()))

    def test_amount_precision_uses_decimal(self):
        from utils.decimal_utils import round_money, to_decimal

        total = to_decimal("0.1") * to_decimal("3") + to_decimal("0.2") * to_decimal("7")
        self.assertEqual(round_money(total), Decimal("1.70"))


if __name__ == "__main__":
    unittest.main()

