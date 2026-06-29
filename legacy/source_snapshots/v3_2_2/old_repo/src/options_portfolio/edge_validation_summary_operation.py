from __future__ import annotations

import json
from os import PathLike
from pathlib import Path
from collections.abc import Mapping, Sequence
from typing import Any

from src.options_portfolio.edge_validation_summary import (
    EXPLICIT_EXCLUSIONS,
    build_options_edge_validation_summary,
)


OPERATION_SCHEMA_VERSION = "options_edge_validation_summary_operation.v1"
EVENT_SCHEMA_VERSION = "options_edge_validation_summary_operation_event.v1"
AUDIT_SCHEMA_VERSION = "options_edge_validation_summary_audit.v1"
HEALTH_SCHEMA_VERSION = "options_edge_validation_summary_health.v1"

OPERATION_TYPE = "options_edge_validation_summary_operation"
VALID_SUMMARY_STATUSES = {"ready", "needs_review", "blocked"}
REQUIRED_EXCLUSIONS = tuple(EXPLICIT_EXCLUSIONS)


def run_options_edge_validation_summary_operation(
    source: Mapping[str, Any] | None,
    *,
    metadata: Mapping[str, Any] | None = None,
    event_log_path: str | PathLike[str] | None = None,
) -> dict[str, Any]:
    """Run options edge validation summary as an auditable operation.

    This operation summarizes manual options outcome records only. It never calls
    broker APIs, routes orders, submits orders, models fills, performs live execution,
    models slippage, or creates automatic close/roll/defense orders.
    """

    edge_summary = build_options_edge_validation_summary(source or {})
    audit_report = build_options_edge_validation_summary_audit_report(edge_summary)
    health_report = build_options_edge_validation_summary_health_report(edge_summary)
    operation_status = _classify_operation_status(
        summary_status=str(edge_summary.get("status", "needs_review")),
        audit_status=str(audit_report.get("status", "needs_review")),
        health_status=str(health_report.get("status", "needs_review")),
    )

    events = [
        _build_event(
            edge_summary=edge_summary,
            event_type="options_edge_validation_summary_operation_started",
            sequence=1,
            status=operation_status,
        ),
        _build_event(
            edge_summary=edge_summary,
            event_type="options_edge_validation_summary_operation_completed",
            sequence=2,
            status=operation_status,
        ),
    ]

    normalized_log_path = _normalize_event_log_path(event_log_path)
    if normalized_log_path is not None:
        _write_jsonl_event_log(normalized_log_path, events)

    operation_record = _build_operation_record(
        edge_summary=edge_summary,
        audit_report=audit_report,
        health_report=health_report,
        operation_status=operation_status,
        event_log_path=normalized_log_path,
        metadata=metadata,
    )

    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": operation_status,
        "operation_record": operation_record,
        "audit_report": audit_report,
        "health_report": health_report,
        "options_edge_validation_summary": edge_summary,
        "events": events,
        "event_log_path": str(normalized_log_path) if normalized_log_path else None,
        "explicit_exclusions": list(edge_summary.get("explicit_exclusions", [])),
    }


