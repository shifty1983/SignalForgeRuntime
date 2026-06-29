from __future__ import annotations

import json
from os import PathLike
from pathlib import Path
from typing import Any, Mapping

from src.backtesting.historical_research_downstream_intake.builder import (
    build_historical_research_downstream_intake,
)


OPERATION_SCHEMA_VERSION = "historical_research_downstream_intake_operation.v1"
EVENT_SCHEMA_VERSION = "historical_research_downstream_intake_operation_event.v1"
AUDIT_SCHEMA_VERSION = "historical_research_downstream_intake_audit.v1"
HEALTH_SCHEMA_VERSION = "historical_research_downstream_intake_health.v1"

OPERATION_TYPE = "historical_research_downstream_intake_operation"


def run_historical_research_downstream_intake_operation(
    source: Any,
    *,
    event_log_path: str | PathLike[str] | None = None,
) -> dict[str, Any]:
    """Run deterministic historical research downstream intake.

    This operation does not call QuantConnect, brokers, market-data services,
    order-routing systems, live-trading APIs, fill engines, slippage engines,
    or external data warehouses.
    """

    downstream_intake = build_historical_research_downstream_intake(source)

    audit_report = build_historical_research_downstream_intake_audit_report(
        downstream_intake
    )
    health_report = build_historical_research_downstream_intake_health_report(
        downstream_intake
    )

    events = [
        _build_event(
            downstream_intake=downstream_intake,
            event_type="historical_research_downstream_intake_operation_started",
            sequence=1,
        ),
        _build_event(
            downstream_intake=downstream_intake,
            event_type="historical_research_downstream_intake_operation_completed",
            sequence=2,
        ),
    ]

    normalized_log_path = _normalize_event_log_path(event_log_path)

    if normalized_log_path is not None:
        _write_jsonl_event_log(normalized_log_path, events)

    operation_record = _build_operation_record(
        downstream_intake=downstream_intake,
        audit_report=audit_report,
        health_report=health_report,
        event_log_path=normalized_log_path,
    )

    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": downstream_intake["status"],
        "operation_record": operation_record,
        "audit_report": audit_report,
        "health_report": health_report,
        "downstream_intake": downstream_intake,
        "events": events,
        "event_log_path": str(normalized_log_path) if normalized_log_path else None,
        "explicit_exclusions": list(downstream_intake.get("explicit_exclusions", [])),
    }


