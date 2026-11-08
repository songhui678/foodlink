"""模糊匹配工具。

生产环境使用 RapidFuzz；如果依赖未安装（例如离线开发环境），
自动降级为 difflib，保证核心匹配流程仍可运行。
"""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any, Sequence

try:
    from rapidfuzz import fuzz as _rf_fuzz
    from rapidfuzz import process as _rf_process

    RAPIDFUZZ_AVAILABLE = True
except Exception:  # pragma: no cover
    _rf_fuzz = None
    _rf_process = None
    RAPIDFUZZ_AVAILABLE = False


def similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if RAPIDFUZZ_AVAILABLE:
        return float(_rf_fuzz.WRatio(left, right))
    return SequenceMatcher(None, left, right).ratio() * 100


def extract_suggestions(
    query: str,
    choices: Sequence[str],
    *,
    limit: int = 5,
    score_cutoff: float = 60.0,
) -> list[tuple[str, float, int]]:
    """返回 (候选文本, 分数, 索引) 列表，分数为 0-100。"""

    if not query or not choices:
        return []
    if RAPIDFUZZ_AVAILABLE:
        results = _rf_process.extract(
            query, choices, scorer=_rf_fuzz.WRatio, limit=limit, score_cutoff=score_cutoff
        )
        return [(str(item[0]), float(item[1]), int(item[2])) for item in results]

    scored = [
        (str(choice), similarity(query, str(choice)), index)
        for index, choice in enumerate(choices)
    ]
    scored = [item for item in scored if item[1] >= score_cutoff]
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:limit]


def explain_backend() -> dict[str, Any]:
    return {
        "rapidfuzz": RAPIDFUZZ_AVAILABLE,
        "backend": "RapidFuzz" if RAPIDFUZZ_AVAILABLE else "difflib（降级）",
    }

