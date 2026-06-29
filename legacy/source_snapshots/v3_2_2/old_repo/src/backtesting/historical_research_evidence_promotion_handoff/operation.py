from __future__ import annotations

import json
from os import PathLike
from pathlib import Path
from typing import Any, Mapping

from src.backtesting.historical_research_evidence_promotion_handoff.builder import (
    build_historical_research_evidence_promotion_handoff,
)


OPERATION_SCHEMA_VERSION = (
    "historical_research_evidence_promotion_handoff_operation.v1"
)
EVENT_SCHEMA_VERSION = (
    "historical_research_evidence_promotion_handoff_operation_event.v1"
)
AUDIT_SCHEMA_VERSION = (
    "historical_research_evidence_promotion_handoff_audit.v1"
)
HEALTH_SCHEMA_VERSION = (
    "historical_research_evidence_promotion_handoff_health.v1"
)

OPERATION_TYPE = (
    "historical_research_evidence_promotion_handoff_operation"
)


def run_historical_research_evidence_promotion_handoff_operation(
    source: Any,
    *,
    event_log_path: str | PathLike[str] | None = None,
) -> dict[str, Any]:
    """Run a deterministic historical research evidence promotion handoff.

    This operation does not call QuantConnect, brokers, market-data services,
    order-routing systems, live-trading APIs, fill engines, slippage engines,
    or external data warehouses.
    """

    promotion_handoff = (
        build_historical_research_evidence_promotion_handoff(source)
    )

    audit_report = (
        build_historical_research_evidence_promotion_handoff_audit_report(
            promotion_handoff
        )
    )

    health_report = (
        build_historical_research_evidence_promotion_handoff_health_report(
            promotion_handoff
        )
    )

    events = [
        _build_event(
            promotion_handoff=promotion_handoff,
            event_type=(
                "historical_research_evidence_promotion_handoff_"
                "operation_started"
            ),
            sequence=1,
        ),
        _build_event(
            promotion_handoff=promotion_handoff,
            event_type=(
                "historical_research_evidence_promotion_handoff_"
                "operation_completed"
            ),
            sequence=2,
        ),
    ]

    normalized_log_path = _normalize_event_log_path(event_log_path)

    if normalized_log_path is not None:
        _write_jsonl_event_log(
            normalized_log_path,
            events,
        )

    operation_record = _build_operation_record(
        promotion_handoff=promotion_handoff,
        audit_report=audit_report,
        health_report=health_report,
        event_log_path=normalized_log_path,
    )

    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": promotion_handoff["status"],
        "operation_record": operation_record,
        "audit_report": audit_report,
        "health_report": health_report,
        "promotion_handoff": promotion_handoff,
        "events": events,
        "event_log_path": (
            str(normalized_log_path)
            if normalized_log_path
            else None
        ),
        "explicit_exclusions": list(
            promotion_handoff.get("explicit_exclusions", [])
        ),
    }