def build_historical_research_downstream_intake_audit_report(
    downstream_intake: Mapping[str, Any],
) -> dict[str, Any]:
    intake_items = _as_list(downstream_intake.get("intake_items"))

    checks = [
        _check(
            name="downstream_intake_schema_version_present",
            passed=bool(downstream_intake.get("schema_version")),
            severity="blocker",
            message="downstream intake schema version is present",
            failure_message="downstream intake schema version is missing",
        ),
        _check(
            name="intake_type_is_expected",
            passed=(
                downstream_intake.get("intake_type")
                == "historical_research_downstream_intake"
            ),
            severity="blocker",
            message="downstream intake type is expected",
            failure_message="unexpected downstream intake type detected",
        ),
        _check(
            name="explicit_exclusions_present",
            passed=_has_required_exclusions(downstream_intake),
            severity="blocker",
            message="manual-only exclusions are present",
            failure_message="one or more required exclusions are missing",
        ),
        _check(
            name="intake_item_count_matches_summary",
            passed=_intake_item_count_matches_summary(downstream_intake),
            severity="blocker",
            message="intake item count matches summary",
            failure_message="intake item count does not match summary",
        ),
        _check(
            name="ready_intake_has_items",
            passed=(
                len(intake_items) > 0
                if downstream_intake.get("status") == "ready"
                else True
            ),
            severity="blocker",
            message="ready downstream intake has items",
            failure_message="ready downstream intake is missing items",
        ),
        _check(
            name="intake_items_have_expected_type",
            passed=_items_have_expected_type(intake_items),
            severity="blocker",
            message="intake items have expected item type",
            failure_message="one or more intake items have unexpected type",
        ),
        _check(
            name="ready_intake_items_are_ready",
            passed=(
                _items_have_status(intake_items, "ready")
                if downstream_intake.get("status") == "ready"
                else True
            ),
            severity="warning",
            message="ready intake items are ready",
            failure_message="one or more intake items are not ready",
        ),
        _check(
            name="ready_intake_can_enter_expected_value_research",
            passed=(
                _summary_flag(
                    downstream_intake,
                    "can_enter_expected_value_research",
                )
                if downstream_intake.get("status") == "ready"
                else True
            ),
            severity="warning",
            message="ready intake can enter expected-value research",
            failure_message="ready intake cannot enter expected-value research",
        ),
        _check(
            name="ready_intake_can_enter_strategy_selection",
            passed=(
                _summary_flag(
                    downstream_intake,
                    "can_enter_strategy_selection",
                )
                if downstream_intake.get("status") == "ready"
                else True
            ),
            severity="warning",
            message="ready intake can enter strategy selection",
            failure_message="ready intake cannot enter strategy selection",
        ),
        _check(
            name="ready_intake_has_strategy_context",
            passed=(
                _summary_positive_count(downstream_intake, "strategy_count")
                if downstream_intake.get("status") == "ready"
                else True
            ),
            severity="warning",
            message="ready intake has strategy context",
            failure_message="ready intake is missing strategy context",
        ),
        _check(
            name="ready_intake_has_symbol_context",
            passed=(
                _summary_positive_count(downstream_intake, "symbol_count")
                if downstream_intake.get("status") == "ready"
                else True
            ),
            severity="warning",
            message="ready intake has symbol context",
            failure_message="ready intake is missing symbol context",
        ),
        _check(
            name="ready_intake_has_decision_evidence",
            passed=(
                _summary_positive_count(
                    downstream_intake,
                    "decision_event_count",
                )
                if downstream_intake.get("status") == "ready"
                else True
            ),
            severity="warning",
            message="ready intake has decision evidence",
            failure_message="ready intake is missing decision evidence",
        ),
        _check(
            name="ready_intake_has_performance_evidence",
            passed=(
                _summary_positive_count(
                    downstream_intake,
                    "performance_metric_count",
                )
                if downstream_intake.get("status") == "ready"
                else True
            ),
            severity="warning",
            message="ready intake has performance evidence",
            failure_message="ready intake is missing performance evidence",
        ),
        _check(
            name="blocked_intake_has_reason",
            passed=_blocked_intake_has_reason(downstream_intake),
            severity="warning",
            message="blocked downstream intake reason handling is valid",
            failure_message="blocked downstream intake is missing blocked reasons",
        ),
    ]

    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_audit_status(
            intake_status=str(downstream_intake.get("status", "needs_review")),
            checks=checks,
        ),
        "summary": _summarize_checks(checks),
        "intake_counts": {
            "items": len(intake_items),
            "strategies": len(_as_list(downstream_intake.get("strategy_ids"))),
            "symbols": len(_as_list(downstream_intake.get("symbols"))),
            "backtests": len(_as_list(downstream_intake.get("backtest_ids"))),
            "evidence": len(_as_list(downstream_intake.get("evidence_ids"))),
        },
        "checks": checks,
        "explicit_exclusions": list(downstream_intake.get("explicit_exclusions", [])),
    }


def build_historical_research_downstream_intake_health_report(
    downstream_intake: Mapping[str, Any],
) -> dict[str, Any]:
    intake_status = str(downstream_intake.get("status", "needs_review"))
    summary = _as_mapping(downstream_intake.get("summary"))

    indicators = {
        "intake_status": intake_status,
        "source_handoff_status": summary.get("source_handoff_status"),
        "backtest_id": summary.get("backtest_id"),
        "intake_item_count": _safe_int(summary.get("intake_item_count")),
        "source_promoted_item_count": _safe_int(
            summary.get("source_promoted_item_count")
        ),
        "strategy_count": _safe_int(summary.get("strategy_count")),
        "symbol_count": _safe_int(summary.get("symbol_count")),
        "backtest_count": _safe_int(summary.get("backtest_count")),
        "evidence_count": _safe_int(summary.get("evidence_count")),
        "decision_event_count": _safe_int(summary.get("decision_event_count")),
        "performance_metric_count": _safe_int(
            summary.get("performance_metric_count")
        ),
        "ready_intake_item_count": _safe_int(
            summary.get("ready_intake_item_count")
        ),
        "needs_review_intake_item_count": _safe_int(
            summary.get("needs_review_intake_item_count")
        ),
        "blocked_intake_item_count": _safe_int(
            summary.get("blocked_intake_item_count")
        ),
        "warning_count": _safe_int(summary.get("warning_count")),
        "blocked_reason_count": _safe_int(summary.get("blocked_reason_count")),
        "can_enter_expected_value_research": bool(
            summary.get("can_enter_expected_value_research")
        ),
        "can_enter_strategy_selection": bool(
            summary.get("can_enter_strategy_selection")
        ),
    }

    return {
        "schema_version": HEALTH_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_health_status(intake_status),
        "indicators": indicators,
        "recommendations": _build_health_recommendations(indicators),
        "explicit_exclusions": list(downstream_intake.get("explicit_exclusions", [])),
    }


