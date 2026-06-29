from __future__ import annotations

import json
from os import PathLike
from pathlib import Path
from typing import Any, Mapping

from src.backtesting.historical_research_evidence_promotion_gate.builder import (
    build_historical_research_evidence_promotion_gate,
)


OPERATION_SCHEMA_VERSION = "historical_research_evidence_promotion_gate_operation.v1"
EVENT_SCHEMA_VERSION = "historical_research_evidence_promotion_gate_operation_event.v1"
AUDIT_SCHEMA_VERSION = "historical_research_evidence_promotion_gate_audit.v1"
HEALTH_SCHEMA_VERSION = "historical_research_evidence_promotion_gate_health.v1"

OPERATION_TYPE = "historical_research_evidence_promotion_gate_operation"


def run_historical_research_evidence_promotion_gate_operation(
    source: Any,
    *,
    event_log_path: str | PathLike[str] | None = None,
) -> dict[str, Any]:
    """Run a deterministic historical research evidence promotion gate operation.

    This operation does not call QuantConnect, brokers, market-data services,
    order-routing systems, live-trading APIs, fill engines, slippage engines,
    or external data warehouses. It only wraps existing final reviewed evidence
    with promotion-gate, audit, and health outputs.
    """

    promotion_gate = build_historical_research_evidence_promotion_gate(source)
    audit_report = build_historical_research_evidence_promotion_gate_audit_report(
        promotion_gate
    )
    health_report = build_historical_research_evidence_promotion_gate_health_report(
        promotion_gate
    )

    events = [
        _build_event(
            promotion_gate=promotion_gate,
            event_type="historical_research_evidence_promotion_gate_operation_started",
            sequence=1,
        ),
        _build_event(
            promotion_gate=promotion_gate,
            event_type="historical_research_evidence_promotion_gate_operation_completed",
            sequence=2,
        ),
    ]

    normalized_log_path = _normalize_event_log_path(event_log_path)
    if normalized_log_path is not None:
        _write_jsonl_event_log(normalized_log_path, events)

    operation_record = _build_operation_record(
        promotion_gate=promotion_gate,
        audit_report=audit_report,
        health_report=health_report,
        event_log_path=normalized_log_path,
    )

    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": promotion_gate["status"],
        "operation_record": operation_record,
        "audit_report": audit_report,
        "health_report": health_report,
        "promotion_gate": promotion_gate,
        "events": events,
        "event_log_path": str(normalized_log_path) if normalized_log_path else None,
        "explicit_exclusions": list(promotion_gate.get("explicit_exclusions", [])),
    }


