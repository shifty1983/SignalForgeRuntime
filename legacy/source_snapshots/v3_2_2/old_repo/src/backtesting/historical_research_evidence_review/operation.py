from __future__ import annotations

import json
from os import PathLike
from pathlib import Path
from typing import Any, Mapping

from src.backtesting.historical_research_evidence_review.builder import (
    build_historical_research_evidence_review_bundle,
)


OPERATION_SCHEMA_VERSION = "historical_research_evidence_review_operation.v1"
EVENT_SCHEMA_VERSION = "historical_research_evidence_review_operation_event.v1"
AUDIT_SCHEMA_VERSION = "historical_research_evidence_review_audit.v1"
HEALTH_SCHEMA_VERSION = "historical_research_evidence_review_health.v1"

OPERATION_TYPE = "historical_research_evidence_review_operation"


def run_historical_research_evidence_review_operation(
    source: Any,
    *,
    event_log_path: str | PathLike[str] | None = None,
) -> dict[str, Any]:
    """Run a deterministic historical research evidence review operation.

    This operation does not call QuantConnect, brokers, market-data services,
    order-routing systems, live-trading APIs, fill engines, slippage engines,
    or external data warehouses. It only wraps an existing local historical
    research evidence intake artifact with operation, audit, and health outputs.
    """

    review_bundle = build_historical_research_evidence_review_bundle(source)
    audit_report = build_historical_research_evidence_review_audit_report(
        review_bundle
    )
    health_report = build_historical_research_evidence_review_health_report(
        review_bundle
    )

    events = [
        _build_event(
            review_bundle=review_bundle,
            event_type="historical_research_evidence_review_operation_started",
            sequence=1,
        ),
        _build_event(
            review_bundle=review_bundle,
            event_type="historical_research_evidence_review_operation_completed",
            sequence=2,
        ),
    ]

    normalized_log_path = _normalize_event_log_path(event_log_path)
    if normalized_log_path is not None:
        _write_jsonl_event_log(normalized_log_path, events)

    operation_record = _build_operation_record(
        review_bundle=review_bundle,
        audit_report=audit_report,
        health_report=health_report,
        event_log_path=normalized_log_path,
    )

    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": review_bundle["status"],
        "operation_record": operation_record,
        "audit_report": audit_report,
        "health_report": health_report,
        "review_bundle": review_bundle,
        "events": events,
        "event_log_path": str(normalized_log_path) if normalized_log_path else None,
        "explicit_exclusions": list(review_bundle.get("explicit_exclusions", [])),
    }


def build_historical_research_evidence_review_audit_report(
    review_bundle: Mapping[str, Any],
) -> dict[str, Any]:
    ready_items = _as_list(review_bundle.get("ready_review_items"))
    needs_review_items = _as_list(review_bundle.get("needs_review_items"))
    blocked_items = _as_list(review_bundle.get("blocked_review_items"))

    checks = [
        _check(
            name="review_schema_version_present",
            passed=bool(review_bundle.get("schema_version")),
            severity="blocker",
            message="review schema version is present",
            failure_message="review schema version is missing",
        ),
        _check(
            name="review_type_is_normalized_historical_research_evidence_review",
            passed=review_bundle.get("review_type")
            == "normalized_historical_research_evidence_review",
            severity="blocker",
            message="review type is normalized historical research evidence review",
            failure_message="unexpected review type detected",
        ),
        _check(
            name="explicit_exclusions_present",
            passed=_has_required_exclusions(review_bundle),
            severity="blocker",
            message="manual-only exclusions are present",
            failure_message="one or more required manual-only exclusions are missing",
        ),
        _check(
            name="review_item_count_matches_summary",
            passed=_review_item_count_matches_summary(review_bundle),
            severity="blocker",
            message="review item count matches review summary",
            failure_message="review item count does not match review summary",
        ),
        _check(
            name="ready_review_has_ready_item",
            passed=len(ready_items) > 0 if review_bundle.get("status") == "ready" else True,
            severity="blocker",
            message="ready review has ready review items",
            failure_message="ready review is missing ready review items",
        ),
        _check(
            name="ready_items_have_expected_type",
            passed=_items_have_type(
                ready_items,
                "historical_research_evidence_review_item",
            ),
            severity="blocker",
            message="ready review items have expected type",
            failure_message="one or more ready review items have unexpected type",
        ),
        _check(
            name="ready_items_have_evidence_id",
            passed=_items_have_key(ready_items, "evidence_id")
            if review_bundle.get("status") == "ready"
            else True,
            severity="warning",
            message="ready review items have evidence ids",
            failure_message="one or more ready review items are missing evidence ids",
        ),
        _check(
            name="ready_items_have_backtest_id",
            passed=_items_have_key(ready_items, "backtest_id")
            if review_bundle.get("status") == "ready"
            else True,
            severity="warning",
            message="ready review items have backtest ids",
            failure_message="one or more ready review items are missing backtest ids",
        ),
        _check(
            name="ready_items_have_decision_evidence",
            passed=_items_have_positive_count(ready_items, "decision_event_count")
            if review_bundle.get("status") == "ready"
            else True,
            severity="warning",
            message="ready review items have decision evidence",
            failure_message="one or more ready review items are missing decision evidence",
        ),
        _check(
            name="ready_items_have_performance_evidence",
            passed=_items_have_positive_count(ready_items, "performance_metric_count")
            if review_bundle.get("status") == "ready"
            else True,
            severity="warning",
            message="ready review items have performance evidence",
            failure_message="one or more ready review items are missing performance evidence",
        ),
        _check(
            name="blocked_review_has_reason",
            passed=_blocked_review_has_reason(review_bundle),
            severity="warning",
            message="blocked review reason handling is valid",
            failure_message="blocked review is missing blocked reasons",
        ),
    ]

    audit_summary = _summarize_checks(checks)

    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_audit_status(
            review_status=str(review_bundle.get("status", "needs_review")),
            checks=checks,
        ),
        "summary": audit_summary,
        "checks": checks,
        "review_item_counts": {
            "ready": len(ready_items),
            "needs_review": len(needs_review_items),
            "blocked": len(blocked_items),
        },
        "explicit_exclusions": list(review_bundle.get("explicit_exclusions", [])),
    }


