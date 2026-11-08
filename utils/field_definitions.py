"""导入类型、字段定义与别名。

不同企业 Excel 的列名可能不同，这里集中维护中文别名，配合界面手动映射。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from utils.errors import DataValidationError
from utils.string_utils import normalize_header


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    required: bool = False
    kind: str = "text"  # text/code/phone/date/money/number
    aliases: tuple[str, ...] = field(default_factory=tuple)
    example: str = ""
    note: str = ""


@dataclass(frozen=True)
class ImportSchema:
    key: str
    label: str
    description: str
    fields: tuple[FieldSpec, ...]
    key_fields: tuple[str, ...] = field(default_factory=tuple)

    @property
    def field_map(self) -> dict[str, FieldSpec]:
        return {item.key: item for item in self.fields}

    @property
    def required_fields(self) -> tuple[FieldSpec, ...]:
        return tuple(item for item in self.fields if item.required)

    def alias_lookup(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for item in self.fields:
            for alias in (item.label, item.key, *item.aliases):
                result[normalize_header(alias)] = item.key
        return result


CUSTOMER_SCHEMA = ImportSchema(
    key="customer",
    label="客户资料",
    description="导入客户编码、名称、联系人和手机号等基础资料。",
    fields=(
        FieldSpec("customer_code", "客户编码", False, "code", ("客户编号", "编码", "客户号", "客户ID"), "KH0001"),
        FieldSpec("customer_name", "客户名称", True, "text", ("客户全称", "经销商名称", "客户", "公司名称", "单位名称"), "华东食品贸易有限公司"),
        FieldSpec("contact", "联系人", False, "text", ("联系人姓名", "联络人", "负责人"), "张经理"),
        FieldSpec("phone", "手机号", False, "phone", ("联系电话", "手机号码", "电话", "联系方式", "手机"), "13800138000"),
        FieldSpec("region", "所属区域", False, "text", ("区域", "地区", "省份", "所在区域"), "华东"),
        FieldSpec("address", "详细地址", False, "text", ("地址", "客户地址", "收货地址"), "上海市浦东新区示例路 1 号"),
    ),
    key_fields=("customer_code", "phone", "customer_name"),
)

PRODUCT_SCHEMA = ImportSchema(
    key="product",
    label="商品资料",
    description="导入商品编码、名称、规格、单位和价格等基础资料。",
    fields=(
        FieldSpec("product_code", "商品编码", False, "code", ("商品编号", "产品编码", "货号", "产品编号", "编码"), "SP0001"),
        FieldSpec("product_name", "商品名称", True, "text", ("产品名称", "品名", "商品", "产品"), "香辣牛肉酱"),
        FieldSpec("specification", "商品规格", False, "text", ("规格", "包装规格", "产品规格"), "200g*24瓶"),
        FieldSpec("unit", "商品单位", False, "text", ("单位", "计量单位"), "箱"),
        FieldSpec("category", "商品分类", False, "text", ("分类", "类别", "产品分类", "品类"), "调味品"),
        FieldSpec("price", "商品价格", False, "money", ("价格", "单价", "售价", "商品单价"), "128.50"),
    ),
    key_fields=("product_code", "product_name", "specification"),
)

ORDER_SCHEMA = ImportSchema(
    key="order",
    label="销售订单",
    description="每行代表一个订单明细；同一订单编号的多行会自动合并为一张订单。",
    fields=(
        FieldSpec("order_no", "订单编号", True, "code", ("订单号", "单号", "销售订单号", "订单号码"), "DD202601001"),
        FieldSpec("customer_code", "客户编码", False, "code", ("客户编号", "客户号", "客户ID"), "KH0001"),
        FieldSpec("customer_name", "客户名称", False, "text", ("客户全称", "经销商名称", "客户", "公司名称"), "华东食品贸易有限公司"),
        FieldSpec("product_code", "商品编码", False, "code", ("商品编号", "产品编码", "货号", "产品编号"), "SP0001"),
        FieldSpec("product_name", "商品名称", False, "text", ("产品名称", "品名", "商品", "产品"), "香辣牛肉酱"),
        FieldSpec("specification", "商品规格", False, "text", ("规格", "包装规格", "产品规格"), "200g*24瓶"),
        FieldSpec("order_date", "订单日期", True, "date", ("下单日期", "日期", "销售日期", "开单日期"), "2026-01-15"),
        FieldSpec("unit", "商品单位", False, "text", ("单位", "计量单位"), "箱"),
        FieldSpec("quantity", "订单数量", True, "number", ("数量", "订购数量", "销售数量"), "10"),
        FieldSpec("unit_price", "单价", False, "money", ("商品单价", "售价", "价格"), "128.50"),
        FieldSpec("amount", "金额", False, "money", ("小计", "金额合计", "销售额", "明细金额"), "1285.00"),
    ),
    key_fields=("order_no", "product_code", "product_name", "specification"),
)

DELIVERY_SCHEMA = ImportSchema(
    key="delivery",
    label="发货记录",
    description="每行代表一次发货明细；一个订单可以对应多张发货单。",
    fields=(
        FieldSpec("delivery_no", "发货单号", True, "code", ("发货编号", "出库单号", "送货单号", "单据编号"), "FH202601001"),
        FieldSpec("order_no", "订单编号", True, "code", ("订单号", "销售订单号", "关联订单号"), "DD202601001"),
        FieldSpec("customer_code", "客户编码", False, "code", ("客户编号", "客户号", "客户ID"), "KH0001"),
        FieldSpec("product_code", "商品编码", True, "code", ("商品编号", "产品编码", "货号", "产品编号"), "SP0001"),
        FieldSpec("delivery_date", "发货日期", True, "date", ("出库日期", "送货日期", "日期"), "2026-01-18"),
        FieldSpec("quantity", "发货数量", True, "number", ("数量", "出库数量", "送货数量"), "8"),
    ),
    key_fields=("delivery_no",),
)

PAYMENT_SCHEMA = ImportSchema(
    key="payment",
    label="回款记录",
    description="导入客户回款单，用于后续财务核对。",
    fields=(
        FieldSpec("payment_no", "回款单号", True, "code", ("回款编号", "收款单号", "收款编号", "单据编号"), "HK202601001"),
        FieldSpec("customer_code", "客户编码", True, "code", ("客户编号", "客户号", "客户ID"), "KH0001"),
        FieldSpec("payment_date", "回款日期", True, "date", ("收款日期", "到账日期", "日期"), "2026-01-25"),
        FieldSpec("amount", "回款金额", True, "money", ("收款金额", "到账金额", "金额"), "1285.00"),
        FieldSpec("remark", "备注", False, "text", ("说明", "备注信息"), "银行转账"),
    ),
    key_fields=("payment_no",),
)

IMPORT_SCHEMAS: dict[str, ImportSchema] = {
    item.key: item
    for item in (CUSTOMER_SCHEMA, PRODUCT_SCHEMA, ORDER_SCHEMA, DELIVERY_SCHEMA, PAYMENT_SCHEMA)
}

IMPORT_TYPE_LABELS: dict[str, str] = {key: schema.label for key, schema in IMPORT_SCHEMAS.items()}


def schema_for(import_type: str) -> ImportSchema:
    schema = IMPORT_SCHEMAS.get(import_type)
    if schema is None:
        raise DataValidationError("未知的导入数据类型，请重新选择。")
    return schema


def field_label(import_type: str, field_key: str) -> str:
    schema = IMPORT_SCHEMAS.get(import_type)
    if schema and field_key in schema.field_map:
        return schema.field_map[field_key].label
    return field_key


def auto_map_columns(columns: Iterable[str], import_type: str) -> dict[str, str]:
    """根据别名自动识别，返回 {字段key: Excel列名}。"""

    schema = schema_for(import_type)
    lookup = schema.alias_lookup()
    mapping: dict[str, str] = {}
    used_fields: set[str] = set()
    for column in columns:
        normalized = normalize_header(column)
        field_key = lookup.get(normalized)
        if field_key and field_key not in used_fields:
            mapping[field_key] = str(column)
            used_fields.add(field_key)
    return mapping


def mapping_to_columns(mapping: dict[str, str | None]) -> dict[str, str]:
    return {field: column for field, column in mapping.items() if column}