def build_options_edge_validation_summary_audit_report(
    edge_summary: Mapping[str, Any]
) -> dict[str, Any]:
    checks = [
        _check(
            name="edge_summary_artifact_type_valid",
            passed=edge_summary.get("artifact_type") == "options_edge_validation_summary",
            severity="blocker",
            message="options edge validation summary artifact type is valid",
            failure_message="options edge validation summary artifact type is invalid",
        ),
        _check(
            name="edge_summary_status_valid",
            passed=edge_summary.get("status") in VALID_SUMMARY_STATUSES,
            severity="blocker",
            message="options edge validation summary status is valid",
            failure_message="options edge validation summary status is invalid",
        ),
        _check(
            name="explicit_exclusions_present",
            passed=_has_required_exclusions(edge_summary),
            severity="blocker",
            message="options edge validation summary exclusions are present",
            failure_message="one or more required exclusions are missing",
        ),
        _check(
            name="no_order_intents_created",
            passed=not _contains_non_null_key(edge_summary, "order_intent"),
            severity="blocker",
            message="options edge validation summary did not create order intents",
            failure_message="options edge validation summary created one or more order intents",
        ),
        _check(
            name="no_broker_order_ids_created",
            passed=not _contains_non_null_key(edge_summary, "broker_order_id"),
            severity="blocker",
            message="options edge validation summary did not create broker order ids",
            failure_message="options edge validation summary created one or more broker order ids",
        ),
        _check(
            name="no_automatic_actions_created",
            passed=not _contains_non_null_key(
                edge_summary,
                "automatic_action",
                "maintenance_action",
                "defense_action",
            ),
            severity="blocker",
            message="options edge validation summary did not create automatic actions",
            failure_message="options edge validation summary created one or more automatic actions",
        ),
        _check(
            name="count_fields_match_summary_lists",
            passed=_count_fields_match_summary_lists(edge_summary),
            severity="blocker",
            message="options edge validation summary counts match outcome lists",
            failure_message="options edge validation summary counts do not match outcome lists",
        ),
        _check(
            name="blocked_items_have_reasons",
            passed=_blocked_items_have_reasons(edge_summary),
            severity="warning",
            message="blocked edge validation items include reasons",
            failure_message="one or more blocked edge validation items are missing reasons",
        ),
    ]

    audit_summary = _summarize_checks(checks)

    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_audit_status(
            summary_status=str(edge_summary.get("status", "needs_review")),
            checks=checks,
        ),
        "summary": audit_summary,
        "checks": checks,
        "explicit_exclusions": list(edge_summary.get("explicit_exclusions", [])),
    }


def build_options_edge_validation_summary_health_report(
    edge_summary: Mapping[str, Any]
) -> dict[str, Any]:
    summary_status = str(edge_summary.get("status", "needs_review"))
    outcome_summary = _as_mapping(edge_summary.get("outcome_summary"))
    open_outcomes = _as_list(edge_summary.get("open_outcomes"))
    pending_outcomes = _as_list(edge_summary.get("pending_outcomes"))
    needs_review_outcomes = _as_list(edge_summary.get("needs_review_outcomes"))
    blocked_items = _as_list(edge_summary.get("blocked_items"))

    indicators = {
        "summary_status": summary_status,
        "summary_date": _string_or_none(edge_summary.get("summary_date")),
        "source_record_count": _safe_int(edge_summary.get("source_record_count")),
        "closed_outcome_count": _safe_int(outcome_summary.get("closed_outcome_count")),
        "open_outcome_count": _safe_int(outcome_summary.get("open_outcome_count")),
        "pending_outcome_count": _safe_int(outcome_summary.get("pending_outcome_count")),
        "needs_review_outcome_count": _safe_int(
            outcome_summary.get("needs_review_outcome_count")
        ),
        "blocked_item_count": _safe_int(outcome_summary.get("blocked_item_count")),
        "win_count": _safe_int(outcome_summary.get("win_count")),
        "loss_count": _safe_int(outcome_summary.get("loss_count")),
        "flat_count": _safe_int(outcome_summary.get("flat_count")),
        "total_realized_pnl": _safe_float(outcome_summary.get("total_realized_pnl")),
        "average_return_pct": _safe_float_or_none(outcome_summary.get("average_return_pct")),
        "average_days_held": _safe_float_or_none(outcome_summary.get("average_days_held")),
        "strategy_performance_count": len(_as_list(edge_summary.get("strategy_performance"))),
        "symbol_performance_count": len(_as_list(edge_summary.get("symbol_performance"))),
        "setup_family_performance_count": len(
            _as_list(edge_summary.get("setup_family_performance"))
        ),
        "has_open_outcomes": bool(open_outcomes),
        "has_pending_outcomes": bool(pending_outcomes),
        "has_needs_review_outcomes": bool(needs_review_outcomes),
        "has_blocked_items": bool(blocked_items),
        "has_order_intent": _contains_non_null_key(edge_summary, "order_intent"),
        "has_broker_order_id": _contains_non_null_key(edge_summary, "broker_order_id"),
        "has_automatic_action": _contains_non_null_key(edge_summary, "automatic_action"),
    }

    return {
        "schema_version": HEALTH_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_health_status(
            summary_status=summary_status,
            indicators=indicators,
        ),
        "indicators": indicators,
        "explicit_exclusions": list(edge_summary.get("explicit_exclusions", [])),
    }