def build_historical_research_evidence_promotion_handoff_audit_report(
    promotion_handoff: Mapping[str, Any],
) -> dict[str, Any]:
    promoted_items = _as_list(
        promotion_handoff.get("promoted_items")
    )

    checks = [
        _check(
            name="promotion_handoff_schema_version_present",
            passed=bool(promotion_handoff.get("schema_version")),
            severity="blocker",
            message="promotion handoff schema version is present",
            failure_message="promotion handoff schema version is missing",
        ),
        _check(
            name="handoff_type_is_expected",
            passed=(
                promotion_handoff.get("handoff_type")
                == "historical_research_evidence_promotion_handoff"
            ),
            severity="blocker",
            message="promotion handoff type is expected",
            failure_message="unexpected promotion handoff type detected",
        ),
        _check(
            name="explicit_exclusions_present",
            passed=_has_required_exclusions(promotion_handoff),
            severity="blocker",
            message="manual-only exclusions are present",
            failure_message="one or more required exclusions are missing",
        ),
        _check(
            name="promoted_item_count_matches_summary",
            passed=_promoted_item_count_matches_summary(
                promotion_handoff
            ),
            severity="blocker",
            message="promoted item count matches summary",
            failure_message="promoted item count does not match summary",
        ),
        _check(
            name="ready_handoff_has_promoted_items",
            passed=(
                len(promoted_items) > 0
                if promotion_handoff.get("status") == "ready"
                else True
            ),
            severity="blocker",
            message="ready handoff has promoted items",
            failure_message="ready handoff is missing promoted items",
        ),
        _check(
            name="promoted_items_have_expected_type",
            passed=_items_have_expected_type(promoted_items),
            severity="blocker",
            message="promoted items have expected handoff item type",
            failure_message="one or more promoted items have unexpected type",
        ),
        _check(
            name="ready_handoff_items_are_ready",
            passed=(
                _items_have_status(promoted_items, "ready")
                if promotion_handoff.get("status") == "ready"
                else True
            ),
            severity="warning",
            message="ready handoff items are ready",
            failure_message="one or more promoted items are not ready",
        ),
        _check(
            name="ready_handoff_can_enter_downstream_research",
            passed=(
                _summary_flag(
                    promotion_handoff,
                    "can_enter_downstream_historical_research",
                )
                if promotion_handoff.get("status") == "ready"
                else True
            ),
            severity="warning",
            message="ready handoff can enter downstream research",
            failure_message=(
                "ready handoff cannot enter downstream research"
            ),
        ),
        _check(
            name="ready_handoff_has_strategy_context",
            passed=(
                _summary_positive_count(
                    promotion_handoff,
                    "strategy_count",
                )
                if promotion_handoff.get("status") == "ready"
                else True
            ),
            severity="warning",
            message="ready handoff has strategy context",
            failure_message="ready handoff is missing strategy context",
        ),
        _check(
            name="ready_handoff_has_symbol_context",
            passed=(
                _summary_positive_count(
                    promotion_handoff,
                    "symbol_count",
                )
                if promotion_handoff.get("status") == "ready"
                else True
            ),
            severity="warning",
            message="ready handoff has symbol context",
            failure_message="ready handoff is missing symbol context",
        ),
        _check(
            name="ready_handoff_has_decision_evidence",
            passed=(
                _summary_positive_count(
                    promotion_handoff,
                    "decision_event_count",
                )
                if promotion_handoff.get("status") == "ready"
                else True
            ),
            severity="warning",
            message="ready handoff has decision evidence",
            failure_message="ready handoff is missing decision evidence",
        ),
        _check(
            name="ready_handoff_has_performance_evidence",
            passed=(
                _summary_positive_count(
                    promotion_handoff,
                    "performance_metric_count",
                )
                if promotion_handoff.get("status") == "ready"
                else True
            ),
            severity="warning",
            message="ready handoff has performance evidence",
            failure_message="ready handoff is missing performance evidence",
        ),
        _check(
            name="blocked_handoff_has_reason",
            passed=_blocked_handoff_has_reason(promotion_handoff),
            severity="warning",
            message="blocked handoff reason handling is valid",
            failure_message="blocked handoff is missing blocked reasons",
        ),
    ]

    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_audit_status(
            handoff_status=str(
                promotion_handoff.get("status", "needs_review")
            ),
            checks=checks,
        ),
        "summary": _summarize_checks(checks),
        "handoff_counts": {
            "promoted_items": len(promoted_items),
            "strategies": len(
                _as_list(promotion_handoff.get("strategy_ids"))
            ),
            "symbols": len(
                _as_list(promotion_handoff.get("symbols"))
            ),
            "backtests": len(
                _as_list(promotion_handoff.get("backtest_ids"))
            ),
            "evidence": len(
                _as_list(promotion_handoff.get("evidence_ids"))
            ),
        },
        "checks": checks,
        "explicit_exclusions": list(
            promotion_handoff.get("explicit_exclusions", [])
        ),
    }


def build_historical_research_evidence_promotion_handoff_health_report(
    promotion_handoff: Mapping[str, Any],
) -> dict[str, Any]:
    handoff_status = str(
        promotion_handoff.get("status", "needs_review")
    )
    summary = _as_mapping(promotion_handoff.get("summary"))

    indicators = {
        "handoff_status": handoff_status,
        "source_gate_status": summary.get("source_gate_status"),
        "backtest_id": summary.get("backtest_id"),
        "promoted_item_count": _safe_int(
            summary.get("promoted_item_count")
        ),
        "source_promotable_evidence_count": _safe_int(
            summary.get("source_promotable_evidence_count")
        ),
        "source_needs_review_evidence_count": _safe_int(
            summary.get("source_needs_review_evidence_count")
        ),
        "source_blocked_evidence_count": _safe_int(
            summary.get("source_blocked_evidence_count")
        ),
        "strategy_count": _safe_int(
            summary.get("strategy_count")
        ),
        "symbol_count": _safe_int(
            summary.get("symbol_count")
        ),
        "backtest_count": _safe_int(
            summary.get("backtest_count")
        ),
        "evidence_count": _safe_int(
            summary.get("evidence_count")
        ),
        "decision_event_count": _safe_int(
            summary.get("decision_event_count")
        ),
        "performance_metric_count": _safe_int(
            summary.get("performance_metric_count")
        ),
        "warning_count": _safe_int(
            summary.get("warning_count")
        ),
        "blocked_reason_count": _safe_int(
            summary.get("blocked_reason_count")
        ),
        "can_enter_downstream_historical_research": bool(
            summary.get(
                "can_enter_downstream_historical_research"
            )
        ),
    }

    return {
        "schema_version": HEALTH_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_health_status(handoff_status),
        "indicators": indicators,
        "recommendations": _build_health_recommendations(
            indicators
        ),
        "explicit_exclusions": list(
            promotion_handoff.get("explicit_exclusions", [])
        ),
    }


