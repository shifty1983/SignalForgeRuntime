# src/backtesting/historical_research_priority_report.py

from __future__ import annotations

from typing import Any, Mapping


REPORT_TYPE = "historical_research_priority_report"

EXPLICIT_EXCLUSIONS = [
    "broker_api_calls",
    "order_routing",
    "order_submission",
    "fills",
    "live_execution",
    "slippage_modeling",
]

REQUIRED_SNAPSHOT_FIELDS = {
    "snapshot_status",
    "is_ready",
    "is_blocked",
    "snapshot_type",
    "snapshot_name",
    "validation_errors",
    "promoted_decisions",
    "needs_review_decisions",
    "blocked_decisions",
    "decision_counts",
    "warnings",
    "blocked_reasons",
    "explicit_exclusions",
}


def build_historical_research_priority_report(
    decision_snapshot: Mapping[str, Any],
    *,
    report_name: str = REPORT_TYPE,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    metadata_dict = dict(metadata or {})

    validation_errors = _validate_decision_snapshot_shape(decision_snapshot)

    if validation_errors:
        return {
            "report_status": "blocked",
            "is_ready": False,
            "is_blocked": True,
            "report_type": REPORT_TYPE,
            "report_name": report_name,
            "validation_errors": validation_errors,
            "priority_candidates": [],
            "needs_review_candidates": [],
            "blocked_candidates": [],
            "priority_summary": {
                "priority_count": 0,
                "needs_review_count": 0,
                "blocked_count": 0,
                "total_count": 0,
            },
            "warnings": [],
            "blocked_reasons": validation_errors,
            "explicit_exclusions": EXPLICIT_EXCLUSIONS,
            "source_summary": {},
            "metadata": metadata_dict,
        }

    promoted_decisions = [
        dict(item) for item in decision_snapshot.get("promoted_decisions", [])
    ]
    needs_review_decisions = [
        dict(item) for item in decision_snapshot.get("needs_review_decisions", [])
    ]
    blocked_decisions = [
        dict(item) for item in decision_snapshot.get("blocked_decisions", [])
    ]

    priority_candidates = _rank_candidates(
        [
            _build_candidate(item, priority_status="priority")
            for item in promoted_decisions
        ]
    )
    needs_review_candidates = _rank_candidates(
        [
            _build_candidate(item, priority_status="needs_review")
            for item in needs_review_decisions
        ]
    )
    blocked_candidates = _rank_candidates(
        [
            _build_candidate(item, priority_status="blocked")
            for item in blocked_decisions
        ]
    )

    warnings = _unique_ordered(
        [str(item) for item in decision_snapshot.get("warnings", [])]
    )
    blocked_reasons = _unique_ordered(
        [str(item) for item in decision_snapshot.get("blocked_reasons", [])]
    )

    priority_count = len(priority_candidates)
    needs_review_count = len(needs_review_candidates)
    blocked_count = len(blocked_candidates)
    total_count = priority_count + needs_review_count + blocked_count

    snapshot_status = decision_snapshot.get("snapshot_status")

    if decision_snapshot.get("is_blocked") is True or blocked_reasons:
        report_status = "blocked"
    elif snapshot_status == "needs_review" or needs_review_count > 0 or warnings:
        report_status = "needs_review"
    else:
        report_status = "ready"

    return {
        "report_status": report_status,
        "is_ready": report_status == "ready",
        "is_blocked": report_status == "blocked",
        "report_type": REPORT_TYPE,
        "report_name": report_name,
        "validation_errors": [],
        "priority_candidates": priority_candidates,
        "needs_review_candidates": needs_review_candidates,
        "blocked_candidates": blocked_candidates,
        "priority_summary": {
            "priority_count": priority_count,
            "needs_review_count": needs_review_count,
            "blocked_count": blocked_count,
            "total_count": total_count,
        },
        "warnings": warnings,
        "blocked_reasons": blocked_reasons,
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
        "source_summary": {
            "snapshot_name": decision_snapshot.get("snapshot_name"),
            "snapshot_status": snapshot_status,
            "is_ready": bool(decision_snapshot.get("is_ready")),
            "is_blocked": bool(decision_snapshot.get("is_blocked")),
            "decision_counts": dict(decision_snapshot.get("decision_counts", {})),
            "source_operation_summary": dict(
                decision_snapshot.get("source_summary", {})
            ),
        },
        "metadata": metadata_dict,
    }


def _validate_decision_snapshot_shape(
    decision_snapshot: Mapping[str, Any],
) -> list[str]:
    validation_errors: list[str] = []

    missing_fields = sorted(REQUIRED_SNAPSHOT_FIELDS - set(decision_snapshot.keys()))
    if missing_fields:
        validation_errors.append(
            f"decision_snapshot missing required fields: {missing_fields}"
        )

    snapshot_status = decision_snapshot.get("snapshot_status")
    if snapshot_status is not None and snapshot_status not in {
        "ready",
        "needs_review",
        "blocked",
    }:
        validation_errors.append(
            f"decision_snapshot invalid snapshot_status: {snapshot_status}"
        )

    if "is_ready" in decision_snapshot and not isinstance(
        decision_snapshot["is_ready"],
        bool,
    ):
        validation_errors.append("decision_snapshot is_ready must be a boolean")

    if "is_blocked" in decision_snapshot and not isinstance(
        decision_snapshot["is_blocked"],
        bool,
    ):
        validation_errors.append("decision_snapshot is_blocked must be a boolean")

    for list_field in [
        "validation_errors",
        "promoted_decisions",
        "needs_review_decisions",
        "blocked_decisions",
        "warnings",
        "blocked_reasons",
        "explicit_exclusions",
    ]:
        if list_field in decision_snapshot and not isinstance(
            decision_snapshot[list_field],
            list,
        ):
            validation_errors.append(
                f"decision_snapshot {list_field} must be a list"
            )

    if "decision_counts" in decision_snapshot and not isinstance(
        decision_snapshot["decision_counts"],
        Mapping,
    ):
        validation_errors.append("decision_snapshot decision_counts must be a mapping")

    explicit_exclusions = decision_snapshot.get("explicit_exclusions")
    if explicit_exclusions is not None and list(explicit_exclusions) != EXPLICIT_EXCLUSIONS:
        validation_errors.append(
            "decision_snapshot explicit_exclusions do not match required exclusions"
        )

    return validation_errors


def _build_candidate(
    decision: Mapping[str, Any],
    *,
    priority_status: str,
) -> dict[str, Any]:
    avg_outcome_edge = _round(
        decision.get(
            "overall_avg_accepted_minus_rejected_avg_direction_adjusted_outcome",
            0.0,
        )
    )
    hit_rate_edge = _round(
        decision.get("overall_avg_accepted_minus_rejected_hit_rate", 0.0)
    )
    completed_run_ratio = _round(decision.get("completed_run_ratio", 0.0))
    stable_run_ratio = _round(decision.get("stable_run_ratio", 0.0))
    positive_edge_run_ratio = _round(decision.get("positive_edge_run_ratio", 0.0))
    positive_hit_rate_edge_run_ratio = _round(
        decision.get("positive_hit_rate_edge_run_ratio", 0.0)
    )

    priority_score = _round(
        avg_outcome_edge
        + hit_rate_edge
        + completed_run_ratio
        + stable_run_ratio
        + positive_edge_run_ratio
        + positive_hit_rate_edge_run_ratio
    )

    return {
        "priority_status": priority_status,
        "export_name": decision.get("export_name"),
        "validation_status": decision.get("validation_status"),
        "promotion_status": decision.get("promotion_status"),
        "is_validated": bool(decision.get("is_validated")),
        "is_promoted": bool(decision.get("is_promoted")),
        "requires_review": bool(decision.get("requires_review")),
        "matrix_run_count": int(decision.get("matrix_run_count", 0)),
        "completed_run_count": int(decision.get("completed_run_count", 0)),
        "blocked_run_count": int(decision.get("blocked_run_count", 0)),
        "stable_run_count": int(decision.get("stable_run_count", 0)),
        "completed_run_ratio": completed_run_ratio,
        "stable_run_ratio": stable_run_ratio,
        "positive_edge_run_ratio": positive_edge_run_ratio,
        "positive_hit_rate_edge_run_ratio": positive_hit_rate_edge_run_ratio,
        "overall_avg_accepted_minus_rejected_avg_direction_adjusted_outcome": avg_outcome_edge,
        "overall_avg_accepted_minus_rejected_hit_rate": hit_rate_edge,
        "priority_score": priority_score,
        "option_behavior_review": dict(decision.get("option_behavior_review", {})),
        "warnings": list(decision.get("warnings", [])),
        "blocked_reasons": list(decision.get("blocked_reasons", [])),
        "metadata": dict(decision.get("metadata", {})),
    }


def _rank_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(
        candidates,
        key=lambda item: (
            -float(item["priority_score"]),
            -float(
                item[
                    "overall_avg_accepted_minus_rejected_avg_direction_adjusted_outcome"
                ]
            ),
            -float(item["overall_avg_accepted_minus_rejected_hit_rate"]),
            str(item["export_name"]),
        ),
    )

    return [
        {
            **candidate,
            "priority_rank": index + 1,
        }
        for index, candidate in enumerate(ranked)
    ]


def _unique_ordered(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []

    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)

    return result


def _round(value: Any) -> float:
    return round(float(value or 0.0), 10)