def _build_operation_record(
    *,
    edge_summary: Mapping[str, Any],
    audit_report: Mapping[str, Any],
    health_report: Mapping[str, Any],
    operation_status: str,
    event_log_path: Path | None,
    metadata: Mapping[str, Any] | None,
) -> dict[str, Any]:
    outcome_summary = _as_mapping(edge_summary.get("outcome_summary"))
    return {
        "operation_type": OPERATION_TYPE,
        "schema_version": OPERATION_SCHEMA_VERSION,
        "status": operation_status,
        "summary_date": _string_or_none(edge_summary.get("summary_date")),
        "source_record_count": _safe_int(edge_summary.get("source_record_count")),
        "operation_summary": {
            "source_record_count": _safe_int(edge_summary.get("source_record_count")),
            "closed_outcome_count": _safe_int(outcome_summary.get("closed_outcome_count")),
            "open_outcome_count": _safe_int(outcome_summary.get("open_outcome_count")),
            "pending_outcome_count": _safe_int(outcome_summary.get("pending_outcome_count")),
            "needs_review_outcome_count": _safe_int(
                outcome_summary.get("needs_review_outcome_count")
            ),
            "blocked_item_count": _safe_int(outcome_summary.get("blocked_item_count")),
            "win_count": _safe_int(outcome_summary.get("win_count")),
            "loss_count": _safe_int(outcome_summary.get("loss_count")),
            "flat_count": _safe_int(outcome_summary.get("flat_count")),
            "total_realized_pnl": _safe_float(outcome_summary.get("total_realized_pnl")),
            "average_return_pct": _safe_float_or_none(outcome_summary.get("average_return_pct")),
            "average_days_held": _safe_float_or_none(outcome_summary.get("average_days_held")),
            "strategy_performance_count": len(_as_list(edge_summary.get("strategy_performance"))),
            "symbol_performance_count": len(_as_list(edge_summary.get("symbol_performance"))),
            "setup_family_performance_count": len(
                _as_list(edge_summary.get("setup_family_performance"))
            ),
            "audit_status": audit_report.get("status"),
            "health_status": health_report.get("status"),
        },
        "event_log_path": str(event_log_path) if event_log_path else None,
        "metadata": dict(metadata or {}),
        "explicit_exclusions": list(edge_summary.get("explicit_exclusions", [])),
    }


def _build_event(
    *,
    edge_summary: Mapping[str, Any],
    event_type: str,
    sequence: int,
    status: str,
) -> dict[str, Any]:
    outcome_summary = _as_mapping(edge_summary.get("outcome_summary"))
    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "event_type": event_type,
        "sequence": sequence,
        "status": status,
        "summary_date": _string_or_none(edge_summary.get("summary_date")),
        "source_record_count": _safe_int(edge_summary.get("source_record_count")),
        "closed_outcome_count": _safe_int(outcome_summary.get("closed_outcome_count")),
        "open_outcome_count": _safe_int(outcome_summary.get("open_outcome_count")),
        "pending_outcome_count": _safe_int(outcome_summary.get("pending_outcome_count")),
        "blocked_item_count": _safe_int(outcome_summary.get("blocked_item_count")),
    }


