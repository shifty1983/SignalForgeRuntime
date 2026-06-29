# src/backtesting/historical_strategy_backtest_matrix.py

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from src.backtesting.historical_strategy_backtest_runner import (
    run_historical_strategy_backtest,
)


OPERATION_TYPE = "historical_strategy_backtest_matrix"


def run_historical_strategy_backtest_matrix(
    candidate_rows: Iterable[Mapping[str, Any]],
    price_rows: Iterable[Mapping[str, Any]],
    *,
    forward_windows: Sequence[int] = (1, 5, 10),
    neutral_bands: Sequence[float] = (0.01,),
    operation_name: str = OPERATION_TYPE,
    metadata: Mapping[str, Any] | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    candidates = [dict(row) for row in candidate_rows]
    prices = [dict(row) for row in price_rows]
    metadata_dict = dict(metadata or {})

    validation_errors = _validate_matrix_inputs(
        forward_windows=forward_windows,
        neutral_bands=neutral_bands,
    )

    if validation_errors:
        return {
            "operation_type": OPERATION_TYPE,
            "operation_name": operation_name,
            "runner_status": "blocked",
            "is_blocked": True,
            "validation_errors": validation_errors,
            "matrix_rows": [],
            "backtest_results": [],
            "summary": {
                "candidate_count": len(candidates),
                "price_row_count": len(prices),
                "matrix_run_count": 0,
                "completed_run_count": 0,
                "blocked_run_count": 0,
                "best_run": None,
                "worst_run": None,
            },
        }

    matrix_rows: list[dict[str, Any]] = []
    backtest_results: list[dict[str, Any]] = []

    for forward_window in sorted(set(int(window) for window in forward_windows)):
        for neutral_band in sorted(set(float(band) for band in neutral_bands)):
            child_operation_name = (
                f"{operation_name}:fw={forward_window}:neutral_band={neutral_band}"
            )

            log_path = None
            if log_dir is not None:
                log_path = (
                    Path(log_dir)
                    / f"{_safe_file_name(child_operation_name)}.jsonl"
                )

            result = run_historical_strategy_backtest(
                candidates,
                prices,
                forward_window=forward_window,
                neutral_band=neutral_band,
                operation_name=child_operation_name,
                metadata={
                    **metadata_dict,
                    "matrix_forward_window": forward_window,
                    "matrix_neutral_band": neutral_band,
                },
                log_path=log_path,
            )

            backtest_results.append(result)

            matrix_rows.append(_build_matrix_row(result))

    completed_rows = [
        row for row in matrix_rows if row["runner_status"] == "completed"
    ]
    blocked_rows = [
        row for row in matrix_rows if row["runner_status"] == "blocked"
    ]

    best_run = _select_best_run(completed_rows)
    worst_run = _select_worst_run(completed_rows)

    runner_status = "blocked" if not completed_rows else "completed"

    return {
        "operation_type": OPERATION_TYPE,
        "operation_name": operation_name,
        "runner_status": runner_status,
        "is_blocked": not completed_rows,
        "validation_errors": [],
        "matrix_rows": matrix_rows,
        "backtest_results": backtest_results,
        "summary": {
            "candidate_count": len(candidates),
            "price_row_count": len(prices),
            "matrix_run_count": len(matrix_rows),
            "completed_run_count": len(completed_rows),
            "blocked_run_count": len(blocked_rows),
            "best_run": best_run,
            "worst_run": worst_run,
        },
    }


def _validate_matrix_inputs(
    *,
    forward_windows: Sequence[int],
    neutral_bands: Sequence[float],
) -> list[str]:
    validation_errors: list[str] = []

    if not forward_windows:
        validation_errors.append("forward_windows must not be empty")

    if not neutral_bands:
        validation_errors.append("neutral_bands must not be empty")

    for index, forward_window in enumerate(forward_windows):
        if not isinstance(forward_window, int):
            validation_errors.append(
                f"forward_windows[{index}] must be an integer"
            )
            continue

        if forward_window <= 0:
            validation_errors.append(
                f"forward_windows[{index}] must be greater than 0"
            )

    for index, neutral_band in enumerate(neutral_bands):
        try:
            numeric_neutral_band = float(neutral_band)
        except (TypeError, ValueError):
            validation_errors.append(
                f"neutral_bands[{index}] must be numeric"
            )
            continue

        if numeric_neutral_band < 0:
            validation_errors.append(
                f"neutral_bands[{index}] must be non-negative"
            )

    return validation_errors


def _build_matrix_row(backtest_result: Mapping[str, Any]) -> dict[str, Any]:
    summary = dict(backtest_result.get("summary", {}))

    evaluation_result = backtest_result.get("evaluation_result")

    accepted_vs_rejected = {}
    health_report = {}

    if evaluation_result is not None:
        operation_record = evaluation_result.get("operation_record", {})
        accepted_vs_rejected = dict(
            operation_record.get("accepted_vs_rejected", {})
        )
        health_report = dict(evaluation_result.get("health_report", {}))

    accepted_summary = accepted_vs_rejected.get("accepted", {})
    rejected_summary = accepted_vs_rejected.get("rejected", {})

    return {
        "operation_name": backtest_result.get("operation_name"),
        "runner_status": backtest_result.get("runner_status"),
        "is_blocked": bool(backtest_result.get("is_blocked")),
        "forward_window": summary.get("forward_window"),
        "neutral_band": summary.get("neutral_band"),
        "candidate_count": summary.get("candidate_count", 0),
        "price_row_count": summary.get("price_row_count", 0),
        "attached_candidate_count": summary.get("attached_candidate_count", 0),
        "evaluated_candidate_count": summary.get("evaluated_candidate_count", 0),
        "accepted_candidate_count": summary.get("accepted_candidate_count", 0),
        "rejected_candidate_count": summary.get("rejected_candidate_count", 0),
        "accepted_avg_direction_adjusted_outcome": _round(
            accepted_summary.get("avg_direction_adjusted_outcome", 0.0)
        ),
        "rejected_avg_direction_adjusted_outcome": _round(
            rejected_summary.get("avg_direction_adjusted_outcome", 0.0)
        ),
        "accepted_hit_rate": _round(accepted_summary.get("hit_rate", 0.0)),
        "rejected_hit_rate": _round(rejected_summary.get("hit_rate", 0.0)),
        "accepted_minus_rejected_avg_direction_adjusted_outcome": _round(
            accepted_vs_rejected.get(
                "accepted_minus_rejected_avg_direction_adjusted_outcome",
                0.0,
            )
        ),
        "accepted_minus_rejected_hit_rate": _round(
            accepted_vs_rejected.get(
                "accepted_minus_rejected_hit_rate",
                0.0,
            )
        ),
        "health_status": health_report.get(
            "health_status",
            summary.get("health_status", "unknown"),
        ),
        "blocked_reasons": list(backtest_result.get("blocked_reasons", [])),
    }


def _select_best_run(
    completed_rows: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not completed_rows:
        return None

    best = max(
        completed_rows,
        key=lambda row: (
            row["accepted_minus_rejected_avg_direction_adjusted_outcome"],
            row["accepted_minus_rejected_hit_rate"],
            row["accepted_avg_direction_adjusted_outcome"],
            -int(row["forward_window"]),
            -float(row["neutral_band"]),
        ),
    )

    return _compact_selected_run(best)


def _select_worst_run(
    completed_rows: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not completed_rows:
        return None

    worst = min(
        completed_rows,
        key=lambda row: (
            row["accepted_minus_rejected_avg_direction_adjusted_outcome"],
            row["accepted_minus_rejected_hit_rate"],
            row["accepted_avg_direction_adjusted_outcome"],
            -int(row["forward_window"]),
            -float(row["neutral_band"]),
        ),
    )

    return _compact_selected_run(worst)


def _compact_selected_run(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "operation_name": row["operation_name"],
        "forward_window": row["forward_window"],
        "neutral_band": row["neutral_band"],
        "accepted_minus_rejected_avg_direction_adjusted_outcome": row[
            "accepted_minus_rejected_avg_direction_adjusted_outcome"
        ],
        "accepted_minus_rejected_hit_rate": row[
            "accepted_minus_rejected_hit_rate"
        ],
        "health_status": row["health_status"],
    }


def _safe_file_name(value: str) -> str:
    return (
        value.replace(":", "_")
        .replace("=", "-")
        .replace("/", "_")
        .replace("\\", "_")
        .replace(".", "_")
    )


def _round(value: Any) -> float:
    return round(float(value), 10)
