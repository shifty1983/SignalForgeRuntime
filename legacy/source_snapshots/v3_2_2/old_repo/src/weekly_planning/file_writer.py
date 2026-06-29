from __future__ import annotations

import json
from os import PathLike
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.weekly_planning.option_trade_plan_operation import (
    run_weekly_option_trade_plan_operation,
)


FILE_WRITER_SCHEMA_VERSION = "weekly_option_trade_plan_files.v1"
OPERATION_TYPE = "weekly_option_trade_plan_file_writer"

DEFAULT_FILENAMES = {
    "weekly_option_trade_plan": "weekly_option_trade_plan.json",
    "operation_result": "weekly_option_trade_plan_operation.json",
    "audit_report": "weekly_option_trade_plan_audit.json",
    "health_report": "weekly_option_trade_plan_health.json",
    "events": "weekly_option_trade_plan_events.json",
    "event_log": "weekly_option_trade_plan_operation.jsonl",
}


def write_weekly_option_trade_plan_operation_files(
    source: Any,
    *,
    output_dir: str | PathLike[str],
    plan_date: str | None = None,
    max_new_trades: int | None = None,
    max_candidates_per_symbol: int | None = None,
) -> dict[str, Any]:
    """
    Write weekly option trade plan operation artifacts to local JSON/JSONL files.

    This writer is a weekend-review artifact writer only. It does not call broker
    APIs, route orders, submit orders, model fills, perform live execution,
    model slippage, or generate maintenance/defense actions.
    """

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    source_args = _extract_source_args(
        source,
        plan_date=plan_date,
        max_new_trades=max_new_trades,
        max_candidates_per_symbol=max_candidates_per_symbol,
    )

    event_log_path = output_path / DEFAULT_FILENAMES["event_log"]
    operation_result = run_weekly_option_trade_plan_operation(
        source_args["option_strategy_candidate_results"],
        plan_date=source_args["plan_date"],
        portfolio_snapshot=source_args["portfolio_snapshot"],
        max_new_trades=source_args["max_new_trades"],
        max_candidates_per_symbol=source_args["max_candidates_per_symbol"],
        metadata=source_args["metadata"],
        event_log_path=event_log_path,
    )

    weekly_option_trade_plan = _as_mapping(
        operation_result.get("weekly_option_trade_plan")
    )
    audit_report = _as_mapping(operation_result.get("audit_report"))
    health_report = _as_mapping(operation_result.get("health_report"))
    events = _as_list(operation_result.get("events"))

    files = {
        "weekly_option_trade_plan": output_path
        / DEFAULT_FILENAMES["weekly_option_trade_plan"],
        "operation_result": output_path / DEFAULT_FILENAMES["operation_result"],
        "audit_report": output_path / DEFAULT_FILENAMES["audit_report"],
        "health_report": output_path / DEFAULT_FILENAMES["health_report"],
        "events": output_path / DEFAULT_FILENAMES["events"],
        "event_log": event_log_path,
    }

    _write_json(files["weekly_option_trade_plan"], weekly_option_trade_plan)
    _write_json(files["operation_result"], operation_result)
    _write_json(files["audit_report"], audit_report)
    _write_json(files["health_report"], health_report)
    _write_json(files["events"], events)

    file_summary = _build_file_summary(files)

    return {
        "schema_version": FILE_WRITER_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": operation_result.get("status", "needs_review"),
        "output_dir": str(output_path),
        "files": {key: str(path) for key, path in files.items()},
        "file_summary": file_summary,
        "source_summary": _build_source_summary(source_args),
        "operation_result": operation_result,
        "explicit_exclusions": list(operation_result.get("explicit_exclusions", [])),
    }


def _extract_source_args(
    source: Any,
    *,
    plan_date: str | None,
    max_new_trades: int | None,
    max_candidates_per_symbol: int | None,
) -> dict[str, Any]:
    if isinstance(source, Mapping):
        source_mapping = source
    else:
        source_mapping = {}

    source_plan_date = _string_or_none(plan_date) or _string_or_none(
        source_mapping.get("plan_date")
    )

    return {
        "option_strategy_candidate_results": _extract_candidate_results(
            source_mapping
        ),
        "plan_date": source_plan_date or "",
        "portfolio_snapshot": _optional_mapping(
            source_mapping.get("portfolio_snapshot")
        ),
        "max_new_trades": _optional_positive_int(
            max_new_trades,
            fallback=source_mapping.get("max_new_trades"),
        ),
        "max_candidates_per_symbol": _optional_positive_int(
            max_candidates_per_symbol,
            fallback=source_mapping.get("max_candidates_per_symbol"),
        ),
        "metadata": _metadata(source_mapping.get("metadata")),
    }


def _extract_candidate_results(source: Mapping[str, Any]) -> Any:
    for key in (
        "option_strategy_candidate_results",
        "candidate_results",
        "defined_risk_option_strategy_candidate_results",
    ):
        if key in source:
            return source.get(key)

    return None


def _metadata(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _optional_mapping(value: Any) -> Mapping[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return dict(value)
    return value


def _optional_positive_int(value: Any, *, fallback: Any) -> int | None:
    selected = value if value is not None else fallback
    if selected is None:
        return None

    try:
        return int(selected)
    except (TypeError, ValueError):
        return selected


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _build_file_summary(files: Mapping[str, Path]) -> dict[str, Any]:
    return {
        "file_count": len(files),
        "written_files": sorted(files.keys()),
        "missing_files": sorted(
            key for key, path in files.items() if not path.exists()
        ),
        "empty_files": sorted(
            key
            for key, path in files.items()
            if path.exists() and path.stat().st_size == 0
        ),
    }


def _build_source_summary(source_args: Mapping[str, Any]) -> dict[str, Any]:
    candidate_results = source_args.get("option_strategy_candidate_results")
    candidate_count = (
        len(candidate_results)
        if isinstance(candidate_results, Sequence)
        and not isinstance(candidate_results, (str, bytes))
        else 0
    )

    return {
        "plan_date": _string_or_none(source_args.get("plan_date")),
        "candidate_result_count": candidate_count,
        "has_portfolio_snapshot": isinstance(
            source_args.get("portfolio_snapshot"), Mapping
        ),
        "max_new_trades": source_args.get("max_new_trades"),
        "max_candidates_per_symbol": source_args.get("max_candidates_per_symbol"),
    }


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _string_or_none(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None

