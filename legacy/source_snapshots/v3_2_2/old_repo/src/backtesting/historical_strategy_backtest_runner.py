# src/backtesting/historical_strategy_backtest_runner.py

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

from src.backtesting.historical_outcome_attachment import (
    attach_historical_forward_returns,
)
from src.backtesting.historical_strategy_evaluation_runner import (
    run_historical_strategy_evaluation_operation,
)


OPERATION_TYPE = "historical_strategy_backtest"


def run_historical_strategy_backtest(
    candidate_rows: Iterable[Mapping[str, Any]],
    price_rows: Iterable[Mapping[str, Any]],
    *,
    forward_window: int = 1,
    neutral_band: float = 0.01,
    operation_name: str = OPERATION_TYPE,
    metadata: Mapping[str, Any] | None = None,
    log_path: str | Path | None = None,
) -> dict[str, Any]:
    candidates = [dict(row) for row in candidate_rows]
    prices = [dict(row) for row in price_rows]
    metadata_dict = dict(metadata or {})

    attachment_result = attach_historical_forward_returns(
        candidates,
        prices,
        forward_window=forward_window,
    )

    if attachment_result["is_blocked"]:
        return {
            "operation_type": OPERATION_TYPE,
            "operation_name": operation_name,
            "runner_status": "blocked",
            "is_blocked": True,
            "attachment_result": attachment_result,
            "evaluation_result": None,
            "downstream_status": "skipped",
            "blocked_reasons": list(attachment_result["validation_errors"]),
            "summary": {
                "candidate_count": len(candidates),
                "price_row_count": len(prices),
                "attached_candidate_count": 0,
                "evaluated_candidate_count": 0,
                "accepted_candidate_count": 0,
                "rejected_candidate_count": 0,
                "forward_window": forward_window,
                "neutral_band": neutral_band,
                "attachment_status": attachment_result["attachment_status"],
                "evaluation_status": "skipped",
                "health_status": "skipped",
                "log_status": "skipped",
            },
        }

    evaluation_result = run_historical_strategy_evaluation_operation(
        attachment_result["historical_candidate_rows"],
        neutral_band=neutral_band,
        operation_name=operation_name,
        metadata=metadata_dict,
        log_path=log_path,
    )

    is_blocked = bool(evaluation_result["is_blocked"])
    runner_status = "blocked" if is_blocked else "completed"

    health_report = evaluation_result["health_report"]
    log_result = evaluation_result["log_result"]

    return {
        "operation_type": OPERATION_TYPE,
        "operation_name": operation_name,
        "runner_status": runner_status,
        "is_blocked": is_blocked,
        "attachment_result": attachment_result,
        "evaluation_result": evaluation_result,
        "downstream_status": "completed",
        "blocked_reasons": list(health_report.get("blocked_reasons", [])),
        "summary": {
            "candidate_count": len(candidates),
            "price_row_count": len(prices),
            "attached_candidate_count": attachment_result["summary"][
                "attached_candidate_count"
            ],
            "evaluated_candidate_count": evaluation_result["summary"][
                "evaluated_candidate_count"
            ],
            "accepted_candidate_count": evaluation_result["summary"][
                "accepted_candidate_count"
            ],
            "rejected_candidate_count": evaluation_result["summary"][
                "rejected_candidate_count"
            ],
            "forward_window": forward_window,
            "neutral_band": neutral_band,
            "attachment_status": attachment_result["attachment_status"],
            "evaluation_status": evaluation_result["evaluation_report"][
                "evaluation_status"
            ],
            "health_status": health_report["health_status"],
            "log_status": log_result["log_status"],
        },
    }
