"""生成带明显“测试数据”标识的端到端演示数据。

演示流程：
1. 创建演示客户和商品；
2. 生成演示订单 Excel 并走真实导入流程；
3. 生成演示发货 Excel 并走真实导入流程；
4. 执行客户/商品匹配日志刷新；
5. 执行订单发货核对；
6. 生成销售分析和 Excel 报表。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database.connection import get_db
from services import (
    customer_service,
    delivery_service,
    excel_service,
    import_service,
    matching_service,
    order_service,
    product_service,
    report_service,
    settings_service,
)
from utils.config import get_settings


PREFIX = "【测试数据】"


def _clear_existing_demo(db) -> None:
    existing = db["customers"].count_documents({"tenant_id": "default", "is_demo": True})
    if existing:
        settings_service.clear_demo_data(db)


def _write_excel(df: pd.DataFrame, path: Path, sheet_name: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)


def generate_demo_data(db, tenant_id: str = "default") -> dict[str, int]:
    _clear_existing_demo(db)
    settings = get_settings()
    settings.ensure_directories()

    customers = [
        {"customer_code": "TEST-KH001", "customer_name": f"{PREFIX}华东食品贸易有限公司", "contact": "张经理", "phone": "13800000001", "region": "华东", "address": "上海市浦东新区测试路 1 号", "is_demo": True},
        {"customer_code": "TEST-KH002", "customer_name": f"{PREFIX}华南调味品商行", "contact": "李经理", "phone": "13800000002", "region": "华南", "address": "广州市天河区测试路 2 号", "is_demo": True},
        {"customer_code": "TEST-KH003", "customer_name": f"{PREFIX}华北食品批发部", "contact": "王经理", "phone": "13800000003", "region": "华北", "address": "北京市朝阳区测试路 3 号", "is_demo": True},
        {"customer_code": "TEST-KH004", "customer_name": f"{PREFIX}重复手机号客户", "contact": "赵经理", "phone": "13800000003", "region": "华北", "address": "北京市测试路 4 号", "is_demo": True},
    ]
    products = [
        {"product_code": "TEST-SP001", "product_name": f"{PREFIX}香辣牛肉酱", "specification": "200g*24瓶", "unit": "箱", "category": "调味品", "price": "128.50", "is_demo": True},
        {"product_code": "TEST-SP002", "product_name": f"{PREFIX}香辣牛肉酱", "specification": "500g*12瓶", "unit": "箱", "category": "调味品", "price": "168.00", "is_demo": True},
        {"product_code": "TEST-SP003", "product_name": f"{PREFIX}香辣牛肉酱", "specification": "200克*24瓶", "unit": "箱", "category": "调味品", "price": "130.00", "is_demo": True},
        {"product_code": "TEST-SP004", "product_name": f"{PREFIX}牛油火锅底料", "specification": "150g*40袋", "unit": "箱", "category": "调味品", "price": "18.50", "is_demo": True},
        {"product_code": "TEST-SP005", "product_name": f"{PREFIX}特级生抽酱油", "specification": "500ml*12瓶", "unit": "箱", "category": "酱油", "price": "45.00", "is_demo": True},
    ]
    for customer in customers:
        customer_service.create_customer(db, customer, tenant_id=tenant_id, source="demo", allow_duplicate_code=True)
    for product in products:
        product_service.create_product(
            db,
            product,
            tenant_id=tenant_id,
            source="demo",
            allow_duplicate_code=True,
            allow_duplicate_identity=True,
        )

    order_rows = [
        {"订单编号": "TEST-DD-001", "客户编码": "TEST-KH001", "客户名称": f"{PREFIX}华东食品贸易有限公司", "商品编码": "TEST-SP001", "商品名称": f"{PREFIX}香辣牛肉酱", "商品规格": "200g*24瓶", "订单日期": "2026-01-15", "单位": "箱", "订单数量": 10, "单价": "128.50", "金额": "1285.00"},
        {"订单编号": "TEST-DD-001", "客户编码": "TEST-KH001", "客户名称": f"{PREFIX}华东食品贸易有限公司", "商品编码": "TEST-SP003", "商品名称": f"{PREFIX}香辣牛肉酱", "商品规格": "200克*24瓶", "订单日期": "2026-01-15", "单位": "箱", "订单数量": 5, "单价": "130.00", "金额": "650.00"},
        {"订单编号": "TEST-DD-002", "客户编码": "TEST-KH002", "客户名称": f"{PREFIX}华南调味品商行", "商品编码": "TEST-SP004", "商品名称": f"{PREFIX}牛油火锅底料", "商品规格": "150g*40袋", "订单日期": "2026-02-03", "单位": "箱", "订单数量": 20, "单价": "18.50", "金额": "370.00"},
        {"订单编号": "TEST-DD-003", "客户编码": "TEST-KH003", "客户名称": f"{PREFIX}华北食品批发部", "商品编码": "TEST-SP005", "商品名称": f"{PREFIX}特级生抽酱油", "商品规格": "500ml*12瓶", "订单日期": "2026-03-08", "单位": "箱", "订单数量": 5, "单价": "45.00", "金额": "225.00"},
        {"订单编号": "TEST-DD-004", "客户编码": "", "客户名称": f"{PREFIX}未建档客户", "商品编码": "TEST-SP001", "商品名称": f"{PREFIX}香辣牛肉酱", "商品规格": "200g*24瓶", "订单日期": "2026-03-12", "单位": "箱", "订单数量": 2, "单价": "128.50", "金额": "257.00"},
    ]
    delivery_rows = [
        {"发货单号": "TEST-FH-001", "订单编号": "TEST-DD-001", "客户编码": "TEST-KH001", "商品编码": "TEST-SP001", "发货日期": "2026-01-18", "发货数量": 6},
        {"发货单号": "TEST-FH-002", "订单编号": "TEST-DD-001", "客户编码": "TEST-KH001", "商品编码": "TEST-SP001", "发货日期": "2026-01-22", "发货数量": 4},
        {"发货单号": "TEST-FH-003", "订单编号": "TEST-DD-001", "客户编码": "TEST-KH001", "商品编码": "TEST-SP003", "发货日期": "2026-01-22", "发货数量": 5},
        {"发货单号": "TEST-FH-004", "订单编号": "TEST-DD-002", "客户编码": "TEST-KH002", "商品编码": "TEST-SP004", "发货日期": "2026-02-08", "发货数量": 12},
        {"发货单号": "TEST-FH-005", "订单编号": "TEST-DD-003", "客户编码": "TEST-KH003", "商品编码": "TEST-SP005", "发货日期": "2026-03-10", "发货数量": 6},
        {"发货单号": "TEST-FH-006", "订单编号": "TEST-DD-NOT-EXIST", "客户编码": "TEST-KH001", "商品编码": "TEST-SP001", "发货日期": "2026-03-15", "发货数量": 1},
    ]

    order_path = Path(settings.demo_dir) / "测试数据_订单.xlsx"
    delivery_path = Path(settings.demo_dir) / "测试数据_发货.xlsx"
    _write_excel(pd.DataFrame(order_rows), order_path, "销售订单")
    _write_excel(pd.DataFrame(delivery_rows), delivery_path, "发货记录")

    order_analysis = excel_service.analyze_file(
        db, order_path.read_bytes(), order_path.name, "order", sheet_name="销售订单"
    )
    for row in order_analysis.validation.rows:
        row["is_demo"] = True
    order_result = import_service.commit_import(
        db, order_analysis, tenant_id=tenant_id, duplicate_file_action="reimport", is_demo=True
    )

    delivery_analysis = excel_service.analyze_file(
        db, delivery_path.read_bytes(), delivery_path.name, "delivery", sheet_name="发货记录"
    )
    for row in delivery_analysis.validation.rows:
        row["is_demo"] = True
    delivery_result = import_service.commit_import(
        db, delivery_analysis, tenant_id=tenant_id, duplicate_file_action="reimport", is_demo=True
    )

    matching_service.refresh_matching_logs(db, tenant_id=tenant_id)
    detail, summary, _ = delivery_service.reconcile(db, tenant_id=tenant_id)

    report_dir = Path(settings.export_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    content, _ = report_service.export_report_bytes(db, "sales_summary", tenant_id=tenant_id)
    (report_dir / "演示销售汇总报表.xlsx").write_bytes(content)

    return {
        "customers": len(customers),
        "products": len(products),
        "orders": order_result.success_rows,
        "deliveries": delivery_result.success_rows,
        "matching_pending": matching_service.pending_matching_count(db, tenant_id),
        "reconciliation_partial": summary.get("部分发货", 0),
        "reconciliation_over": summary.get("超量发货", 0),
        "reconciliation_issues": summary.get("异常", 0),
    }


def main() -> int:
    try:
        db = get_db()
        result = generate_demo_data(db)
        print("演示数据生成完成：")
        for key, value in result.items():
            print(f"  {key}: {value}")
        print("演示 Excel 文件位于 data/demo/，演示报表位于 exports/演示销售汇总报表.xlsx")
        return 0
    except Exception as exc:
        from utils.errors import friendly_error

        print(f"演示数据生成失败：{friendly_error(exc)}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