def _normalize_event_log_path(event_log_path: str | PathLike[str] | None) -> Path | None:
    if event_log_path is None:
        return None
    path = Path(event_log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _write_jsonl_event_log(path: Path, events: Sequence[Mapping[str, Any]]) -> None:
    lines = [json.dumps(dict(event), sort_keys=True) for event in events]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _classify_operation_status(*, summary_status: str, audit_status: str, health_status: str) -> str:
    if "blocked" in {summary_status, audit_status, health_status}:
        return "blocked"
    if "needs_review" in {summary_status, audit_status, health_status}:
        return "needs_review"
    return "ready"


def _classify_audit_status(*, summary_status: str, checks: Sequence[Mapping[str, Any]]) -> str:
    if any(check.get("passed") is not True and check.get("severity") == "blocker" for check in checks):
        return "blocked"
    if summary_status == "blocked":
        return "blocked"
    if summary_status == "needs_review" or any(check.get("passed") is not True for check in checks):
        return "needs_review"
    return "ready"


def _classify_health_status(*, summary_status: str, indicators: Mapping[str, Any]) -> str:
    if (
        indicators.get("has_order_intent")
        or indicators.get("has_broker_order_id")
        or indicators.get("has_automatic_action")
    ):
        return "blocked"
    if summary_status == "blocked" or indicators.get("has_blocked_items"):
        return "blocked"
    if (
        summary_status == "needs_review"
        or indicators.get("has_open_outcomes")
        or indicators.get("has_pending_outcomes")
        or indicators.get("has_needs_review_outcomes")
    ):
        return "needs_review"
    return "ready"


def _count_fields_match_summary_lists(edge_summary: Mapping[str, Any]) -> bool:
    outcome_summary = _as_mapping(edge_summary.get("outcome_summary"))
    return (
        _safe_int(outcome_summary.get("open_outcome_count")) == len(_as_list(edge_summary.get("open_outcomes")))
        and _safe_int(outcome_summary.get("pending_outcome_count")) == len(_as_list(edge_summary.get("pending_outcomes")))
        and _safe_int(outcome_summary.get("needs_review_outcome_count")) == len(_as_list(edge_summary.get("needs_review_outcomes")))
        and _safe_int(outcome_summary.get("blocked_item_count")) == len(_as_list(edge_summary.get("blocked_items")))
    )


def _blocked_items_have_reasons(edge_summary: Mapping[str, Any]) -> bool:
    return all(bool(_as_mapping(item).get("reason")) for item in _as_list(edge_summary.get("blocked_items")))


def _has_required_exclusions(edge_summary: Mapping[str, Any]) -> bool:
    exclusions = set(_as_list(edge_summary.get("explicit_exclusions")))
    return all(exclusion in exclusions for exclusion in REQUIRED_EXCLUSIONS)


def _contains_non_null_key(value: Any, *keys: str) -> bool:
    if isinstance(value, Mapping):
        for key in keys:
            if key in value and value.get(key) is not None:
                return True
        return any(_contains_non_null_key(item, *keys) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_non_null_key(item, *keys) for item in value)
    return False


def _check(*, name: str, passed: bool, severity: str, message: str, failure_message: str) -> dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "severity": severity,
        "message": message if passed else failure_message,
    }


def _summarize_checks(checks: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    passed = sum(1 for check in checks if check.get("passed") is True)
    failed = len(checks) - passed
    blockers = sum(
        1
        for check in checks
        if check.get("passed") is not True and check.get("severity") == "blocker"
    )
    warnings = sum(
        1
        for check in checks
        if check.get("passed") is not True and check.get("severity") != "blocker"
    )
    return {
        "check_count": len(checks),
        "passed_count": passed,
        "failed_count": failed,
        "blocker_count": blockers,
        "warning_count": warnings,
    }


def _safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    try:
        return round(float(value or 0.0), 4)
    except (TypeError, ValueError):
        return 0.0


def _safe_float_or_none(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None

