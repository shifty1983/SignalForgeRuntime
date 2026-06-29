from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


SCHEMA_VERSION = "historical_research_evidence_review_bundle.v1"
REVIEW_TYPE = "normalized_historical_research_evidence_review"

EXPLICIT_EXCLUSIONS = [
    "quantconnect_api_calls",
    "broker_api_calls",
    "order_routing",
    "order_submission",
    "fills",
    "live_execution",
    "local_fill_simulation",
    "local_slippage_modeling",
    "external_data_warehouse_access",
]


def build_historical_research_evidence_review_bundle(
    source: Any,
) -> dict[str, Any]:
    """Build a compact historical research evidence review bundle.

    This builder does not call QuantConnect, brokers, market-data services,
    order-routing systems, live-trading APIs, fill engines, slippage engines,
    or external data warehouses. It only converts normalized historical research
    evidence intake into review-ready evidence items.
    """

    if not isinstance(source, Mapping):
        return _blocked_invalid_shape("source must be a mapping/dict")

    source_copy = deepcopy(dict(source))
    intake_bundle = _extract_intake_bundle(source_copy)

    if not intake_bundle:
        return _blocked_invalid_shape(
            "source is missing historical research evidence intake bundle"
        )

    intake_status = str(intake_bundle.get("status", "needs_review"))
    intake_summary = _as_mapping(intake_bundle.get("summary"))

    ready_items = _build_review_items(
        _as_list(intake_bundle.get("ready_evidence")),
        status="ready",
        intake_bundle=intake_bundle,
    )
    needs_review_items = _build_review_items(
        _as_list(intake_bundle.get("needs_review_evidence")),
        status="needs_review",
        intake_bundle=intake_bundle,
    )
    blocked_items = _build_review_items(
        _as_list(intake_bundle.get("blocked_evidence")),
        status="blocked",
        intake_bundle=intake_bundle,
    )

    warnings = []
    warnings.extend(_as_text_list(intake_bundle.get("warnings")))
    warnings.extend(_item_warnings(ready_items))
    warnings.extend(_item_warnings(needs_review_items))
    warnings.extend(_item_warnings(blocked_items))

    blocked_reasons = []
    blocked_reasons.extend(_as_text_list(intake_bundle.get("blocked_reasons")))
    blocked_reasons.extend(_item_blocked_reasons(blocked_items))

    warnings = _sorted_unique_text(warnings)
    blocked_reasons = _sorted_unique_text(blocked_reasons)

    status = _classify_review_status(
        intake_status=intake_status,
        ready_count=len(ready_items),
        needs_review_count=len(needs_review_items),
        blocked_count=len(blocked_items),
        blocked_reasons=blocked_reasons,
    )

    if status == "blocked" and not blocked_reasons:
        blocked_reasons.append("historical research evidence review is blocked")

    blocked_reasons = _sorted_unique_text(blocked_reasons)

    return {
        "schema_version": SCHEMA_VERSION,
        "review_type": REVIEW_TYPE,
        "status": status,
        "summary": {
            "source_intake_status": intake_status,
            "source_intake_type": intake_bundle.get("intake_type"),
            "source_schema_version": intake_bundle.get("schema_version"),
            "source_adapter_type": intake_summary.get("source_adapter_type"),
            "backtest_id": intake_summary.get("backtest_id"),
            "ready_review_item_count": len(ready_items),
            "needs_review_item_count": len(needs_review_items),
            "blocked_review_item_count": len(blocked_items),
            "source_ready_evidence_count": _safe_int(
                intake_summary.get("ready_evidence_count")
            ),
            "source_needs_review_evidence_count": _safe_int(
                intake_summary.get("needs_review_evidence_count")
            ),
            "source_blocked_evidence_count": _safe_int(
                intake_summary.get("blocked_evidence_count")
            ),
            "decision_event_count": _safe_int(intake_summary.get("decision_event_count")),
            "performance_metric_count": _safe_int(
                intake_summary.get("performance_metric_count")
            ),
            "expected_strategy_count": _safe_int(
                intake_summary.get("expected_strategy_count")
            ),
            "observed_strategy_count": _safe_int(
                intake_summary.get("observed_strategy_count")
            ),
            "expected_symbol_count": _safe_int(
                intake_summary.get("expected_symbol_count")
            ),
            "observed_symbol_count": _safe_int(
                intake_summary.get("observed_symbol_count")
            ),
            "warning_count": len(warnings),
            "blocked_reason_count": len(blocked_reasons),
        },
        "ready_review_items": ready_items,
        "needs_review_items": needs_review_items,
        "blocked_review_items": blocked_items,
        "warnings": warnings,
        "blocked_reasons": blocked_reasons,
        "source_intake_summary": {
            "schema_version": intake_bundle.get("schema_version"),
            "intake_type": intake_bundle.get("intake_type"),
            "status": intake_bundle.get("status"),
            "summary": _json_safe_mapping(intake_summary),
        },
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _blocked_invalid_shape(reason: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "review_type": REVIEW_TYPE,
        "status": "blocked",
        "summary": {
            "source_intake_status": "invalid_shape",
            "source_intake_type": None,
            "source_schema_version": None,
            "source_adapter_type": None,
            "backtest_id": None,
            "ready_review_item_count": 0,
            "needs_review_item_count": 0,
            "blocked_review_item_count": 0,
            "source_ready_evidence_count": 0,
            "source_needs_review_evidence_count": 0,
            "source_blocked_evidence_count": 0,
            "decision_event_count": 0,
            "performance_metric_count": 0,
            "expected_strategy_count": 0,
            "observed_strategy_count": 0,
            "expected_symbol_count": 0,
            "observed_symbol_count": 0,
            "warning_count": 0,
            "blocked_reason_count": 1,
        },
        "ready_review_items": [],
        "needs_review_items": [],
        "blocked_review_items": [],
        "warnings": [],
        "blocked_reasons": [reason],
        "source_intake_summary": {},
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _extract_intake_bundle(source: Mapping[str, Any]) -> dict[str, Any]:
    intake_bundle = source.get("intake_bundle")
    if isinstance(intake_bundle, Mapping):
        return dict(intake_bundle)

    if source.get("schema_version") == "historical_research_evidence_intake_bundle.v1":
        return dict(source)

    operation_result = source.get("operation_result")
    if isinstance(operation_result, Mapping):
        intake_bundle = operation_result.get("intake_bundle")
        if isinstance(intake_bundle, Mapping):
            return dict(intake_bundle)

    return {}


def _build_review_items(
    evidence_items: list[Any],
    *,
    status: str,
    intake_bundle: Mapping[str, Any],
) -> list[dict[str, Any]]:
    review_items = []

    for index, evidence in enumerate(evidence_items, start=1):
        if not isinstance(evidence, Mapping):
            continue

        review_items.append(
            _build_review_item(
                evidence,
                status=status,
                sequence=index,
                intake_bundle=intake_bundle,
            )
        )

    return sorted(
        review_items,
        key=lambda item: (
            item.get("evidence_source") or "",
            item.get("backtest_id") or "",
            ",".join(item.get("symbols", [])),
            item.get("sequence", 0),
        ),
    )


def _build_review_item(
    evidence: Mapping[str, Any],
    *,
    status: str,
    sequence: int,
    intake_bundle: Mapping[str, Any],
) -> dict[str, Any]:
    research_readiness = _as_mapping(evidence.get("research_readiness"))
    alignment_status = _as_mapping(evidence.get("alignment_status"))
    performance_snapshot = _as_mapping(evidence.get("performance_snapshot"))
    decision_snapshot = _as_mapping(evidence.get("decision_snapshot"))

    review_checks = _build_review_checks(
        research_readiness=research_readiness,
        alignment_status=alignment_status,
        evidence=evidence,
    )

    return {
        "review_item_type": "historical_research_evidence_review_item",
        "review_focus": "historical_backtest_evidence",
        "status": status,
        "sequence": sequence,
        "evidence_id": evidence.get("evidence_id"),
        "evidence_category": evidence.get("evidence_category"),
        "evidence_source": evidence.get("evidence_source"),
        "evidence_method": evidence.get("evidence_method"),
        "source_payload_type": evidence.get("source_payload_type"),
        "backtest_id": evidence.get("backtest_id"),
        "review_status": evidence.get("review_status"),
        "export_status": evidence.get("export_status"),
        "import_status": evidence.get("import_status"),
        "strategy_ids": _as_text_list(evidence.get("strategy_ids")),
        "symbols": _as_text_list(evidence.get("symbols")),
        "expected_strategy_count": _safe_int(evidence.get("expected_strategy_count")),
        "observed_strategy_count": _safe_int(evidence.get("observed_strategy_count")),
        "expected_symbol_count": _safe_int(evidence.get("expected_symbol_count")),
        "observed_symbol_count": _safe_int(evidence.get("observed_symbol_count")),
        "decision_event_count": _safe_int(evidence.get("decision_event_count")),
        "performance_metric_count": _safe_int(
            evidence.get("performance_metric_count")
        ),
        "readiness_summary": _build_readiness_summary(research_readiness),
        "alignment_status": _json_safe_mapping(alignment_status),
        "performance_snapshot": _json_safe_mapping(performance_snapshot),
        "decision_snapshot": _json_safe_mapping(decision_snapshot),
        "review_checks": review_checks,
        "review_actions": _build_review_actions(
            evidence_status=status,
            review_checks=review_checks,
            evidence=evidence,
        ),
        "warnings": _sorted_unique_text(_as_text_list(evidence.get("warnings"))),
        "blocked_reasons": _sorted_unique_text(
            _as_text_list(evidence.get("blocked_reasons"))
        ),
        "source_intake": {
            "schema_version": intake_bundle.get("schema_version"),
            "intake_type": intake_bundle.get("intake_type"),
            "status": intake_bundle.get("status"),
        },
    }


def _build_readiness_summary(
    research_readiness: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "can_enter_historical_research_review": bool(
            research_readiness.get("can_enter_historical_research_review")
        ),
        "has_strategy_alignment": bool(
            research_readiness.get("has_strategy_alignment")
        ),
        "has_symbol_alignment": bool(research_readiness.get("has_symbol_alignment")),
        "has_reported_count_alignment": bool(
            research_readiness.get("has_reported_count_alignment")
        ),
        "has_decision_evidence": bool(
            research_readiness.get("has_decision_evidence")
        ),
        "has_performance_evidence": bool(
            research_readiness.get("has_performance_evidence")
        ),
        "has_trade_count": bool(research_readiness.get("has_trade_count")),
        "has_risk_metric": bool(research_readiness.get("has_risk_metric")),
        "has_return_or_quality_metric": bool(
            research_readiness.get("has_return_or_quality_metric")
        ),
    }


def _build_review_checks(
    *,
    research_readiness: Mapping[str, Any],
    alignment_status: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> list[dict[str, Any]]:
    return [
        _review_check(
            name="can_enter_historical_research_review",
            passed=bool(
                research_readiness.get("can_enter_historical_research_review")
            ),
            message="evidence can enter historical research review",
            failure_message="evidence is not ready for historical research review",
        ),
        _review_check(
            name="strategy_alignment_present",
            passed=bool(alignment_status.get("strategies_match")),
            message="strategy alignment is present",
            failure_message="strategy alignment is missing or false",
        ),
        _review_check(
            name="symbol_alignment_present",
            passed=bool(alignment_status.get("symbols_match")),
            message="symbol alignment is present",
            failure_message="symbol alignment is missing or false",
        ),
        _review_check(
            name="reported_count_alignment_present",
            passed=bool(alignment_status.get("reported_count_matches_export")),
            message="reported count alignment is present",
            failure_message="reported count alignment is missing or false",
        ),
        _review_check(
            name="decision_evidence_present",
            passed=_safe_int(evidence.get("decision_event_count")) > 0,
            message="decision evidence is present",
            failure_message="decision evidence is missing",
        ),
        _review_check(
            name="performance_evidence_present",
            passed=_safe_int(evidence.get("performance_metric_count")) > 0,
            message="performance evidence is present",
            failure_message="performance evidence is missing",
        ),
    ]


def _review_check(
    *,
    name: str,
    passed: bool,
    message: str,
    failure_message: str,
) -> dict[str, Any]:
    if passed:
        return {
            "name": name,
            "status": "passed",
            "message": message,
        }

    return {
        "name": name,
        "status": "needs_review",
        "message": failure_message,
    }


def _build_review_actions(
    *,
    evidence_status: str,
    review_checks: list[Mapping[str, Any]],
    evidence: Mapping[str, Any],
) -> list[str]:
    actions = _as_text_list(evidence.get("recommended_research_actions"))

    for check in review_checks:
        if check.get("status") != "passed":
            actions.append(str(check.get("message")))

    if evidence_status == "ready":
        actions.append("include evidence in historical research review")

    if evidence_status == "blocked":
        actions.append("resolve blocked evidence before historical research review")

    return _sorted_unique_text(actions)


def _classify_review_status(
    *,
    intake_status: str,
    ready_count: int,
    needs_review_count: int,
    blocked_count: int,
    blocked_reasons: list[str],
) -> str:
    if intake_status == "blocked" or blocked_count > 0 or blocked_reasons:
        return "blocked"

    if intake_status == "ready" and ready_count > 0 and needs_review_count == 0:
        return "ready"

    if intake_status == "needs_review" or needs_review_count > 0:
        return "needs_review"

    return "needs_review"


def _item_warnings(items: list[Mapping[str, Any]]) -> list[str]:
    warnings: list[str] = []

    for item in items:
        warnings.extend(_as_text_list(item.get("warnings")))

    return warnings


def _item_blocked_reasons(items: list[Mapping[str, Any]]) -> list[str]:
    blocked_reasons: list[str] = []

    for item in items:
        blocked_reasons.extend(_as_text_list(item.get("blocked_reasons")))

    return blocked_reasons


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _as_text_list(value: Any) -> list[str]:
    if value is None:
        return []

    if isinstance(value, str):
        return [value.strip()] if value.strip() else []

    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]

    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]

    return [str(value).strip()] if str(value).strip() else []


def _sorted_unique_text(values: list[str]) -> list[str]:
    return sorted({value.strip() for value in values if value and value.strip()})


def _safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _json_safe_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}

    for key, item in value.items():
        if isinstance(item, Mapping):
            safe[str(key)] = _json_safe_mapping(item)
        elif isinstance(item, list):
            safe[str(key)] = [_json_safe_value(child) for child in item]
        elif isinstance(item, tuple):
            safe[str(key)] = [_json_safe_value(child) for child in item]
        elif isinstance(item, (str, int, float, bool)) or item is None:
            safe[str(key)] = item
        else:
            safe[str(key)] = str(item)

    return safe


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _json_safe_mapping(value)
    if isinstance(value, list):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