def _build_operation_record(
    *,
    downstream_intake: Mapping[str, Any],
    audit_report: Mapping[str, Any],
    health_report: Mapping[str, Any],
    event_log_path: Path | None,
) -> dict[str, Any]:
    summary = _as_mapping(downstream_intake.get("summary"))

    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "operation_id": _build_operation_id(summary),
        "status": downstream_intake.get("status", "needs_review"),
        "summary": {
            "intake_status": downstream_intake.get("status", "needs_review"),
            "audit_status": audit_report.get("status", "needs_review"),
            "health_status": health_report.get("status", "degraded"),
            "source_handoff_status": summary.get("source_handoff_status"),
            "backtest_id": summary.get("backtest_id"),
            "intake_item_count": _safe_int(summary.get("intake_item_count")),
            "source_promoted_item_count": _safe_int(
                summary.get("source_promoted_item_count")
            ),
            "strategy_count": _safe_int(summary.get("strategy_count")),
            "symbol_count": _safe_int(summary.get("symbol_count")),
            "backtest_count": _safe_int(summary.get("backtest_count")),
            "evidence_count": _safe_int(summary.get("evidence_count")),
            "decision_event_count": _safe_int(summary.get("decision_event_count")),
            "performance_metric_count": _safe_int(
                summary.get("performance_metric_count")
            ),
            "ready_intake_item_count": _safe_int(
                summary.get("ready_intake_item_count")
            ),
            "needs_review_intake_item_count": _safe_int(
                summary.get("needs_review_intake_item_count")
            ),
            "blocked_intake_item_count": _safe_int(
                summary.get("blocked_intake_item_count")
            ),
            "warning_count": _safe_int(summary.get("warning_count")),
            "blocked_reason_count": _safe_int(summary.get("blocked_reason_count")),
            "can_enter_expected_value_research": bool(
                summary.get("can_enter_expected_value_research")
            ),
            "can_enter_strategy_selection": bool(
                summary.get("can_enter_strategy_selection")
            ),
        },
        "event_log_path": str(event_log_path) if event_log_path else None,
        "explicit_exclusions": list(downstream_intake.get("explicit_exclusions", [])),
    }


def _build_event(
    *,
    downstream_intake: Mapping[str, Any],
    event_type: str,
    sequence: int,
) -> dict[str, Any]:
    summary = _as_mapping(downstream_intake.get("summary"))

    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "event_type": event_type,
        "sequence": sequence,
        "status": downstream_intake.get("status", "needs_review"),
        "summary": {
            "intake_status": downstream_intake.get("status", "needs_review"),
            "source_handoff_status": summary.get("source_handoff_status"),
            "backtest_id": summary.get("backtest_id"),
            "intake_item_count": _safe_int(summary.get("intake_item_count")),
            "strategy_count": _safe_int(summary.get("strategy_count")),
            "symbol_count": _safe_int(summary.get("symbol_count")),
            "decision_event_count": _safe_int(summary.get("decision_event_count")),
            "performance_metric_count": _safe_int(
                summary.get("performance_metric_count")
            ),
            "warning_count": _safe_int(summary.get("warning_count")),
            "blocked_reason_count": _safe_int(summary.get("blocked_reason_count")),
            "can_enter_expected_value_research": bool(
                summary.get("can_enter_expected_value_research")
            ),
            "can_enter_strategy_selection": bool(
                summary.get("can_enter_strategy_selection")
            ),
        },
        "explicit_exclusions": list(downstream_intake.get("explicit_exclusions", [])),
    }


def _write_jsonl_event_log(
    path: Path,
    events: list[Mapping[str, Any]],
) -> None:
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

    return {
        "name": name,
        "status": "failed" if severity == "blocker" else "warning",
        "severity": severity,
        "message": failure_message,
    }


