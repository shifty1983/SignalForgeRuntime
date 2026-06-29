from __future__ import annotations

import json
from os import PathLike
from pathlib import Path
from typing import Any, Mapping

from src.backtesting.historical_research_evidence_review_final_summary.builder import (
    build_historical_research_evidence_review_final_summary,
)


OPERATION_SCHEMA_VERSION = "historical_research_evidence_review_final_summary_operation.v1"
EVENT_SCHEMA_VERSION = "historical_research_evidence_review_final_summary_operation_event.v1"
AUDIT_SCHEMA_VERSION = "historical_research_evidence_review_final_summary_audit.v1"
HEALTH_SCHEMA_VERSION = "historical_research_evidence_review_final_summary_health.v1"

OPERATION_TYPE = "historical_research_evidence_review_final_summary_operation"


def run_historical_research_evidence_review_final_summary_operation(
    source: Any,
    *,
    event_log_path: str | PathLike[str] | None = None,
) -> dict[str, Any]:
    """Run a deterministic historical research evidence review final summary operation.

    This operation does not call QuantConnect, brokers, market-data services,
    order-routing systems, live-trading APIs, fill engines, slippage engines,
    or external data warehouses. It only wraps an existing local evidence review
    artifact with final-summary, operation, audit, and health outputs.
    """

    final_summary = build_historical_research_evidence_review_final_summary(source)
    audit_report = build_historical_research_evidence_review_final_summary_audit_report(
        final_summary
    )
    health_report = (
        build_historical_research_evidence_review_final_summary_health_report(
            final_summary
        )
    )

    events = [
        _build_event(
            final_summary=final_summary,
            event_type=(
                "historical_research_evidence_review_final_summary_operation_started"
            ),
            sequence=1,
        ),
        _build_event(
            final_summary=final_summary,
            event_type=(
                "historical_research_evidence_review_final_summary_operation_completed"
            ),
            sequence=2,
        ),
    ]

    normalized_log_path = _normalize_event_log_path(event_log_path)
    if normalized_log_path is not None:
        _write_jsonl_event_log(normalized_log_path, events)

    operation_record = _build_operation_record(
        final_summary=final_summary,
        audit_report=audit_report,
        health_report=health_report,
        event_log_path=normalized_log_path,
    )

    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": final_summary["status"],
        "operation_record": operation_record,
        "audit_report": audit_report,
        "health_report": health_report,
        "final_summary": final_summary,
        "events": events,
        "event_log_path": str(normalized_log_path) if normalized_log_path else None,
        "explicit_exclusions": list(final_summary.get("explicit_exclusions", [])),
    }


def build_historical_research_evidence_review_final_summary_audit_report(
    final_summary: Mapping[str, Any],
) -> dict[str, Any]:
    final_items = _as_list(final_summary.get("final_review_items"))

    checks = [
        _check(
            name="final_summary_schema_version_present",
            passed=bool(final_summary.get("schema_version")),
            severity="blocker",
            message="final summary schema version is present",
            failure_message="final summary schema version is missing",
        ),
        _check(
            name="summary_type_is_historical_research_evidence_review_final_summary",
            passed=final_summary.get("summary_type")
            == "historical_research_evidence_review_final_summary",
            severity="blocker",
            message="summary type is historical research evidence review final summary",
            failure_message="unexpected final summary type detected",
        ),
        _check(
            name="explicit_exclusions_present",
            passed=_has_required_exclusions(final_summary),
            severity="blocker",
            message="manual-only exclusions are present",
            failure_message="one or more required exclusions are missing",
        ),
        _check(
            name="final_item_count_matches_summary",
            passed=_final_item_count_matches_summary(final_summary),
            severity="blocker",
            message="final item count matches summary",
            failure_message="final item count does not match summary",
        ),
        _check(
            name="ready_final_summary_has_final_items",
            passed=len(final_items) > 0
            if final_summary.get("status") == "ready"
            else True,
            severity="blocker",
            message="ready final summary has final review items",
            failure_message="ready final summary is missing final review items",
        ),
        _check(
            name="final_items_have_expected_type",
            passed=_items_have_type(
                final_items,
                "historical_research_evidence_review_final_item",
            ),
            severity="blocker",
            message="final review items have expected type",
            failure_message="one or more final review items have unexpected type",
        ),
        _check(
            name="ready_final_items_have_evidence_id",
            passed=_ready_items_have_key(final_items, "evidence_id")
            if final_summary.get("status") == "ready"
            else True,
            severity="warning",
            message="ready final items have evidence ids",
            failure_message="one or more ready final items are missing evidence ids",
        ),
        _check(
            name="ready_final_items_have_backtest_id",
            passed=_ready_items_have_key(final_items, "backtest_id")
            if final_summary.get("status") == "ready"
            else True,
            severity="warning",
            message="ready final items have backtest ids",
            failure_message="one or more ready final items are missing backtest ids",
        ),
        _check(
            name="ready_final_items_have_decision_evidence",
            passed=_ready_items_have_positive_count(
                final_items,
                "decision_event_count",
            )
            if final_summary.get("status") == "ready"
            else True,
            severity="warning",
            message="ready final items have decision evidence",
            failure_message="one or more ready final items are missing decision evidence",
        ),
        _check(
            name="ready_final_items_have_performance_evidence",
            passed=_ready_items_have_positive_count(
                final_items,
                "performance_metric_count",
            )
            if final_summary.get("status") == "ready"
            else True,
            severity="warning",
            message="ready final items have performance evidence",
            failure_message="one or more ready final items are missing performance evidence",
        ),
        _check(
            name="blocked_final_summary_has_reason",
            passed=_blocked_final_summary_has_reason(final_summary),
            severity="warning",
            message="blocked final summary reason handling is valid",
            failure_message="blocked final summary is missing blocked reasons",
        ),
    ]

    audit_summary = _summarize_checks(checks)

    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_audit_status(
            final_status=str(final_summary.get("status", "needs_review")),
            checks=checks,
        ),
        "summary": audit_summary,
        "checks": checks,
        "final_item_counts": _count_final_items(final_items),
        "explicit_exclusions": list(final_summary.get("explicit_exclusions", [])),
    }


