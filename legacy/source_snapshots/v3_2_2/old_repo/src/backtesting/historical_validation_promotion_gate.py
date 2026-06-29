# src/backtesting/historical_validation_promotion_gate.py

from __future__ import annotations

from typing import Any, Mapping


REQUIRED_VALIDATION_RESULT_FIELDS = {
    "operation_type",
    "operation_name",
    "validation_status",
    "is_validated",
    "is_blocked",
    "matrix_result",
    "diagnostics_report",
    "blocked_reasons",
    "warnings",
    "summary",
}


def evaluate_historical_validation_promotion_gate(
    validation_result: Mapping[str, Any],
    *,
    min_stable_run_ratio: float = 1.0,
    min_positive_edge_run_ratio: float = 1.0,
    min_positive_hit_rate_edge_run_ratio: float = 1.0,
    min_completed_run_ratio: float = 1.0,
    require_validated_status: bool = True,
) -> dict[str, Any]:
    validation_errors = _validate_validation_result_shape(validation_result)

    if validation_errors:
        return {
            "promotion_status": "blocked",
            "is_promoted": False,
            "is_blocked": True,
            "validation_errors": validation_errors,
            "blocked_reasons": validation_errors,
            "warnings": [],
            "promotion_metrics": {},
            "summary": {
                "validation_status": validation_result.get("validation_status"),
                "diagnostic_status": None,
                "matrix_run_count": 0,
                "completed_run_count": 0,
                "stable_run_count": 0,
                "positive_edge_run_count": 0,
                "positive_hit_rate_edge_run_count": 0,
            },
        }

    summary = dict(validation_result["summary"])
    diagnostics_report = dict(validation_result["diagnostics_report"])
    diagnostics_summary = dict(diagnostics_report.get("summary", {}))

    matrix_run_count = int(summary.get("matrix_run_count", 0))
    completed_run_count = int(summary.get("completed_run_count", 0))
    blocked_run_count = int(summary.get("blocked_run_count", 0))
    stable_run_count = int(summary.get("stable_run_count", 0))
    positive_edge_run_count = int(summary.get("positive_edge_run_count", 0))
    positive_hit_rate_edge_run_count = int(
        summary.get("positive_hit_rate_edge_run_count", 0)
    )

    completed_run_ratio = _safe_ratio(completed_run_count, matrix_run_count)
    stable_run_ratio = _safe_ratio(stable_run_count, matrix_run_count)
    positive_edge_run_ratio = _safe_ratio(positive_edge_run_count, matrix_run_count)
    positive_hit_rate_edge_run_ratio = _safe_ratio(
        positive_hit_rate_edge_run_count,
        matrix_run_count,
    )

    blocked_reasons: list[str] = []
    warnings: list[str] = []

    validation_status = validation_result.get("validation_status")
    diagnostic_status = diagnostics_report.get("diagnostic_status")

    if validation_result.get("is_blocked") is True:
        blocked_reasons.append("validation_result is blocked")

    if require_validated_status and validation_status == "blocked":
        blocked_reasons.append(
            f"validation_status is not validated: {validation_status}"
        )

    if diagnostic_status == "blocked":
        blocked_reasons.append("diagnostics_report is blocked")
    elif diagnostic_status != "healthy":
        warnings.append(f"diagnostic_status is not healthy: {diagnostic_status}")

    if matrix_run_count == 0:
        blocked_reasons.append("matrix_run_count is zero")

    if completed_run_ratio < min_completed_run_ratio:
        warnings.append("completed run ratio is below promotion threshold")

    if stable_run_ratio < min_stable_run_ratio:
        warnings.append("stable run ratio is below promotion threshold")

    if positive_edge_run_ratio < min_positive_edge_run_ratio:
        warnings.append("positive edge run ratio is below promotion threshold")

    if positive_hit_rate_edge_run_ratio < min_positive_hit_rate_edge_run_ratio:
        warnings.append("positive hit-rate edge run ratio is below promotion threshold")

    warnings.extend(str(item) for item in validation_result.get("warnings", []))
    blocked_reasons.extend(
        str(item) for item in validation_result.get("blocked_reasons", [])
    )

    promotion_metrics = {
        "matrix_run_count": matrix_run_count,
        "completed_run_count": completed_run_count,
        "blocked_run_count": blocked_run_count,
        "stable_run_count": stable_run_count,
        "positive_edge_run_count": positive_edge_run_count,
        "positive_hit_rate_edge_run_count": positive_hit_rate_edge_run_count,
        "completed_run_ratio": _round(completed_run_ratio),
        "stable_run_ratio": _round(stable_run_ratio),
        "positive_edge_run_ratio": _round(positive_edge_run_ratio),
        "positive_hit_rate_edge_run_ratio": _round(
            positive_hit_rate_edge_run_ratio
        ),
        "overall_avg_accepted_minus_rejected_avg_direction_adjusted_outcome": _round(
            diagnostics_summary.get(
                "overall_avg_accepted_minus_rejected_avg_direction_adjusted_outcome",
                0.0,
            )
        ),
        "overall_avg_accepted_minus_rejected_hit_rate": _round(
            diagnostics_summary.get(
                "overall_avg_accepted_minus_rejected_hit_rate",
                0.0,
            )
        ),
        "min_stable_run_ratio": _round(min_stable_run_ratio),
        "min_positive_edge_run_ratio": _round(min_positive_edge_run_ratio),
        "min_positive_hit_rate_edge_run_ratio": _round(
            min_positive_hit_rate_edge_run_ratio
        ),
        "min_completed_run_ratio": _round(min_completed_run_ratio),
        "require_validated_status": require_validated_status,
    }

    if blocked_reasons:
        promotion_status = "blocked"
    elif warnings:
        promotion_status = "needs_review"
    else:
        promotion_status = "promoted"

    return {
        "promotion_status": promotion_status,
        "is_promoted": promotion_status == "promoted",
        "is_blocked": promotion_status == "blocked",
        "validation_errors": [],
        "blocked_reasons": blocked_reasons,
        "warnings": warnings,
        "promotion_metrics": promotion_metrics,
        "summary": {
            "validation_status": validation_status,
            "diagnostic_status": diagnostic_status,
            "matrix_run_count": matrix_run_count,
            "completed_run_count": completed_run_count,
            "stable_run_count": stable_run_count,
            "positive_edge_run_count": positive_edge_run_count,
            "positive_hit_rate_edge_run_count": positive_hit_rate_edge_run_count,
            "best_run": summary.get("best_run"),
            "worst_run": summary.get("worst_run"),
        },
    }


