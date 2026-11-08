"""使用 PyMongo 创建业务索引。"""

from __future__ import annotations

from pymongo.database import Database

from utils.logger import get_logger


INDEX_DEFINITIONS: dict[str, list[tuple[str, list[tuple[str, int]], dict]]] = {
    "customers": [
        ("idx_tenant_code", [("tenant_id", 1), ("customer_code_key", 1)], {}),
        ("idx_tenant_phone", [("tenant_id", 1), ("phone", 1)], {}),
        ("idx_tenant_name", [("tenant_id", 1), ("customer_name_key", 1)], {}),
        ("idx_tenant_active", [("tenant_id", 1), ("is_deleted", 1)], {}),
        ("idx_created", [("created_at", -1)], {}),
    ],
    "products": [
        ("idx_tenant_code", [("tenant_id", 1), ("product_code_key", 1)], {}),
        ("idx_tenant_name_spec", [("tenant_id", 1), ("product_name_key", 1), ("spec_key", 1)], {}),
        ("idx_tenant_active", [("tenant_id", 1), ("is_deleted", 1)], {}),
        ("idx_category", [("category", 1)], {}),
    ],
    "sales_orders": [
        ("idx_tenant_order_no", [("tenant_id", 1), ("order_no", 1)], {}),
        ("idx_tenant_customer", [("tenant_id", 1), ("customer_id", 1)], {}),
        ("idx_tenant_date", [("tenant_id", 1), ("order_date", 1)], {}),
        ("idx_status", [("status", 1)], {}),
        ("idx_batch", [("import_batch_id", 1)], {}),
    ],
    "sales_order_items": [
        ("idx_order", [("order_id", 1)], {}),
        ("idx_order_no", [("order_no", 1), ("product_code", 1)], {}),
        ("idx_product", [("product_id", 1)], {}),
    ],
    "delivery_records": [
        ("idx_delivery_no", [("tenant_id", 1), ("delivery_no", 1)], {}),
        ("idx_order_no", [("tenant_id", 1), ("order_no", 1)], {}),
        ("idx_order_product", [("order_no", 1), ("product_code", 1)], {}),
        ("idx_delivery_date", [("delivery_date", 1)], {}),
        ("idx_batch", [("import_batch_id", 1)], {}),
    ],
    "payment_records": [
        ("idx_payment_no", [("tenant_id", 1), ("payment_no", 1)], {}),
        ("idx_customer", [("tenant_id", 1), ("customer_code", 1)], {}),
        ("idx_payment_date", [("payment_date", 1)], {}),
    ],
    "import_batches": [
        ("idx_batch_id", [("batch_id", 1)], {"unique": True}),
        ("idx_file_hash", [("tenant_id", 1), ("file_hash", 1), ("import_type", 1)], {}),
        ("idx_created", [("created_at", -1)], {}),
    ],
    "import_logs": [
        ("idx_batch", [("batch_id", 1)], {}),
        ("idx_created", [("created_at", -1)], {}),
    ],
    "matching_logs": [
        ("idx_tenant_type_status", [("tenant_id", 1), ("entity_type", 1), ("status", 1)], {}),
        ("idx_source_ref", [("source_ref", 1)], {}),
        ("idx_created", [("created_at", -1)], {}),
    ],
    "error_logs": [
        ("idx_tenant_type", [("tenant_id", 1), ("error_type", 1)], {}),
        ("idx_batch", [("batch_id", 1)], {}),
        ("idx_created", [("created_at", -1)], {}),
    ],
    "field_mapping_configs": [
        ("idx_mapping", [("tenant_id", 1), ("import_type", 1), ("name", 1)], {"unique": True}),
    ],
    "system_settings": [
        ("idx_setting_key", [("tenant_id", 1), ("key", 1)], {"unique": True}),
    ],
}


def ensure_indexes(db: Database) -> list[str]:
    logger = get_logger()
    created: list[str] = []
    for collection_name, indexes in INDEX_DEFINITIONS.items():
        collection = db[collection_name]
        for name, keys, options in indexes:
            try:
                collection.create_index(keys, name=name, **options)
                created.append(f"{collection_name}.{name}")
            except Exception as exc:
                logger.warning("创建索引失败 %s.%s：%s", collection_name, name, type(exc).__name__)
    return created


def drop_test_database(db: Database) -> None:
    """仅供测试清理使用，调用方必须确认 db.name 包含 test。"""

    if "test" not in db.name.lower():
        raise ValueError("拒绝删除非测试数据库")
    db.client.drop_database(db.name)

