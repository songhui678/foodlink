"""手机号与文本型编号处理。

Excel 中的手机号、客户编码、商品编码、订单编号必须按字符串处理，
不能变成科学计数法，也不能丢失前导零。
"""

from __future__ import annotations

import math
import re
import unicodedata
from typing import Any


def to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return unicodedata.normalize("NFKC", value).strip()
    if isinstance(value, bytes):
        for encoding in ("utf-8-sig", "gb18030", "latin-1"):
            try:
                return value.decode(encoding).strip()
            except UnicodeDecodeError:
                continue
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return ""
        if value.is_integer():
            return str(int(value))
        return format(value, "f").rstrip("0").rstrip(".")
    text = str(value).strip()
    if re.fullmatch(r"\d+\.0+", text):
        return text.split(".")[0]
    return text


def normalize_phone(value: Any) -> str:
    text = to_text(value)
    if not text:
        return ""
    if re.fullmatch(r"\d+(?:\.\d+)?[eE]\+?\d+", text):
        try:
            text = str(int(float(text)))
        except (ValueError, OverflowError):
            pass
    text = text.replace("－", "-").replace("—", "-").replace("－", "-")
    digits = re.sub(r"[^\d+]", "", text)
    digits = digits.replace("+", "")
    if digits.startswith("0086") and len(digits) == 15:
        digits = digits[4:]
    elif digits.startswith("86") and len(digits) == 13:
        digits = digits[2:]
    return digits


def code_key(value: Any) -> str:
    """编码匹配键：去除首尾空白，统一大写；保留字符串前导零。"""

    return to_text(value).strip().upper()


def is_mobile(value: Any) -> bool:
    return bool(re.fullmatch(r"1[3-9]\d{9}", normalize_phone(value)))


def is_valid_phone(value: Any) -> bool:
    phone = normalize_phone(value)
    if not phone:
        return False
    if re.fullmatch(r"1[3-9]\d{9}", phone):
        return True
    # 座机：区号 + 号码，允许 7-12 位数字
    return bool(re.fullmatch(r"0\d{9,11}", phone))


def mask_phone(value: Any) -> str:
    phone = normalize_phone(value)
    if len(phone) >= 7:
        return f"{phone[:3]}****{phone[-4:]}"
    return "****" if phone else ""

