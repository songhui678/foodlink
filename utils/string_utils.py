"""字符串标准化工具。"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from utils.phone_utils import to_text


_PUNCTUATION = re.compile(r"[\s\u3000\-_—–·•,，.。;；:：/\\|()（）\[\]【】{}<>《》\"'“”‘’!！?？+*#&@%$￥¥]+")


def normalize_header(value: Any) -> str:
    text = unicodedata.normalize("NFKC", to_text(value)).lower()
    return _PUNCTUATION.sub("", text)


def normalize_text(value: Any) -> str:
    return unicodedata.normalize("NFKC", to_text(value)).strip()


def normalize_name(value: Any) -> str:
    """客户/商品名称标准化，仅用于精确匹配与候选提示。"""

    text = unicodedata.normalize("NFKC", to_text(value)).lower()
    text = _PUNCTUATION.sub("", text)
    return text


def normalize_spec(value: Any) -> str:
    """规格标准化：统一常见单位与乘号，但不改变原始字段。"""

    text = unicodedata.normalize("NFKC", to_text(value)).lower()
    text = text.replace("×", "*").replace("x", "*").replace("Ｘ", "*")
    text = text.replace("克", "g").replace("千克", "kg").replace("公斤", "kg")
    text = text.replace("毫升", "ml").replace("升", "l")
    text = text.replace("袋", "袋").replace("瓶", "瓶").replace("箱", "箱")
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"(\d)\s*\*\s*(\d)", r"\1*\2", text)
    return text


def is_blank(value: Any) -> bool:
    text = normalize_text(value)
    return text == "" or text.lower() in {"nan", "none", "null", "nat"}


def month_key(value: Any) -> str:
    text = to_text(value)
    return text[:7] if len(text) >= 7 else text