def build_historical_research_evidence_promotion_gate_audit_report(
    promotion_gate: Mapping[str, Any],
) -> dict[str, Any]:
    promotable_evidence = _as_list(promotion_gate.get("promotable_evidence"))
    needs_review_evidence = _as_list(promotion_gate.get("needs_review_evidence"))
    blocked_evidence = _as_list(promotion_gate.get("blocked_evidence"))

    checks = [
        _check(
            name="promotion_gate_schema_version_present",
            passed=bool(promotion_gate.get("schema_version")),
            severity="blocker",
            message="promotion gate schema version is present",
            failure_message="promotion gate schema version is missing",
        ),
        _check(
            name="gate_type_is_historical_research_evidence_promotion_gate",
            passed=promotion_gate.get("gate_type")
            == "historical_research_evidence_promotion_gate",
            severity="blocker",
            message="gate type is historical research evidence promotion gate",
            failure_message="unexpected promotion gate type detected",
        ),
        _check(
            name="explicit_exclusions_present",
            passed=_has_required_exclusions(promotion_gate),
            severity="blocker",
            message="manual-only exclusions are present",
            failure_message="one or more required exclusions are missing",
        ),
        _check(
            name="promotion_count_matches_summary",
            passed=_promotion_count_matches_summary(promotion_gate),
            severity="blocker",
            message="promotion counts match summary",
            failure_message="promotion counts do not match summary",
        ),
        _check(
            name="ready_gate_has_promotable_evidence",
            passed=len(promotable_evidence) > 0
            if promotion_gate.get("status") == "ready"
            else True,
            severity="blocker",
            message="ready promotion gate has promotable evidence",
            failure_message="ready promotion gate is missing promotable evidence",
        ),
        _check(
            name="promotable_evidence_has_expected_type",
            passed=_promotion_items_have_type(
                promotable_evidence,
                "historical_research_evidence_promotion_decision",
            ),
            severity="blocker",
            message="promotable evidence has expected promotion item type",
            failure_message="one or more promotable items have unexpected type",
        ),
        _check(
            name="promotable_evidence_has_evidence_id",
            passed=_items_have_key(promotable_evidence, "evidence_id")
            if promotion_gate.get("status") == "ready"
            else True,
            severity="warning",
            message="promotable evidence has evidence ids",
            failure_message="one or more promotable evidence items are missing evidence ids",
        ),
        _check(
            name="promotable_evidence_has_backtest_id",
            passed=_items_have_key(promotable_evidence, "backtest_id")
            if promotion_gate.get("status") == "ready"
            else True,
            severity="warning",
            message="promotable evidence has backtest ids",
            failure_message="one or more promotable evidence items are missing backtest ids",
        ),
        _check(
            name="promotable_evidence_has_decision_evidence",
            passed=_items_have_positive_count(
                promotable_evidence,
                "decision_event_count",
            )
            if promotion_gate.get("status") == "ready"
            else True,
            severity="warning",
            message="promotable evidence has decision evidence",
            failure_message="one or more promotable evidence items are missing decision evidence",
        ),
        _check(
            name="promotable_evidence_has_performance_evidence",
            passed=_items_have_positive_count(
                promotable_evidence,
                "performance_metric_count",
            )
            if promotion_gate.get("status") == "ready"
            else True,
            severity="warning",
            message="promotable evidence has performance evidence",
            failure_message="one or more promotable evidence items are missing performance evidence",
        ),
        _check(
            name="blocked_gate_has_reason",
            passed=_blocked_gate_has_reason(promotion_gate),
            severity="warning",
            message="blocked promotion gate reason handling is valid",
            failure_message="blocked promotion gate is missing blocked reasons",
        ),
    ]

    audit_summary = _summarize_checks(checks)

    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_audit_status(
            gate_status=str(promotion_gate.get("status", "needs_review")),
            checks=checks,
        ),
        "summary": audit_summary,
        "promotion_counts": {
            "promotable": len(promotable_evidence),
            "needs_review": len(needs_review_evidence),
            "blocked": len(blocked_evidence),
        },
        "checks": checks,
        "explicit_exclusions": list(promotion_gate.get("explicit_exclusions", [])),
    }


def build_historical_research_evidence_promotion_gate_health_report(
    promotion_gate: Mapping[str, Any],
) -> dict[str, Any]:
    gate_status = str(promotion_gate.get("status", "needs_review"))
    summary = _as_mapping(promotion_gate.get("summary"))

    indicators = {
        "gate_status": gate_status,
        "source_final_status": summary.get("source_final_status"),
        "source_summary_type": summary.get("source_summary_type"),
        "backtest_id": summary.get("backtest_id"),
        "promotable_evidence_count": _safe_int(
            summary.get("promotable_evidence_count")
        ),
        "needs_review_evidence_count": _safe_int(
            summary.get("needs_review_evidence_count")
        ),
        "blocked_evidence_count": _safe_int(summary.get("blocked_evidence_count")),
        "decision_event_count": _safe_int(summary.get("decision_event_count")),
        "performance_metric_count": _safe_int(summary.get("performance_metric_count")),
        "expected_strategy_count": _safe_int(summary.get("expected_strategy_count")),
        "observed_strategy_count": _safe_int(summary.get("observed_strategy_count")),
        "expected_symbol_count": _safe_int(summary.get("expected_symbol_count")),
        "observed_symbol_count": _safe_int(summary.get("observed_symbol_count")),
        "warning_count": _safe_int(summary.get("warning_count")),
        "blocked_reason_count": _safe_int(summary.get("blocked_reason_count")),
    }

    recommendations = _build_health_recommendations(indicators)

    return {
        "schema_version": HEALTH_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_health_status(gate_status),
        "indicators": indicators,
        "recommendations": recommendations,
        "explicit_exclusions": list(promotion_gate.get("explicit_exclusions", [])),
    }