def build_historical_research_evidence_review_final_summary_health_report(
    final_summary: Mapping[str, Any],
) -> dict[str, Any]:
    final_status = str(final_summary.get("status", "needs_review"))
    summary = _as_mapping(final_summary.get("summary"))

    indicators = {
        "final_status": final_status,
        "source_review_status": summary.get("source_review_status"),
        "source_review_type": summary.get("source_review_type"),
        "source_adapter_type": summary.get("source_adapter_type"),
        "backtest_id": summary.get("backtest_id"),
        "ready_final_item_count": _safe_int(summary.get("ready_final_item_count")),
        "needs_review_final_item_count": _safe_int(
            summary.get("needs_review_final_item_count")
        ),
        "blocked_final_item_count": _safe_int(
            summary.get("blocked_final_item_count")
        ),
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
        "status": _classify_health_status(final_status),
        "indicators": indicators,
        "recommendations": recommendations,
        "explicit_exclusions": list(final_summary.get("explicit_exclusions", [])),
    }


def _build_operation_record(
    *,
    final_summary: Mapping[str, Any],
    audit_report: Mapping[str, Any],
    health_report: Mapping[str, Any],
    event_log_path: Path | None,
) -> dict[str, Any]:
    summary = _as_mapping(final_summary.get("summary"))
    operation_id = _build_operation_id(summary)

    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "operation_id": operation_id,
        "status": final_summary.get("status", "needs_review"),
        "summary": {
            "source_review_status": summary.get("source_review_status", "needs_review"),
            "source_review_type": summary.get("source_review_type"),
            "source_adapter_type": summary.get("source_adapter_type"),
            "backtest_id": summary.get("backtest_id"),
            "final_status": final_summary.get("status", "needs_review"),
            "audit_status": audit_report.get("status", "needs_review"),
            "health_status": health_report.get("status", "degraded"),
            "ready_final_item_count": _safe_int(
                summary.get("ready_final_item_count")
            ),
            "needs_review_final_item_count": _safe_int(
                summary.get("needs_review_final_item_count")
            ),
            "blocked_final_item_count": _safe_int(
                summary.get("blocked_final_item_count")
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
        "explicit_exclusions": list(final_summary.get("explicit_exclusions", [])),
    }


def _build_event(
    *,
    final_summary: Mapping[str, Any],
    event_type: str,
    sequence: int,
) -> dict[str, Any]:
    summary = _as_mapping(final_summary.get("summary"))

    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "event_type": event_type,
        "sequence": sequence,
        "status": final_summary.get("status", "needs_review"),
        "summary": {
            "source_review_status": summary.get("source_review_status", "needs_review"),
            "backtest_id": summary.get("backtest_id"),
            "final_status": final_summary.get("status", "needs_review"),
            "ready_final_item_count": _safe_int(
                summary.get("ready_final_item_count")
            ),
            "needs_review_final_item_count": _safe_int(
                summary.get("needs_review_final_item_count")
            ),
            "blocked_final_item_count": _safe_int(
                summary.get("blocked_final_item_count")
            ),
            "decision_event_count": _safe_int(summary.get("decision_event_count")),
            "performance_metric_count": _safe_int(
                summary.get("performance_metric_count")
            ),
            "warning_count": _safe_int(summary.get("warning_count")),
            "blocked_reason_count": _safe_int(summary.get("blocked_reason_count")),
        },
        "explicit_exclusions": list(final_summary.get("explicit_exclusions", [])),
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
    final_status: str,
    checks: list[Mapping[str, Any]],
) -> str:
    if any(check.get("status") == "failed" for check in checks):
        return "blocked"

    if final_status == "blocked":
        return "blocked"

    if final_status == "needs_review":
        return "needs_review"

    if any(check.get("status") == "warning" for check in checks):
        return "needs_review"

    return "ready"


