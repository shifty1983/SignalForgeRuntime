from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from os import PathLike
from pathlib import Path
from typing import Any

from src.options_portfolio.edge_validation_review import (
    EXPLICIT_EXCLUSIONS,
    build_options_edge_validation_review,
)


OPERATION_SCHEMA_VERSION = "options_edge_validation_review_operation.v1"
EVENT_SCHEMA_VERSION = "options_edge_validation_review_operation_event.v1"
AUDIT_SCHEMA_VERSION = "options_edge_validation_review_audit.v1"
HEALTH_SCHEMA_VERSION = "options_edge_validation_review_health.v1"

OPERATION_TYPE = "options_edge_validation_review_operation"
VALID_REVIEW_STATUSES = {"ready", "needs_review", "blocked"}
VALID_EDGE_CLASSIFICATIONS = {
    "edge_supported",
    "needs_more_data",
    "underperforming",
    "blocked",
}
REQUIRED_EXCLUSIONS = tuple(EXPLICIT_EXCLUSIONS)


def run_options_edge_validation_review_operation(
    source: Mapping[str, Any] | None,
    *,
    metadata: Mapping[str, Any] | None = None,
    event_log_path: str | PathLike[str] | None = None,
) -> dict[str, Any]:
    """Run options edge validation review as an auditable operation.

    This operation classifies outcome-summary evidence only. It never calls broker
    APIs, routes orders, submits orders, models fills, performs live execution,
    models slippage, or creates automatic close/roll/defense orders.
    """

    edge_review = build_options_edge_validation_review(source or {})
    audit_report = build_options_edge_validation_review_audit_report(edge_review)
    health_report = build_options_edge_validation_review_health_report(edge_review)
    operation_status = _classify_operation_status(
        review_status=str(edge_review.get("status", "needs_review")),
        audit_status=str(audit_report.get("status", "needs_review")),
        health_status=str(health_report.get("status", "needs_review")),
    )

    events = [
        _build_event(
            edge_review=edge_review,
            event_type="options_edge_validation_review_operation_started",
            sequence=1,
            status=operation_status,
        ),
        _build_event(
            edge_review=edge_review,
            event_type="options_edge_validation_review_operation_completed",
            sequence=2,
            status=operation_status,
        ),
    ]

    normalized_log_path = _normalize_event_log_path(event_log_path)
    if normalized_log_path is not None:
        _write_jsonl_event_log(normalized_log_path, events)

    operation_record = _build_operation_record(
        edge_review=edge_review,
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
        "options_edge_validation_review": edge_review,
        "events": events,
        "event_log_path": str(normalized_log_path) if normalized_log_path else None,
        "explicit_exclusions": list(edge_review.get("explicit_exclusions", [])),
    }


def build_options_edge_validation_review_audit_report(
    edge_review: Mapping[str, Any]
) -> dict[str, Any]:
    checks = [
        _check(
            name="edge_review_artifact_type_valid",
            passed=edge_review.get("artifact_type") == "options_edge_validation_review",
            severity="blocker",
            message="options edge validation review artifact type is valid",
            failure_message="options edge validation review artifact type is invalid",
        ),
        _check(
            name="edge_review_status_valid",
            passed=edge_review.get("status") in VALID_REVIEW_STATUSES,
            severity="blocker",
            message="options edge validation review status is valid",
            failure_message="options edge validation review status is invalid",
        ),
        _check(
            name="overall_edge_classification_valid",
            passed=_as_mapping(edge_review.get("overall_review")).get("edge_classification")
            in VALID_EDGE_CLASSIFICATIONS,
            severity="blocker",
            message="overall options edge classification is valid",
            failure_message="overall options edge classification is invalid",
        ),
        _check(
            name="explicit_exclusions_present",
            passed=_has_required_exclusions(edge_review),
            severity="blocker",
            message="options edge validation review exclusions are present",
            failure_message="one or more required exclusions are missing",
        ),
        _check(
            name="no_order_intents_created",
            passed=not _contains_non_null_key(edge_review, "order_intent"),
            severity="blocker",
            message="options edge validation review did not create order intents",
            failure_message="options edge validation review created one or more order intents",
        ),
        _check(
            name="no_broker_order_ids_created",
            passed=not _contains_non_null_key(edge_review, "broker_order_id"),
            severity="blocker",
            message="options edge validation review did not create broker order ids",
            failure_message="options edge validation review created one or more broker order ids",
        ),
        _check(
            name="no_automatic_actions_created",
            passed=not _contains_non_null_key(
                edge_review,
                "automatic_action",
                "maintenance_action",
                "defense_action",
            ),
            severity="blocker",
            message="options edge validation review did not create automatic actions",
            failure_message="options edge validation review created one or more automatic actions",
        ),
        _check(
            name="blocked_items_have_reasons",
            passed=_blocked_items_have_reasons(edge_review),
            severity="warning",
            message="blocked options edge review items include reasons",
            failure_message="one or more blocked options edge review items are missing reasons",
        ),
        _check(
            name="review_actions_require_manual_approval",
            passed=_review_actions_require_manual_approval(edge_review),
            severity="warning",
            message="options edge review actions require manual approval",
            failure_message="one or more options edge review actions do not require manual approval",
        ),
    ]

    audit_summary = _summarize_checks(checks)

    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_audit_status(
            review_status=str(edge_review.get("status", "needs_review")),
            checks=checks,
        ),
        "summary": audit_summary,
        "checks": checks,
        "explicit_exclusions": list(edge_review.get("explicit_exclusions", [])),
    }


