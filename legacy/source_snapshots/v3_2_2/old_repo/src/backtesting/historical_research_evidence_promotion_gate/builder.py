from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


SCHEMA_VERSION = "historical_research_evidence_promotion_gate.v1"
GATE_TYPE = "historical_research_evidence_promotion_gate"

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


def build_historical_research_evidence_promotion_gate(
    source: Any,
) -> dict[str, Any]:
    """Build a historical research evidence promotion gate.

    This builder does not call QuantConnect, brokers, market-data services,
    order-routing systems, live-trading APIs, fill engines, slippage engines,
    or external data warehouses. It only classifies existing final reviewed
    evidence into promotable / needs_review / blocked decisions.
    """

    if not isinstance(source, Mapping):
        return _blocked_invalid_shape("source must be a mapping/dict")

    source_copy = deepcopy(dict(source))
    final_summary = _extract_final_summary(source_copy)

    if not final_summary:
        return _blocked_invalid_shape(
            "source is missing historical research evidence review final summary"
        )

    final_status = str(final_summary.get("status", "needs_review"))
    final_summary_payload = _as_mapping(final_summary.get("summary"))

    decisions = _build_promotion_decisions(
        _as_list(final_summary.get("final_review_items"))
    )

    promotable_evidence = [
        decision
        for decision in decisions
        if decision.get("promotion_decision") == "promotable"
    ]
    needs_review_evidence = [
        decision
        for decision in decisions
        if decision.get("promotion_decision") == "needs_review"
    ]
    blocked_evidence = [
        decision
        for decision in decisions
        if decision.get("promotion_decision") == "blocked"
    ]

    warnings = []
    warnings.extend(_as_text_list(final_summary.get("warnings")))
    warnings.extend(_decision_warnings(decisions))

    blocked_reasons = []
    blocked_reasons.extend(_as_text_list(final_summary.get("blocked_reasons")))
    blocked_reasons.extend(_decision_blocked_reasons(decisions))

    warnings = _sorted_unique_text(warnings)
    blocked_reasons = _sorted_unique_text(blocked_reasons)

    status = _classify_gate_status(
        final_status=final_status,
        promotable_count=len(promotable_evidence),
        needs_review_count=len(needs_review_evidence),
        blocked_count=len(blocked_evidence),
        blocked_reasons=blocked_reasons,
    )

    if status == "blocked" and not blocked_reasons:
        blocked_reasons.append("historical research evidence promotion gate is blocked")

    blocked_reasons = _sorted_unique_text(blocked_reasons)

    return {
        "schema_version": SCHEMA_VERSION,
        "gate_type": GATE_TYPE,
        "status": status,
        "summary": {
            "source_final_status": final_status,
            "source_summary_type": final_summary.get("summary_type"),
            "source_schema_version": final_summary.get("schema_version"),
            "backtest_id": final_summary_payload.get("backtest_id"),
            "promotable_evidence_count": len(promotable_evidence),
            "needs_review_evidence_count": len(needs_review_evidence),
            "blocked_evidence_count": len(blocked_evidence),
            "source_ready_final_item_count": _safe_int(
                final_summary_payload.get("ready_final_item_count")
            ),
            "source_needs_review_final_item_count": _safe_int(
                final_summary_payload.get("needs_review_final_item_count")
            ),
            "source_blocked_final_item_count": _safe_int(
                final_summary_payload.get("blocked_final_item_count")
            ),
            "decision_event_count": _safe_int(
                final_summary_payload.get("decision_event_count")
            ),
            "performance_metric_count": _safe_int(
                final_summary_payload.get("performance_metric_count")
            ),
            "expected_strategy_count": _safe_int(
                final_summary_payload.get("expected_strategy_count")
            ),
            "observed_strategy_count": _safe_int(
                final_summary_payload.get("observed_strategy_count")
            ),
            "expected_symbol_count": _safe_int(
                final_summary_payload.get("expected_symbol_count")
            ),
            "observed_symbol_count": _safe_int(
                final_summary_payload.get("observed_symbol_count")
            ),
            "warning_count": len(warnings),
            "blocked_reason_count": len(blocked_reasons),
        },
        "promotable_evidence": promotable_evidence,
        "needs_review_evidence": needs_review_evidence,
        "blocked_evidence": blocked_evidence,
        "warnings": warnings,
        "blocked_reasons": blocked_reasons,
        "source_final_summary": {
            "schema_version": final_summary.get("schema_version"),
            "summary_type": final_summary.get("summary_type"),
            "status": final_summary.get("status"),
            "summary": _json_safe_mapping(final_summary_payload),
        },
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _blocked_invalid_shape(reason: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "gate_type": GATE_TYPE,
        "status": "blocked",
        "summary": {
            "source_final_status": "invalid_shape",
            "source_summary_type": None,
            "source_schema_version": None,
            "backtest_id": None,
            "promotable_evidence_count": 0,
            "needs_review_evidence_count": 0,
            "blocked_evidence_count": 0,
            "source_ready_final_item_count": 0,
            "source_needs_review_final_item_count": 0,
            "source_blocked_final_item_count": 0,
            "decision_event_count": 0,
            "performance_metric_count": 0,
            "expected_strategy_count": 0,
            "observed_strategy_count": 0,
            "expected_symbol_count": 0,
            "observed_symbol_count": 0,
            "warning_count": 0,
            "blocked_reason_count": 1,
        },
        "promotable_evidence": [],
        "needs_review_evidence": [],
        "blocked_evidence": [],
        "warnings": [],
        "blocked_reasons": [reason],
        "source_final_summary": {},
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _extract_final_summary(source: Mapping[str, Any]) -> dict[str, Any]:
    final_summary = source.get("final_summary")
    if isinstance(final_summary, Mapping):
        return dict(final_summary)

    if (
        source.get("schema_version")
        == "historical_research_evidence_review_final_summary.v1"
    ):
        return dict(source)

    operation_result = source.get("operation_result")
    if isinstance(operation_result, Mapping):
        final_summary = operation_result.get("final_summary")
        if isinstance(final_summary, Mapping):
            return dict(final_summary)

    pipeline_result = source.get("pipeline_result")
    if isinstance(pipeline_result, Mapping):
        final_summary = pipeline_result.get("final_summary")
        if isinstance(final_summary, Mapping):
            return dict(final_summary)

    return {}


def _build_promotion_decisions(
    final_items: list[Any],
) -> list[dict[str, Any]]:
    decisions = []

    for index, final_item in enumerate(final_items, start=1):
        if not isinstance(final_item, Mapping):
            continue

        decisions.append(_build_promotion_decision(final_item, sequence=index))

    return sorted(
        decisions,
        key=lambda decision: (
            decision.get("promotion_decision") or "",
            decision.get("evidence_source") or "",
            decision.get("backtest_id") or "",
            decision.get("evidence_id") or "",
        ),
    )


def _build_promotion_decision(
    final_item: Mapping[str, Any],
    *,
    sequence: int,
) -> dict[str, Any]:
    readiness_summary = _as_mapping(final_item.get("readiness_summary"))
    alignment_status = _as_mapping(final_item.get("alignment_status"))
    review_check_summary = _as_mapping(final_item.get("review_check_summary"))
    performance_snapshot = _as_mapping(final_item.get("performance_snapshot"))

    gate_checks = _build_gate_checks(
        final_item=final_item,
        readiness_summary=readiness_summary,
        alignment_status=alignment_status,
        review_check_summary=review_check_summary,
    )

    item_blocked_reasons = _sorted_unique_text(
        _as_text_list(final_item.get("blocked_reasons"))
    )

    promotion_decision = _classify_promotion_decision(
        final_item_status=str(final_item.get("status", "needs_review")),
        gate_checks=gate_checks,
        blocked_reasons=item_blocked_reasons,
    )

    return {
        "promotion_item_type": "historical_research_evidence_promotion_decision",
        "promotion_decision": promotion_decision,
        "sequence": sequence,
        "evidence_id": final_item.get("evidence_id"),
        "evidence_source": final_item.get("evidence_source"),
        "evidence_method": final_item.get("evidence_method"),
        "evidence_category": final_item.get("evidence_category"),
        "backtest_id": final_item.get("backtest_id"),
        "final_item_status": final_item.get("status"),
        "review_status": final_item.get("review_status"),
        "export_status": final_item.get("export_status"),
        "import_status": final_item.get("import_status"),
        "strategy_ids": _as_text_list(final_item.get("strategy_ids")),
        "symbols": _as_text_list(final_item.get("symbols")),
        "expected_strategy_count": _safe_int(
            final_item.get("expected_strategy_count")
        ),
        "observed_strategy_count": _safe_int(
            final_item.get("observed_strategy_count")
        ),
        "expected_symbol_count": _safe_int(final_item.get("expected_symbol_count")),
        "observed_symbol_count": _safe_int(final_item.get("observed_symbol_count")),
        "decision_event_count": _safe_int(final_item.get("decision_event_count")),
        "performance_metric_count": _safe_int(
            final_item.get("performance_metric_count")
        ),
        "readiness_summary": _json_safe_mapping(readiness_summary),
        "alignment_status": _json_safe_mapping(alignment_status),
        "performance_snapshot": _json_safe_mapping(performance_snapshot),
        "review_check_summary": _json_safe_mapping(review_check_summary),
        "gate_checks": gate_checks,
        "promotion_actions": _build_promotion_actions(
            promotion_decision=promotion_decision,
            gate_checks=gate_checks,
            final_item=final_item,
        ),
        "warnings": _sorted_unique_text(_as_text_list(final_item.get("warnings"))),
        "blocked_reasons": item_blocked_reasons,
    }


def _build_gate_checks(
    *,
    final_item: Mapping[str, Any],
    readiness_summary: Mapping[str, Any],
    alignment_status: Mapping[str, Any],
    review_check_summary: Mapping[str, Any],
) -> list[dict[str, Any]]:
    return [
        _gate_check(
            name="final_item_status_ready",
            passed=final_item.get("status") == "ready",
            message="final item status is ready",
            failure_message="final item status is not ready",
        ),
        _gate_check(
            name="evidence_id_present",
            passed=bool(final_item.get("evidence_id")),
            message="evidence id is present",
            failure_message="evidence id is missing",
        ),
        _gate_check(
            name="backtest_id_present",
            passed=bool(final_item.get("backtest_id")),
            message="backtest id is present",
            failure_message="backtest id is missing",
        ),
        _gate_check(
            name="decision_evidence_present",
            passed=_safe_int(final_item.get("decision_event_count")) > 0,
            message="decision evidence is present",
            failure_message="decision evidence is missing",
        ),
        _gate_check(
            name="performance_evidence_present",
            passed=_safe_int(final_item.get("performance_metric_count")) > 0,
            message="performance evidence is present",
            failure_message="performance evidence is missing",
        ),
        _gate_check(
            name="review_checks_passed",
            passed=_safe_int(review_check_summary.get("needs_review_count")) == 0
            and _safe_int(review_check_summary.get("passed_count")) > 0,
            message="review checks passed",
            failure_message="one or more review checks need review",
        ),
        _gate_check(
            name="historical_research_readiness_confirmed",
            passed=bool(
                readiness_summary.get("can_enter_historical_research_review")
            ),
            message="historical research readiness is confirmed",
            failure_message="historical research readiness is not confirmed",
        ),
        _gate_check(
            name="strategy_alignment_confirmed",
            passed=bool(alignment_status.get("strategies_match")),
            message="strategy alignment is confirmed",
            failure_message="strategy alignment is missing or false",
        ),
        _gate_check(
            name="symbol_alignment_confirmed",
            passed=bool(alignment_status.get("symbols_match")),
            message="symbol alignment is confirmed",
            failure_message="symbol alignment is missing or false",
        ),
    ]


def _gate_check(
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


def _classify_promotion_decision(
    *,
    final_item_status: str,
    gate_checks: list[Mapping[str, Any]],
    blocked_reasons: list[str],
) -> str:
    if final_item_status == "blocked" or blocked_reasons:
        return "blocked"

    if any(check.get("status") != "passed" for check in gate_checks):
        return "needs_review"

    return "promotable"


def _build_promotion_actions(
    *,
    promotion_decision: str,
    gate_checks: list[Mapping[str, Any]],
    final_item: Mapping[str, Any],
) -> list[str]:
    actions = _as_text_list(final_item.get("review_actions"))

    if promotion_decision == "promotable":
        actions.append("promote evidence to downstream historical research")

    if promotion_decision == "blocked":
        actions.append("resolve blocked evidence before promotion")

    for check in gate_checks:
        if check.get("status") != "passed":
            actions.append(str(check.get("message")))

    return _sorted_unique_text(actions)


def _classify_gate_status(
    *,
    final_status: str,
    promotable_count: int,
    needs_review_count: int,
    blocked_count: int,
    blocked_reasons: list[str],
) -> str:
    if final_status == "blocked" or blocked_count > 0 or blocked_reasons:
        return "blocked"

    if final_status == "needs_review" or needs_review_count > 0:
        return "needs_review"

    if final_status == "ready" and promotable_count > 0:
        return "ready"

    return "needs_review"


def _decision_warnings(decisions: list[Mapping[str, Any]]) -> list[str]:
    warnings: list[str] = []

    for decision in decisions:
        warnings.extend(_as_text_list(decision.get("warnings")))

    return warnings


def _decision_blocked_reasons(decisions: list[Mapping[str, Any]]) -> list[str]:
    blocked_reasons: list[str] = []

    for decision in decisions:
        blocked_reasons.extend(_as_text_list(decision.get("blocked_reasons")))

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
