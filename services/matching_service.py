"""客户与商品智能匹配。

匹配优先级：
客户：编码完全一致 > 手机号完全一致 > 名称标准化后完全一致 > 模糊候选建议（不自动确认）。
商品：编码完全一致 > 名称 + 规格完全一致 > 名称标准化后完全一致（仅候选）> 模糊候选建议。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd
from pymongo.database import Database

from database.repositories.customer_repository import CustomerRepository
from database.repositories.log_repository import LogRepository
from database.repositories.order_repository import OrderRepository
from database.repositories.product_repository import ProductRepository
from utils.fuzzy import extract_suggestions, similarity
from utils.phone_utils import code_key
from utils.string_utils import normalize_name, normalize_spec


_customers = CustomerRepository()
_products = ProductRepository()
_orders = OrderRepository()
_logs = LogRepository()


STATUS_LABELS = {
    "matched": "已匹配",
    "unmatched": "未匹配",
    "multiple": "多条候选",
    "duplicate": "重复记录",
    "abnormal": "数据异常",
    "ignored": "已忽略",
}

METHOD_LABELS = {
    "code_exact": "客户/商品编码完全一致",
    "phone_exact": "手机号完全一致",
    "name_exact": "名称标准化后完全一致",
    "name_spec_exact": "名称 + 规格完全一致",
    "fuzzy_suggestion": "模糊匹配建议",
    "manual": "人工确认",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _candidate(doc: dict[str, Any], *, score: float | None = None, reason: str = "") -> dict[str, Any]:
    return {
        "id": doc.get("id") or str(doc.get("_id", "")),
        "customer_code": doc.get("customer_code", ""),
        "customer_name": doc.get("customer_name", ""),
        "contact": doc.get("contact", ""),
        "phone": doc.get("phone", ""),
        "region": doc.get("region", ""),
        "product_code": doc.get("product_code", ""),
        "product_name": doc.get("product_name", ""),
        "specification": doc.get("specification", ""),
        "unit": doc.get("unit", ""),
        "price": doc.get("price"),
        "score": round(float(score), 1) if score is not None else None,
        "reason": reason,
    }


def _outcome(
    *,
    status: str,
    method: str = "",
    matched: dict[str, Any] | None = None,
    candidates: list[dict[str, Any]] | None = None,
    message: str = "",
) -> dict[str, Any]:
    return {
        "status": status,
        "status_label": STATUS_LABELS.get(status, status),
        "match_method": method,
        "match_method_label": METHOD_LABELS.get(method, method),
        "matched": matched,
        "candidates": candidates or [],
        "message": message,
    }


def _fuzzy_customer_candidates(query: str, customers: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    if not query:
        return []
    choices = [normalize_name(item.get("customer_name", "")) for item in customers]
    suggestions = extract_suggestions(query, choices, limit=limit, score_cutoff=55)
    candidates: list[dict[str, Any]] = []
    for _, score, index in suggestions:
        item = customers[index]
        candidates.append(_candidate(item, score=score, reason="名称相似"))
    return candidates


def _fuzzy_product_candidates(query: str, products: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    if not query:
        return []
    choices = [normalize_name(item.get("product_name", "")) for item in products]
    suggestions = extract_suggestions(query, choices, limit=limit, score_cutoff=55)
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for _, score, index in suggestions:
        item = products[index]
        item_id = str(item.get("id", ""))
        if item_id in seen:
            continue
        seen.add(item_id)
        candidates.append(_candidate(item, score=score, reason="名称相似，请核对规格"))
    return candidates


def match_customer(
    db: Database,
    *,
    customer_code: Any = "",
    customer_name: Any = "",
    phone: Any = "",
    tenant_id: str = "default",
    include_suggestions: bool = True,
) -> dict[str, Any]:
    from utils.phone_utils import normalize_phone

    code = str(customer_code or "").strip()
    name = str(customer_name or "").strip()
    normalized_phone = normalize_phone(phone)
    name_key = normalize_name(name)
    code_value_key = code_key(code)

    if not code and not normalized_phone and not name:
        return _outcome(status="abnormal", message="客户编码、手机号和客户名称均为空，无法匹配。")

    if code_value_key:
        matches = _customers.find_by_code_key(db, code_value_key, tenant_id)
        if len(matches) == 1:
            return _outcome(
                status="matched",
                method="code_exact",
                matched=_candidate(matches[0], score=100, reason="客户编码一致"),
                message="按客户编码匹配成功。",
            )
        if len(matches) > 1:
            return _outcome(
                status="duplicate",
                method="code_exact",
                candidates=[_candidate(item, score=100, reason="客户编码重复") for item in matches],
                message=f"客户编码“{code}”对应 {len(matches)} 条客户资料，请人工选择。",
            )

    if normalized_phone:
        matches = _customers.find_by_phone(db, normalized_phone, tenant_id)
        if len(matches) == 1:
            return _outcome(
                status="matched",
                method="phone_exact",
                matched=_candidate(matches[0], score=100, reason="手机号一致"),
                message="按手机号匹配成功。",
            )
        if len(matches) > 1:
            return _outcome(
                status="multiple",
                method="phone_exact",
                candidates=[_candidate(item, score=100, reason="手机号相同") for item in matches],
                message=f"手机号对应 {len(matches)} 条客户资料，请人工选择。",
            )

    if name_key:
        matches = _customers.find_by_name_key(db, name_key, tenant_id)
        if len(matches) == 1:
            return _outcome(
                status="matched",
                method="name_exact",
                matched=_candidate(matches[0], score=100, reason="名称标准化后一致"),
                message="按客户名称匹配成功。",
            )
        if len(matches) > 1:
            return _outcome(
                status="multiple",
                method="name_exact",
                candidates=[_candidate(item, score=100, reason="客户名称相同") for item in matches],
                message=f"客户名称“{name}”对应 {len(matches)} 条资料，请人工选择。",
            )

    if include_suggestions:
        active = _customers.all_active(db, tenant_id)
        candidates = _fuzzy_customer_candidates(name_key, active)
        if candidates:
            return _outcome(
                status="unmatched",
                method="fuzzy_suggestion",
                candidates=candidates,
                message="未找到精确匹配。以下仅为模糊候选建议，不会自动确认。",
            )
    return _outcome(status="unmatched", message="未找到匹配客户，请手动选择或先新增客户。")


def match_product(
    db: Database,
    *,
    product_code: Any = "",
    product_name: Any = "",
    specification: Any = "",
    tenant_id: str = "default",
    include_suggestions: bool = True,
) -> dict[str, Any]:
    code = str(product_code or "").strip()
    name = str(product_name or "").strip()
    spec = str(specification or "").strip()
    name_key = normalize_name(name)
    spec_key = normalize_spec(spec)
    code_value_key = code_key(code)

    if not code and not name:
        return _outcome(status="abnormal", message="商品编码和商品名称均为空，无法匹配。")

    if code_value_key:
        matches = _products.find_by_code_key(db, code_value_key, tenant_id)
        if len(matches) == 1:
            return _outcome(
                status="matched",
                method="code_exact",
                matched=_candidate(matches[0], score=100, reason="商品编码一致"),
                message="按商品编码匹配成功。",
            )
        if len(matches) > 1:
            return _outcome(
                status="duplicate",
                method="code_exact",
                candidates=[_candidate(item, score=100, reason="商品编码重复") for item in matches],
                message=f"商品编码“{code}”对应 {len(matches)} 条商品资料，请人工选择。",
            )

    if name_key:
        same_name = _products.find_by_name_key(db, name_key, tenant_id)
        if spec_key:
            exact = [item for item in same_name if normalize_spec(item.get("specification", "")) == spec_key]
            if len(exact) == 1:
                return _outcome(
                    status="matched",
                    method="name_spec_exact",
                    matched=_candidate(exact[0], score=100, reason="名称与规格一致"),
                    message="按商品名称 + 规格匹配成功。",
                )
            if len(exact) > 1:
                return _outcome(
                    status="duplicate",
                    method="name_spec_exact",
                    candidates=[_candidate(item, score=100, reason="名称规格重复") for item in exact],
                    message="商品名称与规格对应多条记录，请人工选择。",
                )
            if same_name:
                return _outcome(
                    status="multiple",
                    method="name_exact",
                    candidates=[_candidate(item, score=90, reason="名称相同但规格不同") for item in same_name],
                    message="存在同名商品但规格不同，不能自动合并，请人工确认。",
                )
        else:
            if len(same_name) == 1 and not normalize_spec(same_name[0].get("specification", "")):
                return _outcome(
                    status="matched",
                    method="name_exact",
                    matched=_candidate(same_name[0], score=100, reason="名称一致且双方均无规格"),
                    message="商品名称一致且双方均无规格，匹配成功。",
                )
            if same_name:
                return _outcome(
                    status="multiple",
                    method="name_exact",
                    candidates=[_candidate(item, score=90, reason="名称相同，规格需人工确认") for item in same_name],
                    message="商品名称相同但未提供规格，不能自动确认，请人工选择。",
                )

    if include_suggestions:
        active = _products.all_active(db, tenant_id)
        candidates = _fuzzy_product_candidates(name_key or code_value_key, active)
        if candidates:
            return _outcome(
                status="unmatched",
                method="fuzzy_suggestion",
                candidates=candidates,
                message="未找到精确匹配。以下仅为模糊候选建议，请核对商品规格。",
            )
    return _outcome(status="unmatched", message="未找到匹配商品，请手动选择或先新增商品。")


def _log_document(
    *,
    entity_type: str,
    source_type: str,
    source_ref: str,
    outcome: dict[str, Any],
    input_code: str,
    input_name: str,
    input_phone: str = "",
    input_spec: str = "",
    order_no: str = "",
    tenant_id: str = "default",
) -> dict[str, Any]:
    matched = outcome.get("matched") or {}
    status = outcome.get("status", "unmatched")
    now = _now()
    return {
        "tenant_id": tenant_id,
        "entity_type": entity_type,
        "source_type": source_type,
        "source_ref": source_ref,
        "order_no": order_no,
        "input_code": input_code,
        "input_name": input_name,
        "input_phone": input_phone,
        "input_spec": input_spec,
        "status": status,
        "status_label": STATUS_LABELS.get(status, status),
        "match_method": outcome.get("match_method", ""),
        "matched_id": matched.get("id", ""),
        "matched_code": matched.get("customer_code") or matched.get("product_code") or "",
        "matched_name": matched.get("customer_name") or matched.get("product_name") or "",
        "candidates": outcome.get("candidates", []),
        "message": outcome.get("message", ""),
        "resolved": status == "matched",
        "resolved_at": now if status == "matched" else None,
        "created_at": now,
        "updated_at": now,
    }


def record_customer_match(
    db: Database,
    *,
    customer_code: str = "",
    customer_name: str = "",
    phone: str = "",
    source_type: str = "order_import",
    source_ref: str = "",
    order_no: str = "",
    tenant_id: str = "default",
) -> tuple[dict[str, Any], str]:
    outcome = match_customer(
        db, customer_code=customer_code, customer_name=customer_name, phone=phone, tenant_id=tenant_id
    )
    log = _log_document(
        entity_type="customer",
        source_type=source_type,
        source_ref=source_ref,
        outcome=outcome,
        input_code=str(customer_code or ""),
        input_name=str(customer_name or ""),
        input_phone=str(phone or ""),
        order_no=order_no or source_ref,
        tenant_id=tenant_id,
    )
    log_id = _logs.add_matching_log(db, log)
    return outcome, log_id


def record_product_match(
    db: Database,
    *,
    product_code: str = "",
    product_name: str = "",
    specification: str = "",
    source_type: str = "order_import",
    source_ref: str = "",
    order_no: str = "",
    tenant_id: str = "default",
) -> tuple[dict[str, Any], str]:
    outcome = match_product(
        db, product_code=product_code, product_name=product_name, specification=specification, tenant_id=tenant_id
    )
    log = _log_document(
        entity_type="product",
        source_type=source_type,
        source_ref=source_ref,
        outcome=outcome,
        input_code=str(product_code or ""),
        input_name=str(product_name or ""),
        input_spec=str(specification or ""),
        order_no=order_no or source_ref,
        tenant_id=tenant_id,
    )
    log_id = _logs.add_matching_log(db, log)
    return outcome, log_id


def list_matching_logs(db: Database, *, entity_type: str = "", status: str = "", search: str = "", skip: int = 0, limit: int = 100, tenant_id: str = "default") -> list[dict[str, Any]]:
    return _logs.list_matching_logs(
        db, tenant_id=tenant_id, entity_type=entity_type, status=status, search=search, skip=skip, limit=limit
    )


def pending_matching_count(db: Database, tenant_id: str = "default") -> int:
    return _logs.pending_matching_count(db, tenant_id)


def pending_matching_dataframe(db: Database, entity_type: str = "", status: str = "", tenant_id: str = "default") -> pd.DataFrame:
    logs = list_matching_logs(db, entity_type=entity_type, status=status or "", tenant_id=tenant_id, limit=2000)
    if status:
        logs = [item for item in logs if item.get("status") == status]
    elif not entity_type:
        logs = [item for item in logs if item.get("status") in {"unmatched", "multiple", "duplicate", "abnormal"}]
    rows = []
    for item in logs:
        rows.append(
            {
                "日志ID": item.get("id", ""),
                "类型": "客户" if item.get("entity_type") == "customer" else "商品",
                "来源": item.get("source_type", ""),
                "关联单号": item.get("order_no", ""),
                "输入编码": item.get("input_code", ""),
                "输入名称": item.get("input_name", ""),
                "状态": STATUS_LABELS.get(item.get("status", ""), item.get("status", "")),
                "匹配方式": METHOD_LABELS.get(item.get("match_method", ""), item.get("match_method", "")),
                "说明": item.get("message", ""),
                "候选数": len(item.get("candidates", []) or []),
                "已解决": "是" if item.get("resolved") else "否",
                "创建时间": item.get("created_at", ""),
            }
        )
    return pd.DataFrame(
        rows,
        columns=["日志ID", "类型", "来源", "关联单号", "输入编码", "输入名称", "状态", "匹配方式", "说明", "候选数", "已解决", "创建时间"],
    )


def candidate_customers(db: Database, search: str = "", tenant_id: str = "default", limit: int = 100) -> list[dict[str, Any]]:
    items = _customers.all_active(db, tenant_id)
    if search:
        needle = search.strip().lower()
        items = [
            item
            for item in items
            if needle in str(item.get("customer_name", "")).lower()
            or needle in str(item.get("customer_code", "")).lower()
            or needle in str(item.get("phone", ""))
        ]
    return items[:limit]


def candidate_products(db: Database, search: str = "", tenant_id: str = "default", limit: int = 100) -> list[dict[str, Any]]:
    items = _products.all_active(db, tenant_id)
    if search:
        needle = search.strip().lower()
        items = [
            item
            for item in items
            if needle in str(item.get("product_name", "")).lower()
            or needle in str(item.get("product_code", "")).lower()
            or needle in str(item.get("specification", "")).lower()
        ]
    return items[:limit]


def resolve_matching_log(
    db: Database,
    *,
    log_id: str,
    target_id: str,
    entity_type: str | None = None,
    apply_all: bool = False,
    tenant_id: str = "default",
) -> dict[str, Any]:
    log = _logs.get_matching_log(db, log_id)
    if not log:
        return {"ok": False, "message": "匹配日志不存在。"}
    entity = entity_type or log.get("entity_type", "")
    if entity == "customer":
        target = _customers.get(db, target_id)
        if not target:
            return {"ok": False, "message": "选择的客户不存在或已删除。"}
        order_no = log.get("order_no") or log.get("source_ref", "")
        _orders.update_by_order_no(
            db,
            order_no,
            {
                "customer_id": target.get("id"),
                "customer_code": target.get("customer_code", ""),
                "customer_name": target.get("customer_name", ""),
            },
            tenant_id,
        )
        if apply_all:
            query: dict[str, Any] = {"tenant_id": tenant_id}
            if log.get("input_code"):
                query["customer_code"] = log["input_code"]
            elif log.get("input_name"):
                query["customer_name"] = log["input_name"]
            db["sales_orders"].update_many(
                query,
                {"$set": {"customer_id": target.get("id"), "customer_code": target.get("customer_code", ""),
                          "customer_name": target.get("customer_name", "")}},
            )
        if order_no:
            recompute_order_status(db, order_no, tenant_id=tenant_id)
        matched_code = target.get("customer_code", "")
        matched_name = target.get("customer_name", "")
    elif entity == "product":
        target = _products.get(db, target_id)
        if not target:
            return {"ok": False, "message": "选择的商品不存在或已删除。"}
        order_no = log.get("order_no") or log.get("source_ref", "")
        update_data = {
            "product_id": target.get("id"),
            "product_code": target.get("product_code", ""),
            "product_name": target.get("product_name", ""),
            "specification": target.get("specification", ""),
            "unit": target.get("unit", ""),
        }
        item_query: dict[str, Any] = {"order_no": order_no}
        if log.get("input_code"):
            item_query["product_code"] = log["input_code"]
        elif log.get("input_name"):
            item_query["product_name"] = log["input_name"]
        db["sales_order_items"].update_many(item_query, {"$set": update_data})
        if apply_all:
            all_query: dict[str, Any] = {}
            if log.get("input_code"):
                all_query["product_code"] = log["input_code"]
            elif log.get("input_name"):
                all_query["product_name"] = log["input_name"]
            if all_query:
                db["sales_order_items"].update_many(all_query, {"$set": update_data})
        if order_no:
            recompute_order_status(db, order_no, tenant_id=tenant_id)
        matched_code = target.get("product_code", "")
        matched_name = target.get("product_name", "")
    else:
        return {"ok": False, "message": "未知的匹配类型。"}

    _logs.update_matching_log(
        db,
        log_id,
        {
            "status": "matched",
            "status_label": STATUS_LABELS["matched"],
            "matched_id": target.get("id"),
            "matched_code": matched_code,
            "matched_name": matched_name,
            "match_method": "manual",
            "message": "已由用户人工确认匹配关系。",
            "resolved": True,
            "resolved_at": _now(),
            "updated_at": _now(),
        },
    )
    return {"ok": True, "message": "匹配关系已保存，相关订单已更新。"}


def ignore_matching_log(db: Database, *, log_id: str) -> bool:
    return _logs.update_matching_log(
        db,
        log_id,
        {
            "status": "ignored",
            "status_label": STATUS_LABELS["ignored"],
            "resolved": True,
            "resolved_at": _now(),
            "updated_at": _now(),
            "message": "用户已忽略此匹配异常。",
        },
    )


def recompute_order_status(db: Database, order_no: str, *, tenant_id: str = "default") -> str:
    orders = _orders.find_by_order_no(db, order_no, tenant_id)
    if not orders:
        return ""
    status = "正常"
    for order in orders:
        items = _orders.get_items(db, order["id"])
        if not order.get("customer_id"):
            status = "待匹配"
            break
        if any(not item.get("product_id") for item in items):
            status = "待匹配"
            break
        if order.get("amount_mismatch") or any(item.get("amount_mismatch") for item in items):
            status = "金额异常"
            break
    _orders.update_by_order_no(db, order_no, {"status": status}, tenant_id)
    return status


def refresh_matching_logs(db: Database, *, tenant_id: str = "default", limit: int = 3000) -> int:
    """从订单/明细中补齐尚未生成的匹配日志，返回新增数量。"""

    created = 0
    orders = _orders.all_orders(db, tenant_id=tenant_id)
    for order in orders[:limit]:
        order_no = str(order.get("order_no", ""))
        if not order.get("customer_id"):
            existing = db["matching_logs"].count_documents(
                {"tenant_id": tenant_id, "entity_type": "customer", "order_no": order_no, "resolved": {"$ne": True}}
            )
            if not existing:
                record_customer_match(
                    db,
                    customer_code=order.get("customer_code", ""),
                    customer_name=order.get("customer_name", ""),
                    source_type="order_existing",
                    source_ref=order_no,
                    order_no=order_no,
                    tenant_id=tenant_id,
                )
                created += 1
        items = _orders.get_items(db, order["id"])
        for item in items:
            if item.get("product_id"):
                continue
            source_ref = f"{order_no}#{item.get('product_code') or item.get('product_name') or item.get('id')}"
            existing = db["matching_logs"].count_documents(
                {"tenant_id": tenant_id, "entity_type": "product", "source_ref": source_ref, "resolved": {"$ne": True}}
            )
            if not existing:
                record_product_match(
                    db,
                    product_code=item.get("product_code", ""),
                    product_name=item.get("product_name", ""),
                    specification=item.get("specification", ""),
                    source_type="order_existing",
                    source_ref=source_ref,
                    order_no=order_no,
                    tenant_id=tenant_id,
                )
                created += 1
    return created


def log_to_dataframe(logs: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for item in logs:
        rows.append(
            {
                "类型": "客户" if item.get("entity_type") == "customer" else "商品",
                "输入编码": item.get("input_code", ""),
                "输入名称": item.get("input_name", ""),
                "状态": STATUS_LABELS.get(item.get("status", ""), item.get("status", "")),
                "匹配方式": METHOD_LABELS.get(item.get("match_method", ""), item.get("match_method", "")),
                "匹配结果": item.get("matched_name", ""),
                "说明": item.get("message", ""),
                "创建时间": item.get("created_at", ""),
            }
        )
    return pd.DataFrame(rows, columns=["类型", "输入编码", "输入名称", "状态", "匹配方式", "匹配结果", "说明", "创建时间"])