def _build_operation_record(
    *,
    promotion_handoff: Mapping[str, Any],
    audit_report: Mapping[str, Any],
    health_report: Mapping[str, Any],
    event_log_path: Path | None,
) -> dict[str, Any]:
    summary = _as_mapping(promotion_handoff.get("summary"))

    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "operation_id": _build_operation_id(summary),
        "status": promotion_handoff.get("status", "needs_review"),
        "summary": {
            "handoff_status": promotion_handoff.get(
                "status",
                "needs_review",
            ),
            "audit_status": audit_report.get(
                "status",
                "needs_review",
            ),
            "health_status": health_report.get(
                "status",
                "degraded",
            ),
            "source_gate_status": summary.get("source_gate_status"),
            "backtest_id": summary.get("backtest_id"),
            "promoted_item_count": _safe_int(
                summary.get("promoted_item_count")
            ),
            "source_promotable_evidence_count": _safe_int(
                summary.get("source_promotable_evidence_count")
            ),
            "source_needs_review_evidence_count": _safe_int(
                summary.get("source_needs_review_evidence_count")
            ),
            "source_blocked_evidence_count": _safe_int(
                summary.get("source_blocked_evidence_count")
            ),
            "strategy_count": _safe_int(
                summary.get("strategy_count")
            ),
            "symbol_count": _safe_int(
                summary.get("symbol_count")
            ),
            "backtest_count": _safe_int(
                summary.get("backtest_count")
            ),
            "evidence_count": _safe_int(
                summary.get("evidence_count")
            ),
            "decision_event_count": _safe_int(
                summary.get("decision_event_count")
            ),
            "performance_metric_count": _safe_int(
                summary.get("performance_metric_count")
            ),
            "warning_count": _safe_int(
                summary.get("warning_count")
            ),
            "blocked_reason_count": _safe_int(
                summary.get("blocked_reason_count")
            ),
            "can_enter_downstream_historical_research": bool(
                summary.get(
                    "can_enter_downstream_historical_research"
                )
            ),
        },
        "event_log_path": (
            str(event_log_path)
            if event_log_path
            else None
        ),
        "explicit_exclusions": list(
            promotion_handoff.get("explicit_exclusions", [])
        ),
    }


def _build_event(
    *,
    promotion_handoff: Mapping[str, Any],
    event_type: str,
    sequence: int,
) -> dict[str, Any]:
    summary = _as_mapping(promotion_handoff.get("summary"))

    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "event_type": event_type,
        "sequence": sequence,
        "status": promotion_handoff.get("status", "needs_review"),
        "summary": {
            "handoff_status": promotion_handoff.get(
                "status",
                "needs_review",
            ),
            "source_gate_status": summary.get("source_gate_status"),
            "backtest_id": summary.get("backtest_id"),
            "promoted_item_count": _safe_int(
                summary.get("promoted_item_count")
            ),
            "strategy_count": _safe_int(
                summary.get("strategy_count")
            ),
            "symbol_count": _safe_int(
                summary.get("symbol_count")
            ),
            "decision_event_count": _safe_int(
                summary.get("decision_event_count")
            ),
            "performance_metric_count": _safe_int(
                summary.get("performance_metric_count")
            ),
            "warning_count": _safe_int(
                summary.get("warning_count")
            ),
            "blocked_reason_count": _safe_int(
                summary.get("blocked_reason_count")
            ),
            "can_enter_downstream_historical_research": bool(
                summary.get(
                    "can_enter_downstream_historical_research"
                )
            ),
        },
        "explicit_exclusions": list(
            promotion_handoff.get("explicit_exclusions", [])
        ),
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


def _normalize_event_log_path(
    path: str | PathLike[str] | None,
) -> Path | None:
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
        "status": (
            "failed"
            if severity == "blocker"
            else "warning"
        ),
        "severity": severity,
        "message": failure_message,
    }


