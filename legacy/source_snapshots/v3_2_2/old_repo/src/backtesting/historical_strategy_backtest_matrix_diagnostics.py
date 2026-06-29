# src/backtesting/historical_strategy_backtest_matrix_diagnostics.py

from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Any, Mapping


REQUIRED_MATRIX_RESULT_FIELDS = {
    "operation_type",
    "operation_name",
    "runner_status",
    "is_blocked",
    "matrix_rows",
    "summary",
}


def evaluate_historical_strategy_backtest_matrix_diagnostics(
    matrix_result: Mapping[str, Any],
    *,
    min_avg_outcome_edge: float = 0.0,
    min_hit_rate_edge: float = 0.0,
    require_all_runs_completed: bool = False,
) -> dict[str, Any]:
    validation_errors = _validate_matrix_result(matrix_result)

    if validation_errors:
        return {
            "diagnostic_status": "blocked",
            "is_blocked": True,
            "is_healthy": False,
            "validation_errors": validation_errors,
            "blocked_reasons": validation_errors,
            "warnings": [],
            "summary": {
                "matrix_run_count": 0,
                "completed_run_count": 0,
                "blocked_run_count": 0,
                "stable_run_count": 0,
                "positive_edge_run_count": 0,
                "positive_hit_rate_edge_run_count": 0,
            },
            "by_forward_window": {},
            "by_neutral_band": {},
        }

    matrix_rows = [dict(row) for row in matrix_result.get("matrix_rows", [])]

    completed_rows = [
        row for row in matrix_rows if row.get("runner_status") == "completed"
    ]
    blocked_rows = [
        row for row in matrix_rows if row.get("runner_status") == "blocked"
    ]

    blocked_reasons: list[str] = []
    warnings: list[str] = []

    if not matrix_rows:
        blocked_reasons.append("matrix_result has no matrix rows")

    if not completed_rows:
        blocked_reasons.append("matrix_result has no completed runs")

    if blocked_rows and require_all_runs_completed:
        blocked_reasons.append("matrix_result has blocked child runs")
    elif blocked_rows:
        warnings.append(f"matrix_result has {len(blocked_rows)} blocked child run(s)")

    for row in completed_rows:
        operation_name = str(row.get("operation_name"))
        avg_outcome_edge = _as_float(
            row.get("accepted_minus_rejected_avg_direction_adjusted_outcome", 0.0)
        )
        hit_rate_edge = _as_float(
            row.get("accepted_minus_rejected_hit_rate", 0.0)
        )
        health_status = str(row.get("health_status", "unknown"))

        if avg_outcome_edge <= min_avg_outcome_edge:
            warnings.append(
                f"{operation_name} accepted-minus-rejected avg outcome edge is not above threshold"
            )

        if hit_rate_edge <= min_hit_rate_edge:
            warnings.append(
                f"{operation_name} accepted-minus-rejected hit-rate edge is not above threshold"
            )

        if health_status != "healthy":
            warnings.append(
                f"{operation_name} child health_status is {health_status}"
            )

    stable_rows = [
        row
        for row in completed_rows
        if _as_float(
            row.get("accepted_minus_rejected_avg_direction_adjusted_outcome", 0.0)
        )
        > min_avg_outcome_edge
        and _as_float(row.get("accepted_minus_rejected_hit_rate", 0.0))
        > min_hit_rate_edge
        and row.get("health_status") == "healthy"
    ]

    positive_edge_rows = [
        row
        for row in completed_rows
        if _as_float(
            row.get("accepted_minus_rejected_avg_direction_adjusted_outcome", 0.0)
        )
        > 0
    ]

    positive_hit_rate_edge_rows = [
        row
        for row in completed_rows
        if _as_float(row.get("accepted_minus_rejected_hit_rate", 0.0)) > 0
    ]

    if blocked_reasons:
        diagnostic_status = "blocked"
    elif warnings:
        diagnostic_status = "warning"
    else:
        diagnostic_status = "healthy"

    matrix_summary = dict(matrix_result.get("summary", {}))

    return {
        "diagnostic_status": diagnostic_status,
        "is_blocked": diagnostic_status == "blocked",
        "is_healthy": diagnostic_status == "healthy",
        "validation_errors": [],
        "blocked_reasons": blocked_reasons,
        "warnings": warnings,
        "summary": {
            "matrix_run_count": len(matrix_rows),
            "completed_run_count": len(completed_rows),
            "blocked_run_count": len(blocked_rows),
            "stable_run_count": len(stable_rows),
            "positive_edge_run_count": len(positive_edge_rows),
            "positive_hit_rate_edge_run_count": len(positive_hit_rate_edge_rows),
            "overall_avg_accepted_minus_rejected_avg_direction_adjusted_outcome": _average_metric(
                completed_rows,
                "accepted_minus_rejected_avg_direction_adjusted_outcome",
            ),
            "overall_avg_accepted_minus_rejected_hit_rate": _average_metric(
                completed_rows,
                "accepted_minus_rejected_hit_rate",
            ),
            "best_run": matrix_summary.get("best_run"),
            "worst_run": matrix_summary.get("worst_run"),
            "min_avg_outcome_edge": _round(min_avg_outcome_edge),
            "min_hit_rate_edge": _round(min_hit_rate_edge),
            "require_all_runs_completed": require_all_runs_completed,
        },
        "by_forward_window": _summarize_by(matrix_rows, "forward_window"),
        "by_neutral_band": _summarize_by(matrix_rows, "neutral_band"),
    }