def _validate_validation_result_shape(
    validation_result: Mapping[str, Any],
) -> list[str]:
    validation_errors: list[str] = []

    missing_fields = sorted(
        REQUIRED_VALIDATION_RESULT_FIELDS - set(validation_result.keys())
    )
    if missing_fields:
        validation_errors.append(
            f"validation_result missing required fields: {missing_fields}"
        )

    validation_status = validation_result.get("validation_status")
    if validation_status is not None and validation_status not in {
        "validated",
        "needs_review",
        "blocked",
    }:
        validation_errors.append(
            f"validation_result invalid validation_status: {validation_status}"
        )

    if "is_validated" in validation_result and not isinstance(
        validation_result["is_validated"],
        bool,
    ):
        validation_errors.append("validation_result is_validated must be a boolean")

    if "is_blocked" in validation_result and not isinstance(
        validation_result["is_blocked"],
        bool,
    ):
        validation_errors.append("validation_result is_blocked must be a boolean")

    if "summary" in validation_result and not isinstance(
        validation_result["summary"],
        Mapping,
    ):
        validation_errors.append("validation_result summary must be a mapping")

    if "diagnostics_report" in validation_result and not isinstance(
        validation_result["diagnostics_report"],
        Mapping,
    ):
        validation_errors.append(
            "validation_result diagnostics_report must be a mapping"
        )

    if "blocked_reasons" in validation_result and not isinstance(
        validation_result["blocked_reasons"],
        list,
    ):
        validation_errors.append("validation_result blocked_reasons must be a list")

    if "warnings" in validation_result and not isinstance(
        validation_result["warnings"],
        list,
    ):
        validation_errors.append("validation_result warnings must be a list")

    return validation_errors


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0

    return numerator / denominator


def _round(value: Any) -> float:
    return round(float(value or 0.0), 10)
