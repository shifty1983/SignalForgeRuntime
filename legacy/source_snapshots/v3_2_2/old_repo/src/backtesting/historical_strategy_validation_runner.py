# src/backtesting/historical_strategy_validation_runner.py

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from src.backtesting.historical_strategy_backtest_matrix import (
    run_historical_strategy_backtest_matrix,
)
from src.backtesting.historical_strategy_backtest_matrix_diagnostics import (
    evaluate_historical_strategy_backtest_matrix_diagnostics,
)


OPERATION_TYPE = "historical_strategy_validation"


def run_historical_strategy_validation(
    candidate_rows: Iterable[Mapping[str, Any]],
    price_rows: Iterable[Mapping[str, Any]],
    *,
    forward_windows: Sequence[int] = (1, 5, 10),
    neutral_bands: Sequence[float] = (0.01,),
    min_avg_outcome_edge: float = 0.0,
    min_hit_rate_edge: float = 0.0,
    require_all_runs_completed: bool = False,
    operation_name: str = OPERATION_TYPE,
    metadata: Mapping[str, Any] | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    candidates = [dict(row) for row in candidate_rows]
    prices = [dict(row) for row in price_rows]
    metadata_dict = dict(metadata or {})

    matrix_result = run_historical_strategy_backtest_matrix(
        candidates,
        prices,
        forward_windows=forward_windows,
        neutral_bands=neutral_bands,
        operation_name=f"{operation_name}:matrix",
        metadata={
            **metadata_dict,
            "parent_operation_type": OPERATION_TYPE,
            "parent_operation_name": operation_name,
        },
        log_dir=log_dir,
    )

    diagnostics_report = evaluate_historical_strategy_backtest_matrix_diagnostics(
        matrix_result,
        min_avg_outcome_edge=min_avg_outcome_edge,
        min_hit_rate_edge=min_hit_rate_edge,
        require_all_runs_completed=require_all_runs_completed,
    )

    validation_status = _derive_validation_status(diagnostics_report)
    is_blocked = validation_status == "blocked"
    is_validated = validation_status == "validated"

    return {
        "operation_type": OPERATION_TYPE,
        "operation_name": operation_name,
        "validation_status": validation_status,
        "is_validated": is_validated,
        "is_blocked": is_blocked,
        "matrix_result": matrix_result,
        "diagnostics_report": diagnostics_report,
        "blocked_reasons": list(diagnostics_report.get("blocked_reasons", [])),
        "warnings": list(diagnostics_report.get("warnings", [])),
        "summary": {
            "candidate_count": len(candidates),
            "price_row_count": len(prices),
            "forward_windows": list(forward_windows),
            "neutral_bands": [float(band) for band in neutral_bands],
            "min_avg_outcome_edge": round(float(min_avg_outcome_edge), 10),
            "min_hit_rate_edge": round(float(min_hit_rate_edge), 10),
            "require_all_runs_completed": require_all_runs_completed,
            "matrix_run_count": diagnostics_report["summary"][
                "matrix_run_count"
            ],
            "completed_run_count": diagnostics_report["summary"][
                "completed_run_count"
            ],
            "blocked_run_count": diagnostics_report["summary"][
                "blocked_run_count"
            ],
            "stable_run_count": diagnostics_report["summary"][
                "stable_run_count"
            ],
            "positive_edge_run_count": diagnostics_report["summary"][
                "positive_edge_run_count"
            ],
            "positive_hit_rate_edge_run_count": diagnostics_report["summary"][
                "positive_hit_rate_edge_run_count"
            ],
            "diagnostic_status": diagnostics_report["diagnostic_status"],
            "best_run": diagnostics_report["summary"].get("best_run"),
            "worst_run": diagnostics_report["summary"].get("worst_run"),
        },
    }


def _derive_validation_status(
    diagnostics_report: Mapping[str, Any],
) -> str:
    diagnostic_status = diagnostics_report.get("diagnostic_status")

    if diagnostic_status == "blocked":
        return "blocked"

    if diagnostic_status == "healthy":
        return "validated"

    return "needs_review"