def _summarize_checks(checks: list[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "passed_count": sum(
            1 for check in checks if check.get("status") == "passed"
        ),
        "warning_count": sum(
            1 for check in checks if check.get("status") == "warning"
        ),
        "failed_count": sum(
            1 for check in checks if check.get("status") == "failed"
        ),
        "check_count": len(checks),
    }


def _classify_audit_status(
    *,
    intake_status: str,
    checks: list[Mapping[str, Any]],
) -> str:
    if any(check.get("status") == "failed" for check in checks):
        return "blocked"

    if intake_status == "blocked":
        return "blocked"

    if intake_status == "needs_review":
        return "needs_review"

    if any(check.get("status") == "warning" for check in checks):
        return "needs_review"

    return "ready"


def _classify_health_status(intake_status: str) -> str:
    if intake_status == "ready":
        return "healthy"

    if intake_status == "blocked":
        return "blocked"

    return "degraded"


def _build_health_recommendations(
    indicators: Mapping[str, Any],
) -> list[str]:
    recommendations: list[str] = []

    if _safe_int(indicators.get("intake_item_count")) == 0:
        recommendations.append(
            "add downstream intake items before expected-value research"
        )

    if _safe_int(indicators.get("needs_review_intake_item_count")) > 0:
        recommendations.append(
            "review needs-review downstream intake items"
        )

    if _safe_int(indicators.get("blocked_intake_item_count")) > 0:
        recommendations.append(
            "resolve blocked downstream intake items"
        )

    if _safe_int(indicators.get("strategy_count")) == 0:
        recommendations.append(
            "add strategy context before expected-value research"
        )

    if _safe_int(indicators.get("symbol_count")) == 0:
        recommendations.append(
            "add symbol context before expected-value research"
        )

    if _safe_int(indicators.get("decision_event_count")) == 0:
        recommendations.append(
            "add decision evidence before expected-value research"
        )

    if _safe_int(indicators.get("performance_metric_count")) == 0:
        recommendations.append(
            "add performance evidence before expected-value research"
        )

    if _safe_int(indicators.get("blocked_reason_count")) > 0:
        recommendations.append(
            "resolve blocked reasons before expected-value research"
        )

    if (
        indicators.get("intake_status") == "ready"
        and indicators.get("can_enter_expected_value_research")
        and indicators.get("can_enter_strategy_selection")
    ):
        recommendations.append(
            "historical research downstream intake is ready"
        )

    if not recommendations:
        recommendations.append("no health actions required")

    return sorted(set(recommendations))


def _has_required_exclusions(downstream_intake: Mapping[str, Any]) -> bool:
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

    exclusions = downstream_intake.get("explicit_exclusions")

    if not isinstance(exclusions, list):
        return False

    return required.issubset({str(item) for item in exclusions})


def _intake_item_count_matches_summary(
    downstream_intake: Mapping[str, Any],
) -> bool:
    summary = _as_mapping(downstream_intake.get("summary"))
    intake_items = _as_list(downstream_intake.get("intake_items"))

    return len(intake_items) == _safe_int(summary.get("intake_item_count"))


def _items_have_expected_type(items: list[Any]) -> bool:
    return all(
        isinstance(item, Mapping)
        and item.get("intake_item_type")
        == "historical_research_downstream_intake_item"
        for item in items
    )


def _items_have_status(items: list[Any], status: str) -> bool:
    return all(
        isinstance(item, Mapping) and item.get("status") == status
        for item in items
    )


def _summary_flag(downstream_intake: Mapping[str, Any], key: str) -> bool:
    summary = _as_mapping(downstream_intake.get("summary"))

    return bool(summary.get(key))


def _summary_positive_count(
    downstream_intake: Mapping[str, Any],
    key: str,
) -> bool:
    summary = _as_mapping(downstream_intake.get("summary"))

    return _safe_int(summary.get(key)) > 0


def _blocked_intake_has_reason(downstream_intake: Mapping[str, Any]) -> bool:
    if downstream_intake.get("status") != "blocked":
        return True

    blocked_reasons = downstream_intake.get("blocked_reasons")

    return isinstance(blocked_reasons, list) and len(blocked_reasons) > 0


def _build_operation_id(summary: Mapping[str, Any]) -> str:
    backtest_id = summary.get("backtest_id") or "historical_research_downstream_intake"

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