def _build_operation_record(
    *,
    promotion_gate: Mapping[str, Any],
    audit_report: Mapping[str, Any],
    health_report: Mapping[str, Any],
    event_log_path: Path | None,
) -> dict[str, Any]:
    summary = _as_mapping(promotion_gate.get("summary"))
    operation_id = _build_operation_id(summary)

    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "operation_id": operation_id,
        "status": promotion_gate.get("status", "needs_review"),
        "summary": {
            "gate_status": promotion_gate.get("status", "needs_review"),
            "audit_status": audit_report.get("status", "needs_review"),
            "health_status": health_report.get("status", "degraded"),
            "source_final_status": summary.get("source_final_status"),
            "backtest_id": summary.get("backtest_id"),
            "promotable_evidence_count": _safe_int(
                summary.get("promotable_evidence_count")
            ),
            "needs_review_evidence_count": _safe_int(
                summary.get("needs_review_evidence_count")
            ),
            "blocked_evidence_count": _safe_int(
                summary.get("blocked_evidence_count")
            ),
            "decision_event_count": _safe_int(summary.get("decision_event_count")),
            "performance_metric_count": _safe_int(
                summary.get("performance_metric_count")
            ),
            "expected_strategy_count": _safe_int(
                summary.get("expected_strategy_count")
            ),
            "observed_strategy_count": _safe_int(
                summary.get("observed_strategy_count")
            ),
            "expected_symbol_count": _safe_int(summary.get("expected_symbol_count")),
            "observed_symbol_count": _safe_int(summary.get("observed_symbol_count")),
            "warning_count": _safe_int(summary.get("warning_count")),
            "blocked_reason_count": _safe_int(summary.get("blocked_reason_count")),
        },
        "event_log_path": str(event_log_path) if event_log_path else None,
        "explicit_exclusions": list(promotion_gate.get("explicit_exclusions", [])),
    }


def _build_event(
    *,
    promotion_gate: Mapping[str, Any],
    event_type: str,
    sequence: int,
) -> dict[str, Any]:
    summary = _as_mapping(promotion_gate.get("summary"))

    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "event_type": event_type,
        "sequence": sequence,
        "status": promotion_gate.get("status", "needs_review"),
        "summary": {
            "gate_status": promotion_gate.get("status", "needs_review"),
            "source_final_status": summary.get("source_final_status"),
            "backtest_id": summary.get("backtest_id"),
            "promotable_evidence_count": _safe_int(
                summary.get("promotable_evidence_count")
            ),
            "needs_review_evidence_count": _safe_int(
                summary.get("needs_review_evidence_count")
            ),
            "blocked_evidence_count": _safe_int(
                summary.get("blocked_evidence_count")
            ),
            "warning_count": _safe_int(summary.get("warning_count")),
            "blocked_reason_count": _safe_int(summary.get("blocked_reason_count")),
        },
        "explicit_exclusions": list(promotion_gate.get("explicit_exclusions", [])),
    }