def build_historical_research_evidence_review_health_report(
    review_bundle: Mapping[str, Any],
) -> dict[str, Any]:
    review_status = str(review_bundle.get("status", "needs_review"))
    summary = _as_mapping(review_bundle.get("summary"))

    indicators = {
        "review_status": review_status,
        "source_intake_status": summary.get("source_intake_status"),
        "source_intake_type": summary.get("source_intake_type"),
        "source_adapter_type": summary.get("source_adapter_type"),
        "backtest_id": summary.get("backtest_id"),
        "ready_review_item_count": _safe_int(summary.get("ready_review_item_count")),
        "needs_review_item_count": _safe_int(summary.get("needs_review_item_count")),
        "blocked_review_item_count": _safe_int(summary.get("blocked_review_item_count")),
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
        "status": _classify_health_status(review_status),
        "indicators": indicators,
        "recommendations": recommendations,
        "explicit_exclusions": list(review_bundle.get("explicit_exclusions", [])),
    }


def _build_operation_record(
    *,
    review_bundle: Mapping[str, Any],
    audit_report: Mapping[str, Any],
    health_report: Mapping[str, Any],
    event_log_path: Path | None,
) -> dict[str, Any]:
    summary = _as_mapping(review_bundle.get("summary"))
    operation_id = _build_operation_id(summary)

    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "operation_id": operation_id,
        "status": review_bundle.get("status", "needs_review"),
        "summary": {
            "source_intake_status": summary.get("source_intake_status", "needs_review"),
            "source_intake_type": summary.get("source_intake_type"),
            "source_adapter_type": summary.get("source_adapter_type"),
            "backtest_id": summary.get("backtest_id"),
            "review_status": review_bundle.get("status", "needs_review"),
            "audit_status": audit_report.get("status", "needs_review"),
            "health_status": health_report.get("status", "degraded"),
            "ready_review_item_count": _safe_int(
                summary.get("ready_review_item_count")
            ),
            "needs_review_item_count": _safe_int(
                summary.get("needs_review_item_count")
            ),
            "blocked_review_item_count": _safe_int(
                summary.get("blocked_review_item_count")
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
        "explicit_exclusions": list(review_bundle.get("explicit_exclusions", [])),
    }


def _build_event(
    *,
    review_bundle: Mapping[str, Any],
    event_type: str,
    sequence: int,
) -> dict[str, Any]:
    summary = _as_mapping(review_bundle.get("summary"))

    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "event_type": event_type,
        "sequence": sequence,
        "status": review_bundle.get("status", "needs_review"),
        "summary": {
            "source_intake_status": summary.get("source_intake_status", "needs_review"),
            "backtest_id": summary.get("backtest_id"),
            "review_status": review_bundle.get("status", "needs_review"),
            "ready_review_item_count": _safe_int(
                summary.get("ready_review_item_count")
            ),
            "needs_review_item_count": _safe_int(
                summary.get("needs_review_item_count")
            ),
            "blocked_review_item_count": _safe_int(
                summary.get("blocked_review_item_count")
            ),
            "decision_event_count": _safe_int(summary.get("decision_event_count")),
            "performance_metric_count": _safe_int(
                summary.get("performance_metric_count")
            ),
            "warning_count": _safe_int(summary.get("warning_count")),
            "blocked_reason_count": _safe_int(summary.get("blocked_reason_count")),
        },
        "explicit_exclusions": list(review_bundle.get("explicit_exclusions", [])),
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
    review_status: str,
    checks: list[Mapping[str, Any]],
) -> str:
    if any(check.get("status") == "failed" for check in checks):
        return "blocked"

    if review_status == "blocked":
        return "blocked"

    if review_status == "needs_review":
        return "needs_review"

    if any(check.get("status") == "warning" for check in checks):
        return "needs_review"

    return "ready"