def _classify_health_status(final_status: str) -> str:
    if final_status == "ready":
        return "healthy"
    if final_status == "blocked":
        return "blocked"
    return "degraded"


def _build_health_recommendations(indicators: Mapping[str, Any]) -> list[str]:
    recommendations: list[str] = []

    if _safe_int(indicators.get("ready_final_item_count")) == 0 and indicators.get(
        "final_status"
    ) == "ready":
        recommendations.append("add ready final historical research evidence items")

    if _safe_int(indicators.get("needs_review_final_item_count")) > 0:
        recommendations.append("review needs-review final historical research items")

    if _safe_int(indicators.get("blocked_final_item_count")) > 0:
        recommendations.append("resolve blocked final historical research items")

    if _safe_int(indicators.get("decision_event_count")) == 0:
        recommendations.append("include decision evidence before final review")

    if _safe_int(indicators.get("performance_metric_count")) == 0:
        recommendations.append("include performance evidence before final review")

    if _safe_int(indicators.get("blocked_reason_count")) > 0:
        recommendations.append("resolve blocked reasons before final review promotion")

    if indicators.get("final_status") == "ready":
        recommendations.append("historical research evidence review final summary is ready")

    if not recommendations:
        recommendations.append("no health actions required")

    return sorted(set(recommendations))


def _has_required_exclusions(final_summary: Mapping[str, Any]) -> bool:
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

    exclusions = final_summary.get("explicit_exclusions")
    if not isinstance(exclusions, list):
        return False

    return required.issubset({str(item) for item in exclusions})


def _final_item_count_matches_summary(final_summary: Mapping[str, Any]) -> bool:
    summary = _as_mapping(final_summary.get("summary"))
    items = _as_list(final_summary.get("final_review_items"))

    counts = _count_final_items(items)

    return (
        counts["ready"] == _safe_int(summary.get("ready_final_item_count"))
        and counts["needs_review"]
        == _safe_int(summary.get("needs_review_final_item_count"))
        and counts["blocked"] == _safe_int(summary.get("blocked_final_item_count"))
    )


def _count_final_items(items: list[Any]) -> dict[str, int]:
    return {
        "ready": sum(
            1 for item in items if isinstance(item, Mapping) and item.get("status") == "ready"
        ),
        "needs_review": sum(
            1
            for item in items
            if isinstance(item, Mapping) and item.get("status") == "needs_review"
        ),
        "blocked": sum(
            1
            for item in items
            if isinstance(item, Mapping) and item.get("status") == "blocked"
        ),
    }


def _items_have_type(items: list[Any], item_type: str) -> bool:
    return all(
        isinstance(item, Mapping) and item.get("final_item_type") == item_type
        for item in items
    )


def _ready_items_have_key(items: list[Any], key: str) -> bool:
    ready_items = [
        item
        for item in items
        if isinstance(item, Mapping) and item.get("status") == "ready"
    ]
    return all(bool(item.get(key)) for item in ready_items)


def _ready_items_have_positive_count(items: list[Any], key: str) -> bool:
    ready_items = [
        item
        for item in items
        if isinstance(item, Mapping) and item.get("status") == "ready"
    ]
    return all(_safe_int(item.get(key)) > 0 for item in ready_items)


def _blocked_final_summary_has_reason(final_summary: Mapping[str, Any]) -> bool:
    if final_summary.get("status") != "blocked":
        return True

    blocked_reasons = final_summary.get("blocked_reasons")
    return isinstance(blocked_reasons, list) and len(blocked_reasons) > 0


def _build_operation_id(summary: Mapping[str, Any]) -> str:
    backtest_id = (
        summary.get("backtest_id")
        or "historical_research_evidence_review_final_summary"
    )
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
