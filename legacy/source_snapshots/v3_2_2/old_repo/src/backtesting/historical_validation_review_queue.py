# src/backtesting/historical_validation_review_queue.py

from __future__ import annotations

from typing import Any, Iterable, Mapping


QUEUE_TYPE = "historical_validation_review_queue"

EXPLICIT_EXCLUSIONS = [
    "broker_api_calls",
    "order_routing",
    "order_submission",
    "fills",
    "live_execution",
    "slippage_modeling",
]

REQUIRED_SUMMARY_EXPORT_FIELDS = {
    "export_status",
    "is_blocked",
    "summary_type",
    "export_name",
    "validation_errors",
    "validation_summary",
    "promotion_summary",
    "edge_summary",
    "review_flags",
    "explicit_exclusions",
    "metadata",
}


def build_historical_validation_review_queue(
    summary_exports: Iterable[Mapping[str, Any]],
    *,
    queue_name: str = QUEUE_TYPE,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    exports = [dict(item) for item in summary_exports]
    metadata_dict = dict(metadata or {})

    validation_errors = _validate_summary_exports(exports)

    if validation_errors:
        return {
            "queue_status": "blocked",
            "is_blocked": True,
            "queue_type": QUEUE_TYPE,
            "queue_name": queue_name,
            "validation_errors": validation_errors,
            "promoted_review": [],
            "needs_review": [],
            "blocked_review": [],
            "review_counts": {
                "promoted_review": 0,
                "needs_review": 0,
                "blocked_review": 0,
                "total": 0,
            },
            "warnings": [],
            "blocked_reasons": validation_errors,
            "explicit_exclusions": EXPLICIT_EXCLUSIONS,
            "metadata": metadata_dict,
        }

    promoted_review: list[dict[str, Any]] = []
    needs_review: list[dict[str, Any]] = []
    blocked_review: list[dict[str, Any]] = []
    warnings: list[str] = []
    blocked_reasons: list[str] = []

    for export in exports:
        review_item = _build_review_item(export)
        review_flags = dict(export.get("review_flags", {}))

        item_warnings = [str(item) for item in review_flags.get("warnings", [])]
        item_blocked_reasons = [
            str(item) for item in review_flags.get("blocked_reasons", [])
        ]

        warnings.extend(item_warnings)
        blocked_reasons.extend(item_blocked_reasons)

        if export.get("is_blocked") is True or item_blocked_reasons:
            blocked_review.append(review_item)
        elif review_flags.get("is_promoted") is True and not review_flags.get(
            "requires_review",
            True,
        ):
            promoted_review.append(review_item)
        else:
            needs_review.append(review_item)

    promoted_review = _sort_queue(promoted_review)
    needs_review = _sort_queue(needs_review)
    blocked_review = _sort_queue(blocked_review)

    warnings = _unique_ordered(warnings)
    blocked_reasons = _unique_ordered(blocked_reasons)

    return {
        "queue_status": "completed",
        "is_blocked": False,
        "queue_type": QUEUE_TYPE,
        "queue_name": queue_name,
        "validation_errors": [],
        "promoted_review": promoted_review,
        "needs_review": needs_review,
        "blocked_review": blocked_review,
        "review_counts": {
            "promoted_review": len(promoted_review),
            "needs_review": len(needs_review),
            "blocked_review": len(blocked_review),
            "total": len(exports),
        },
        "warnings": warnings,
        "blocked_reasons": blocked_reasons,
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
        "metadata": metadata_dict,
    }


def _validate_summary_exports(exports: list[dict[str, Any]]) -> list[str]:
    validation_errors: list[str] = []

    if not exports:
        validation_errors.append("summary_exports must not be empty")
        return validation_errors

    seen_export_names: set[str] = set()

    for index, export in enumerate(exports):
        if not isinstance(export, Mapping):
            validation_errors.append(f"summary_exports[{index}] must be a mapping")
            continue

        missing_fields = sorted(REQUIRED_SUMMARY_EXPORT_FIELDS - set(export.keys()))
        if missing_fields:
            validation_errors.append(
                f"summary_exports[{index}] missing required fields: {missing_fields}"
            )

        export_status = export.get("export_status")
        if export_status is not None and export_status not in {
            "completed",
            "blocked",
        }:
            validation_errors.append(
                f"summary_exports[{index}] invalid export_status: {export_status}"
            )

        if "is_blocked" in export and not isinstance(export["is_blocked"], bool):
            validation_errors.append(
                f"summary_exports[{index}] is_blocked must be a boolean"
            )

        if "review_flags" in export and not isinstance(
            export["review_flags"],
            Mapping,
        ):
            validation_errors.append(
                f"summary_exports[{index}] review_flags must be a mapping"
            )

        if "validation_summary" in export and not isinstance(
            export["validation_summary"],
            Mapping,
        ):
            validation_errors.append(
                f"summary_exports[{index}] validation_summary must be a mapping"
            )

        if "promotion_summary" in export and not isinstance(
            export["promotion_summary"],
            Mapping,
        ):
            validation_errors.append(
                f"summary_exports[{index}] promotion_summary must be a mapping"
            )

        if "edge_summary" in export and not isinstance(
            export["edge_summary"],
            Mapping,
        ):
            validation_errors.append(
                f"summary_exports[{index}] edge_summary must be a mapping"
            )

        export_name = export.get("export_name")
        if export_name in seen_export_names:
            validation_errors.append(
                f"summary_exports[{index}] duplicate export_name: {export_name}"
            )
        elif export_name is not None:
            seen_export_names.add(str(export_name))

        explicit_exclusions = export.get("explicit_exclusions")
        if explicit_exclusions is not None and list(explicit_exclusions) != EXPLICIT_EXCLUSIONS:
            validation_errors.append(
                f"summary_exports[{index}] explicit_exclusions do not match required exclusions"
            )

    return validation_errors


def _build_review_item(summary_export: Mapping[str, Any]) -> dict[str, Any]:
    validation_summary = dict(summary_export.get("validation_summary", {}))
    promotion_summary = dict(summary_export.get("promotion_summary", {}))
    edge_summary = dict(summary_export.get("edge_summary", {}))
    review_flags = dict(summary_export.get("review_flags", {}))
    option_behavior_review = dict(
        summary_export.get("option_behavior_review", {})
    )
        
    return {
        "export_name": summary_export.get("export_name"),
        "export_status": summary_export.get("export_status"),
        "validation_status": validation_summary.get("validation_status"),
        "promotion_status": promotion_summary.get("promotion_status"),
        "is_validated": bool(review_flags.get("is_validated")),
        "is_promoted": bool(review_flags.get("is_promoted")),
        "requires_review": bool(review_flags.get("requires_review")),
        "has_warnings": bool(review_flags.get("has_warnings")),
        "has_blocked_reasons": bool(review_flags.get("has_blocked_reasons")),
        "matrix_run_count": int(validation_summary.get("matrix_run_count", 0)),
        "completed_run_count": int(validation_summary.get("completed_run_count", 0)),
        "blocked_run_count": int(validation_summary.get("blocked_run_count", 0)),
        "stable_run_count": int(validation_summary.get("stable_run_count", 0)),
        "completed_run_ratio": _round(
            promotion_summary.get("completed_run_ratio", 0.0)
        ),
        "stable_run_ratio": _round(promotion_summary.get("stable_run_ratio", 0.0)),
        "positive_edge_run_ratio": _round(
            promotion_summary.get("positive_edge_run_ratio", 0.0)
        ),
        "positive_hit_rate_edge_run_ratio": _round(
            promotion_summary.get("positive_hit_rate_edge_run_ratio", 0.0)
        ),
        "overall_avg_accepted_minus_rejected_avg_direction_adjusted_outcome": _round(
            edge_summary.get(
                "overall_avg_accepted_minus_rejected_avg_direction_adjusted_outcome",
                0.0,
            )
        ),
        "overall_avg_accepted_minus_rejected_hit_rate": _round(
            edge_summary.get(
                "overall_avg_accepted_minus_rejected_hit_rate",
                0.0,
            )
        ),
        "option_behavior_review": option_behavior_review,
        "warnings": list(review_flags.get("warnings", [])),
        "blocked_reasons": list(review_flags.get("blocked_reasons", [])),
        "metadata": dict(summary_export.get("metadata", {})),
    }


def _sort_queue(queue_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        queue_items,
        key=lambda item: (
            -float(
                item[
                    "overall_avg_accepted_minus_rejected_avg_direction_adjusted_outcome"
                ]
            ),
            -float(item["overall_avg_accepted_minus_rejected_hit_rate"]),
            str(item["export_name"]),
        ),
    )


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