def _summarize_checks(
    checks: list[Mapping[str, Any]],
) -> dict[str, int]:
    return {
        "passed_count": sum(
            1
            for check in checks
            if check.get("status") == "passed"
        ),
        "warning_count": sum(
            1
            for check in checks
            if check.get("status") == "warning"
        ),
        "failed_count": sum(
            1
            for check in checks
            if check.get("status") == "failed"
        ),
        "check_count": len(checks),
    }


def _classify_audit_status(
    *,
    handoff_status: str,
    checks: list[Mapping[str, Any]],
) -> str:
    if any(
        check.get("status") == "failed"
        for check in checks
    ):
        return "blocked"

    if handoff_status == "blocked":
        return "blocked"

    if handoff_status == "needs_review":
        return "needs_review"

    if any(
        check.get("status") == "warning"
        for check in checks
    ):
        return "needs_review"

    return "ready"


def _classify_health_status(handoff_status: str) -> str:
    if handoff_status == "ready":
        return "healthy"

    if handoff_status == "blocked":
        return "blocked"

    return "degraded"


def _build_health_recommendations(
    indicators: Mapping[str, Any],
) -> list[str]:
    recommendations: list[str] = []

    if _safe_int(indicators.get("promoted_item_count")) == 0:
        recommendations.append(
            "add promoted evidence before downstream research"
        )

    if (
        _safe_int(
            indicators.get("source_needs_review_evidence_count")
        )
        > 0
    ):
        recommendations.append(
            "review source needs-review promotion evidence"
        )

    if (
        _safe_int(
            indicators.get("source_blocked_evidence_count")
        )
        > 0
    ):
        recommendations.append(
            "resolve source blocked promotion evidence"
        )

    if _safe_int(indicators.get("strategy_count")) == 0:
        recommendations.append(
            "add strategy context before downstream research"
        )

    if _safe_int(indicators.get("symbol_count")) == 0:
        recommendations.append(
            "add symbol context before downstream research"
        )

    if _safe_int(indicators.get("decision_event_count")) == 0:
        recommendations.append(
            "add decision evidence before downstream research"
        )

    if _safe_int(indicators.get("performance_metric_count")) == 0:
        recommendations.append(
            "add performance evidence before downstream research"
        )

    if _safe_int(indicators.get("blocked_reason_count")) > 0:
        recommendations.append(
            "resolve blocked reasons before downstream research"
        )

    if (
        indicators.get("handoff_status") == "ready"
        and indicators.get(
            "can_enter_downstream_historical_research"
        )
    ):
        recommendations.append(
            "historical research evidence promotion handoff is ready"
        )

    if not recommendations:
        recommendations.append("no health actions required")

    return sorted(set(recommendations))


def _has_required_exclusions(
    promotion_handoff: Mapping[str, Any],
) -> bool:
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

    exclusions = promotion_handoff.get("explicit_exclusions")

    if not isinstance(exclusions, list):
        return False

    return required.issubset(
        {str(item) for item in exclusions}
    )


def _promoted_item_count_matches_summary(
    promotion_handoff: Mapping[str, Any],
) -> bool:
    summary = _as_mapping(promotion_handoff.get("summary"))
    promoted_items = _as_list(
        promotion_handoff.get("promoted_items")
    )

    return len(promoted_items) == _safe_int(
        summary.get("promoted_item_count")
    )


def _items_have_expected_type(items: list[Any]) -> bool:
    return all(
        isinstance(item, Mapping)
        and item.get("handoff_item_type")
        == "historical_research_evidence_promotion_handoff_item"
        for item in items
    )


def _items_have_status(
    items: list[Any],
    status: str,
) -> bool:
    return all(
        isinstance(item, Mapping)
        and item.get("status") == status
        for item in items
    )


def _summary_flag(
    promotion_handoff: Mapping[str, Any],
    key: str,
) -> bool:
    summary = _as_mapping(promotion_handoff.get("summary"))

    return bool(summary.get(key))


def _summary_positive_count(
    promotion_handoff: Mapping[str, Any],
    key: str,
) -> bool:
    summary = _as_mapping(promotion_handoff.get("summary"))

    return _safe_int(summary.get(key)) > 0


def _blocked_handoff_has_reason(
    promotion_handoff: Mapping[str, Any],
) -> bool:
    if promotion_handoff.get("status") != "blocked":
        return True

    blocked_reasons = promotion_handoff.get("blocked_reasons")

    return (
        isinstance(blocked_reasons, list)
        and len(blocked_reasons) > 0
    )


def _build_operation_id(summary: Mapping[str, Any]) -> str:
    backtest_id = (
        summary.get("backtest_id")
        or "historical_research_evidence_promotion_handoff"
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