def _validate_matrix_result(matrix_result: Mapping[str, Any]) -> list[str]:
    validation_errors: list[str] = []

    missing_fields = sorted(REQUIRED_MATRIX_RESULT_FIELDS - set(matrix_result.keys()))
    if missing_fields:
        validation_errors.append(
            f"matrix_result missing required fields: {missing_fields}"
        )

    if "matrix_rows" in matrix_result and not isinstance(
        matrix_result["matrix_rows"],
        list,
    ):
        validation_errors.append("matrix_result matrix_rows must be a list")

    if "summary" in matrix_result and not isinstance(
        matrix_result["summary"],
        Mapping,
    ):
        validation_errors.append("matrix_result summary must be a mapping")

    runner_status = matrix_result.get("runner_status")
    if runner_status is not None and runner_status not in {"completed", "blocked"}:
        validation_errors.append(
            f"matrix_result invalid runner_status: {runner_status}"
        )

    if "is_blocked" in matrix_result and not isinstance(
        matrix_result["is_blocked"],
        bool,
    ):
        validation_errors.append("matrix_result is_blocked must be a boolean")

    return validation_errors


def _summarize_by(
    matrix_rows: list[dict[str, Any]],
    group_field: str,
) -> dict[str, dict[str, Any]]:
    grouped_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in matrix_rows:
        grouped_rows[str(row.get(group_field))].append(row)

    return {
        group_key: _summarize_rows(rows)
        for group_key, rows in sorted(grouped_rows.items(), key=lambda item: item[0])
    }


def _summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    completed_rows = [
        row for row in rows if row.get("runner_status") == "completed"
    ]
    blocked_rows = [
        row for row in rows if row.get("runner_status") == "blocked"
    ]

    return {
        "run_count": len(rows),
        "completed_run_count": len(completed_rows),
        "blocked_run_count": len(blocked_rows),
        "avg_accepted_minus_rejected_avg_direction_adjusted_outcome": _average_metric(
            completed_rows,
            "accepted_minus_rejected_avg_direction_adjusted_outcome",
        ),
        "min_accepted_minus_rejected_avg_direction_adjusted_outcome": _min_metric(
            completed_rows,
            "accepted_minus_rejected_avg_direction_adjusted_outcome",
        ),
        "max_accepted_minus_rejected_avg_direction_adjusted_outcome": _max_metric(
            completed_rows,
            "accepted_minus_rejected_avg_direction_adjusted_outcome",
        ),
        "avg_accepted_minus_rejected_hit_rate": _average_metric(
            completed_rows,
            "accepted_minus_rejected_hit_rate",
        ),
        "positive_edge_run_count": sum(
            1
            for row in completed_rows
            if _as_float(
                row.get(
                    "accepted_minus_rejected_avg_direction_adjusted_outcome",
                    0.0,
                )
            )
            > 0
        ),
        "positive_hit_rate_edge_run_count": sum(
            1
            for row in completed_rows
            if _as_float(row.get("accepted_minus_rejected_hit_rate", 0.0)) > 0
        ),
    }


def _average_metric(rows: list[dict[str, Any]], metric: str) -> float:
    if not rows:
        return 0.0

    return _round(mean(_as_float(row.get(metric, 0.0)) for row in rows))


def _min_metric(rows: list[dict[str, Any]], metric: str) -> float:
    if not rows:
        return 0.0

    return _round(min(_as_float(row.get(metric, 0.0)) for row in rows))


def _max_metric(rows: list[dict[str, Any]], metric: str) -> float:
    if not rows:
        return 0.0

    return _round(max(_as_float(row.get(metric, 0.0)) for row in rows))


def _as_float(value: Any) -> float:
    return float(value or 0.0)


def _round(value: Any) -> float:
    return round(float(value), 10)