def _classify_health_status(review_status: str) -> str:
    if review_status == "ready":
        return "healthy"
    if review_status == "blocked":
        return "blocked"
    return "degraded"


def _build_health_recommendations(indicators: Mapping[str, Any]) -> list[str]:
    recommendations: list[str] = []

    if _safe_int(indicators.get("ready_review_item_count")) == 0 and indicators.get(
        "review_status"
    ) == "ready":
        recommendations.append("add ready historical research review items")

    if _safe_int(indicators.get("needs_review_item_count")) > 0:
        recommendations.append("review needs-review historical research evidence items")

    if _safe_int(indicators.get("blocked_review_item_count")) > 0:
        recommendations.append("resolve blocked historical research review items")

    if _safe_int(indicators.get("decision_event_count")) == 0:
        recommendations.append("include decision evidence before evidence review")

    if _safe_int(indicators.get("performance_metric_count")) == 0:
        recommendations.append("include performance evidence before evidence review")

    if _safe_int(indicators.get("blocked_reason_count")) > 0:
        recommendations.append("resolve blocked reasons before review promotion")

    if indicators.get("review_status") == "ready":
        recommendations.append("historical research evidence review is ready")

    if not recommendations:
        recommendations.append("no health actions required")

    return sorted(set(recommendations))


def _has_required_exclusions(review_bundle: Mapping[str, Any]) -> bool:
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

    exclusions = review_bundle.get("explicit_exclusions")
    if not isinstance(exclusions, list):
        return False

    return required.issubset({str(item) for item in exclusions})


def _review_item_count_matches_summary(review_bundle: Mapping[str, Any]) -> bool:
    summary = _as_mapping(review_bundle.get("summary"))

    ready_items = _as_list(review_bundle.get("ready_review_items"))
    needs_review_items = _as_list(review_bundle.get("needs_review_items"))
    blocked_items = _as_list(review_bundle.get("blocked_review_items"))

    return (
        len(ready_items) == _safe_int(summary.get("ready_review_item_count"))
        and len(needs_review_items) == _safe_int(summary.get("needs_review_item_count"))
        and len(blocked_items) == _safe_int(summary.get("blocked_review_item_count"))
    )


def _items_have_type(items: list[Any], item_type: str) -> bool:
    return all(
        isinstance(item, Mapping) and item.get("review_item_type") == item_type
        for item in items
    )


def _items_have_key(items: list[Any], key: str) -> bool:
    return all(isinstance(item, Mapping) and bool(item.get(key)) for item in items)


def _items_have_positive_count(items: list[Any], key: str) -> bool:
    return all(
        isinstance(item, Mapping) and _safe_int(item.get(key)) > 0
        for item in items
    )


def _blocked_review_has_reason(review_bundle: Mapping[str, Any]) -> bool:
    if review_bundle.get("status") != "blocked":
        return True

    blocked_reasons = review_bundle.get("blocked_reasons")
    return isinstance(blocked_reasons, list) and len(blocked_reasons) > 0


def _build_operation_id(summary: Mapping[str, Any]) -> str:
    backtest_id = summary.get("backtest_id") or "historical_research_evidence_review"
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