def build_options_edge_validation_review_health_report(
    edge_review: Mapping[str, Any]
) -> dict[str, Any]:
    review_status = str(edge_review.get("status", "needs_review"))
    overall_review = _as_mapping(edge_review.get("overall_review"))
    strategy_reviews = _as_list(edge_review.get("strategy_reviews"))
    symbol_reviews = _as_list(edge_review.get("symbol_reviews"))
    setup_family_reviews = _as_list(edge_review.get("setup_family_reviews"))
    review_actions = _as_list(edge_review.get("review_actions"))
    blocked_items = _as_list(edge_review.get("blocked_items"))

    indicators = {
        "review_status": review_status,
        "review_date": _string_or_none(edge_review.get("review_date")),
        "source_summary_count": _safe_int(edge_review.get("source_summary_count")),
        "overall_edge_classification": _string_or_none(
            overall_review.get("edge_classification")
        ),
        "overall_closed_outcome_count": _safe_int(
            overall_review.get("closed_outcome_count")
        ),
        "overall_win_rate": _safe_float_or_none(overall_review.get("win_rate")),
        "overall_total_realized_pnl": _safe_float(
            overall_review.get("total_realized_pnl")
        ),
        "overall_average_return_pct": _safe_float_or_none(
            overall_review.get("average_return_pct")
        ),
        "strategy_review_count": len(strategy_reviews),
        "symbol_review_count": len(symbol_reviews),
        "setup_family_review_count": len(setup_family_reviews),
        "review_action_count": len(review_actions),
        "blocked_item_count": len(blocked_items),
        "has_edge_supported": _has_classification(edge_review, "edge_supported"),
        "has_needs_more_data": _has_classification(edge_review, "needs_more_data"),
        "has_underperforming": _has_classification(edge_review, "underperforming"),
        "has_blocked_items": bool(blocked_items),
        "has_order_intent": _contains_non_null_key(edge_review, "order_intent"),
        "has_broker_order_id": _contains_non_null_key(edge_review, "broker_order_id"),
        "has_automatic_action": _contains_non_null_key(edge_review, "automatic_action"),
    }

    return {
        "schema_version": HEALTH_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_health_status(
            review_status=review_status,
            indicators=indicators,
        ),
        "indicators": indicators,
        "explicit_exclusions": list(edge_review.get("explicit_exclusions", [])),
    }


def _build_operation_record(
    *,
    edge_review: Mapping[str, Any],
    audit_report: Mapping[str, Any],
    health_report: Mapping[str, Any],
    operation_status: str,
    event_log_path: Path | None,
    metadata: Mapping[str, Any] | None,
) -> dict[str, Any]:
    overall_review = _as_mapping(edge_review.get("overall_review"))
    return {
        "operation_type": OPERATION_TYPE,
        "schema_version": OPERATION_SCHEMA_VERSION,
        "status": operation_status,
        "review_date": _string_or_none(edge_review.get("review_date")),
        "source_summary_count": _safe_int(edge_review.get("source_summary_count")),
        "operation_summary": {
            "overall_edge_classification": _string_or_none(
                overall_review.get("edge_classification")
            ),
            "overall_closed_outcome_count": _safe_int(
                overall_review.get("closed_outcome_count")
            ),
            "overall_win_rate": _safe_float_or_none(overall_review.get("win_rate")),
            "overall_total_realized_pnl": _safe_float(
                overall_review.get("total_realized_pnl")
            ),
            "overall_average_return_pct": _safe_float_or_none(
                overall_review.get("average_return_pct")
            ),
            "strategy_review_count": len(_as_list(edge_review.get("strategy_reviews"))),
            "symbol_review_count": len(_as_list(edge_review.get("symbol_reviews"))),
            "setup_family_review_count": len(_as_list(edge_review.get("setup_family_reviews"))),
            "review_action_count": len(_as_list(edge_review.get("review_actions"))),
            "blocked_item_count": len(_as_list(edge_review.get("blocked_items"))),
            "audit_status": audit_report.get("status"),
            "health_status": health_report.get("status"),
        },
        "event_log_path": str(event_log_path) if event_log_path else None,
        "metadata": dict(metadata or {}),
        "explicit_exclusions": list(edge_review.get("explicit_exclusions", [])),
    }


