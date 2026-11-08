"""统一异常类型与中文友好错误提示。"""

from __future__ import annotations

import re


class FoodLinkError(Exception):
    """所有业务异常基类。"""

    default_message = "操作未完成，请稍后重试。"

    def __init__(self, message: str | None = None, *, detail: str | None = None):
        self.user_message = message or self.default_message
        self.detail = detail
        super().__init__(self.user_message)


class DatabaseConnectionError(FoodLinkError):
    default_message = (
        "无法连接 MongoDB 数据库。请确认 MongoDB 已启动，并检查 .env 中的 MONGODB_URI 配置。"
    )


class DataValidationError(FoodLinkError):
    default_message = "数据校验未通过，请检查填写内容。"


class ImportValidationError(FoodLinkError):
    default_message = "Excel 数据校验未通过，请检查字段映射和错误数据。"


class ExportError(FoodLinkError):
    default_message = "报表导出失败，请稍后重试。"


class BackupError(FoodLinkError):
    default_message = "数据库备份或恢复失败，请检查备份文件和目录权限。"


class PermissionDeniedError(FoodLinkError):
    default_message = "当前操作不被允许。"


def friendly_error(exc: BaseException) -> str:
    """把异常转换为适合最终用户阅读的中文提示，不展示堆栈。"""

    if isinstance(exc, FoodLinkError):
        return exc.user_message

    if type(exc).__name__ == "ValidationError":
        try:
            errors = getattr(exc, "errors", lambda: [])()
            messages = []
            labels = {"customer_name": "客户名称", "product_name": "商品名称", "amount": "金额",
                      "quantity": "数量", "phone": "手机号", "price": "价格"}
            for item in errors:
                location = item.get("loc", ())
                field = labels.get(str(location[-1]) if location else "", str(location[-1]) if location else "字段")
                messages.append(f"{field}：{item.get('msg', '格式不正确')}")
            if messages:
                return "数据校验未通过；" + "；".join(messages[:5])
        except Exception:
            pass
        return "数据校验未通过，请检查填写内容。"

    text = str(exc or "").strip()
    if isinstance(exc, KeyError):
        key = text.strip("'\"")
        field_names = {
            "customer_code": "客户编码",
            "customer_name": "客户名称",
            "product_code": "商品编码",
            "product_name": "商品名称",
            "order_no": "订单编号",
            "delivery_no": "发货单号",
            "quantity": "数量",
            "amount": "金额",
            "phone": "手机号",
        }
        label = field_names.get(key, key)
        return f"未找到{label}字段，请检查 Excel 字段映射。"

    if "ServerSelectionTimeoutError" in type(exc).__name__ or "Connection refused" in text:
        return DatabaseConnectionError.default_message
    if "Authentication failed" in text or "auth" in text.lower() and "mongo" in text.lower():
        return "MongoDB 身份验证失败，请检查用户名和密码配置。"
    if "No such file or directory" in text:
        return "找不到所需文件或目录，请检查路径后重试。"
    if re.search(r"Permission denied|not writable", text, re.I):
        return "没有文件读写权限，请检查目录权限。"
    if "FileNotFoundError" in type(exc).__name__:
        return "找不到所需文件，请重新选择。"
    if "JSONDecodeError" in type(exc).__name__:
        return "文件格式不正确，无法解析。"

    # 不把原始堆栈或底层异常文本直接展示给用户
    return "操作未完成，请稍后重试。如问题持续，请查看 logs/foodlink.log 获取详细信息。"