def _write_jsonl_event_log(path: Path, events: list[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        for event in events:
            file.write(json.dumps(event, sort_keys=True))
            file.write("\n")


def _normalize_event_log_path(path: str | PathLike[str] | None) -> Path | None:
    if path is None:
        return None
    return Path(path)


def _check(
    *,
    name: str,
    passed: bool,
    severity: str,
    message: str,
    failure_message: str,
) -> dict[str, Any]:
    if passed:
        return {
            "name": name,
            "status": "passed",
            "severity": severity,
            "message": message,
        }

    failed_status = "failed" if severity == "blocker" else "warning"

    return {
        "name": name,
        "status": failed_status,
        "severity": severity,
        "message": failure_message,
    }


def _summarize_checks(checks: list[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "passed_count": sum(1 for check in checks if check.get("status") == "passed"),
        "warning_count": sum(1 for check in checks if check.get("status") == "warning"),
        "failed_count": sum(1 for check in checks if check.get("status") == "failed"),
        "check_count": len(checks),
    }


def _classify_audit_status(
    *,
    gate_status: str,
    checks: list[Mapping[str, Any]],
) -> str:
    if any(check.get("status") == "failed" for check in checks):
        return "blocked"

    if gate_status == "blocked":
        return "blocked"

    if gate_status == "needs_review":
        return "needs_review"

    if any(check.get("status") == "warning" for check in checks):
        return "needs_review"

    return "ready"


def _classify_health_status(gate_status: str) -> str:
    if gate_status == "ready":
        return "healthy"
    if gate_status == "blocked":
        return "blocked"
    return "degraded"


def _build_health_recommendations(indicators: Mapping[str, Any]) -> list[str]:
    recommendations: list[str] = []

    if _safe_int(indicators.get("promotable_evidence_count")) == 0 and indicators.get(
        "gate_status"
    ) == "ready":
        recommendations.append("add promotable historical research evidence")

    if _safe_int(indicators.get("needs_review_evidence_count")) > 0:
        recommendations.append("review needs-review promotion evidence")

    if _safe_int(indicators.get("blocked_evidence_count")) > 0:
        recommendations.append("resolve blocked promotion evidence")

    if _safe_int(indicators.get("decision_event_count")) == 0:
        recommendations.append("include decision evidence before promotion")

    if _safe_int(indicators.get("performance_metric_count")) == 0:
        recommendations.append("include performance evidence before promotion")

    if _safe_int(indicators.get("blocked_reason_count")) > 0:
        recommendations.append("resolve blocked reasons before promotion")

    if indicators.get("gate_status") == "ready":
        recommendations.append("historical research evidence promotion gate is ready")

    if not recommendations:
        recommendations.append("no health actions required")

    return sorted(set(recommendations))


def _has_required_exclusions(promotion_gate: Mapping[str, Any]) -> bool:
    required = {
        "quantconnect_api_calls",
        "broker_api_calls",
        "order_routing",
        "order_submission",
        "fills",
        "live_execution",
        "local_fill_simulation",
        "local_slippage_modeling",
        "external_data_warehouse_access",
    }

    exclusions = promotion_gate.get("explicit_exclusions")
    if not isinstance(exclusions, list):
        return False

    return required.issubset({str(item) for item in exclusions})


def _promotion_count_matches_summary(promotion_gate: Mapping[str, Any]) -> bool:
    summary = _as_mapping(promotion_gate.get("summary"))

    promotable_evidence = _as_list(promotion_gate.get("promotable_evidence"))
    needs_review_evidence = _as_list(promotion_gate.get("needs_review_evidence"))
    blocked_evidence = _as_list(promotion_gate.get("blocked_evidence"))

    return (
        len(promotable_evidence)
        == _safe_int(summary.get("promotable_evidence_count"))
        and len(needs_review_evidence)
        == _safe_int(summary.get("needs_review_evidence_count"))
        and len(blocked_evidence)
        == _safe_int(summary.get("blocked_evidence_count"))
    )


def _promotion_items_have_type(items: list[Any], item_type: str) -> bool:
    return all(
        isinstance(item, Mapping) and item.get("promotion_item_type") == item_type
        for item in items
    )


def _items_have_key(items: list[Any], key: str) -> bool:
    return all(isinstance(item, Mapping) and bool(item.get(key)) for item in items)


def _items_have_positive_count(items: list[Any], key: str) -> bool:
    return all(
        isinstance(item, Mapping) and _safe_int(item.get(key)) > 0
        for item in items
    )


def _blocked_gate_has_reason(promotion_gate: Mapping[str, Any]) -> bool:
    if promotion_gate.get("status") != "blocked":
        return True

    blocked_reasons = promotion_gate.get("blocked_reasons")
    return isinstance(blocked_reasons, list) and len(blocked_reasons) > 0


def _build_operation_id(summary: Mapping[str, Any]) -> str:
    backtest_id = summary.get("backtest_id") or "historical_research_evidence_promotion_gate"
    return f"{OPERATION_TYPE}::{backtest_id}"


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