def _build_event(
    *,
    edge_review: Mapping[str, Any],
    event_type: str,
    sequence: int,
    status: str,
) -> dict[str, Any]:
    overall_review = _as_mapping(edge_review.get("overall_review"))
    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "event_type": event_type,
        "sequence": sequence,
        "status": status,
        "review_date": _string_or_none(edge_review.get("review_date")),
        "source_summary_count": _safe_int(edge_review.get("source_summary_count")),
        "overall_edge_classification": _string_or_none(
            overall_review.get("edge_classification")
        ),
        "review_action_count": len(_as_list(edge_review.get("review_actions"))),
        "blocked_item_count": len(_as_list(edge_review.get("blocked_items"))),
    }


def _check(
    *,
    name: str,
    passed: bool,
    severity: str,
    message: str,
    failure_message: str,
) -> dict[str, Any]:
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


def _classify_operation_status(
    *,
    review_status: str,
    audit_status: str,
    health_status: str,
) -> str:
    if "blocked" in {review_status, audit_status, health_status}:
        return "blocked"
    if "needs_review" in {review_status, audit_status, health_status}:
        return "needs_review"
    return "ready"


def _classify_audit_status(*, review_status: str, checks: Sequence[Mapping[str, Any]]) -> str:
    if any(check.get("passed") is not True and check.get("severity") == "blocker" for check in checks):
        return "blocked"
    if review_status == "blocked":
        return "blocked"
    if review_status == "needs_review" or any(check.get("passed") is not True for check in checks):
        return "needs_review"
    return "ready"


def _classify_health_status(*, review_status: str, indicators: Mapping[str, Any]) -> str:
    if (
        indicators.get("has_order_intent")
        or indicators.get("has_broker_order_id")
        or indicators.get("has_automatic_action")
    ):
        return "blocked"
    if review_status == "blocked" or indicators.get("has_blocked_items"):
        return "blocked"
    if (
        review_status == "needs_review"
        or indicators.get("has_needs_more_data")
        or indicators.get("has_underperforming")
    ):
        return "needs_review"
    return "ready"


def _has_required_exclusions(edge_review: Mapping[str, Any]) -> bool:
    exclusions = set(_as_list(edge_review.get("explicit_exclusions")))
    return all(item in exclusions for item in REQUIRED_EXCLUSIONS)


def _blocked_items_have_reasons(edge_review: Mapping[str, Any]) -> bool:
    return all(bool(_as_mapping(item).get("reason")) for item in _as_list(edge_review.get("blocked_items")))


def _review_actions_require_manual_approval(edge_review: Mapping[str, Any]) -> bool:
    return all(
        _as_mapping(item).get("requires_manual_approval") is True
        for item in _as_list(edge_review.get("review_actions"))
    )


def _has_classification(edge_review: Mapping[str, Any], classification: str) -> bool:
    overall_review = _as_mapping(edge_review.get("overall_review"))
    if overall_review.get("edge_classification") == classification:
        return True
    for group_key in ("strategy_reviews", "symbol_reviews", "setup_family_reviews"):
        for row in _as_list(edge_review.get(group_key)):
            if _as_mapping(row).get("edge_classification") == classification:
                return True
    return False


def _contains_non_null_key(value: Any, *keys: str) -> bool:
    if isinstance(value, Mapping):
        for key in keys:
            if key in value and value.get(key) is not None:
                return True
        return any(_contains_non_null_key(item, *keys) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_non_null_key(item, *keys) for item in value)
    return False


def _normalize_event_log_path(path: str | PathLike[str] | None) -> Path | None:
    if path is None:
        return None
    normalized = Path(path)
    normalized.parent.mkdir(parents=True, exist_ok=True)
    return normalized


def _write_jsonl_event_log(path: Path, events: Sequence[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, sort_keys=True) + "\n")


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _safe_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

