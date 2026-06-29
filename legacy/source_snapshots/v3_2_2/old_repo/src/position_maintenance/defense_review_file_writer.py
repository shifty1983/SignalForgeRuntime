from __future__ import annotations

import json
from os import PathLike
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.position_maintenance.defense_review_operation import (
    run_options_strategy_defense_review_operation,
)


FILE_WRITER_SCHEMA_VERSION = "options_strategy_defense_review_files.v1"
OPERATION_TYPE = "options_strategy_defense_review_file_writer"

DEFAULT_FILENAMES = {
    "options_strategy_defense_review": "options_strategy_defense_review.json",
    "operation_result": "options_strategy_defense_review_operation.json",
    "audit_report": "options_strategy_defense_review_audit.json",
    "health_report": "options_strategy_defense_review_health.json",
    "events": "options_strategy_defense_review_events.json",
    "event_log": "options_strategy_defense_review_operation.jsonl",
}


def write_options_strategy_defense_review_operation_files(
    source: Any,
    *,
    output_dir: str | PathLike[str],
    plan_date: str | None = None,
    market_regime: str | None = None,
    max_candidates_per_position: int | None = None,
) -> dict[str, Any]:
    """
    Write options-strategy defense review operation artifacts to local files.

    This writer is a manual review artifact writer only. It does not call broker
    APIs, route orders, submit orders, model fills, perform live execution,
    model slippage, or create automatic close/roll/defense orders.
    """

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    source_args = _extract_source_args(
        source,
        plan_date=plan_date,
        market_regime=market_regime,
        max_candidates_per_position=max_candidates_per_position,
    )

    event_log_path = output_path / DEFAULT_FILENAMES["event_log"]
    operation_result = run_options_strategy_defense_review_operation(
        source_args["positions"],
        plan_date=source_args["plan_date"],
        market_regime=source_args["market_regime"],
        regime_options_policy=source_args["regime_options_policy"],
        asset_behavior_options_policy=source_args["asset_behavior_options_policy"],
        option_behavior_options_policy=source_args["option_behavior_options_policy"],
        max_candidates_per_position=source_args["max_candidates_per_position"],
        metadata=source_args["metadata"],
        event_log_path=event_log_path,
    )

    defense_review = _as_mapping(
        operation_result.get("options_strategy_defense_review")
    )
    audit_report = _as_mapping(operation_result.get("audit_report"))
    health_report = _as_mapping(operation_result.get("health_report"))
    events = _as_list(operation_result.get("events"))

    files = {
        "options_strategy_defense_review": output_path
        / DEFAULT_FILENAMES["options_strategy_defense_review"],
        "operation_result": output_path / DEFAULT_FILENAMES["operation_result"],
        "audit_report": output_path / DEFAULT_FILENAMES["audit_report"],
        "health_report": output_path / DEFAULT_FILENAMES["health_report"],
        "events": output_path / DEFAULT_FILENAMES["events"],
        "event_log": event_log_path,
    }

    _write_json(files["options_strategy_defense_review"], defense_review)
    _write_json(files["operation_result"], operation_result)
    _write_json(files["audit_report"], audit_report)
    _write_json(files["health_report"], health_report)
    _write_json(files["events"], events)

    return {
        "schema_version": FILE_WRITER_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": operation_result.get("status", "needs_review"),
        "output_dir": str(output_path),
        "files": {key: str(path) for key, path in files.items()},
        "file_summary": _build_file_summary(files),
        "source_summary": _build_source_summary(source_args),
        "operation_result": operation_result,
        "explicit_exclusions": list(operation_result.get("explicit_exclusions", [])),
    }


def _extract_source_args(
    source: Any,
    *,
    plan_date: str | None,
    market_regime: str | None,
    max_candidates_per_position: int | None,
) -> dict[str, Any]:
    source_mapping = source if isinstance(source, Mapping) else {}

    source_plan_date = _string_or_none(plan_date) or _string_or_none(
        source_mapping.get("plan_date")
    )
    source_market_regime = _string_or_none(market_regime) or _string_or_none(
        source_mapping.get("market_regime")
    )

    return {
        "positions": _extract_positions(source_mapping),
        "plan_date": source_plan_date or "",
        "market_regime": source_market_regime,
        "regime_options_policy": _optional_mapping(
            source_mapping.get("regime_options_policy")
        ),
        "asset_behavior_options_policy": _optional_mapping(
            source_mapping.get("asset_behavior_options_policy")
        ),
        "option_behavior_options_policy": _optional_mapping(
            source_mapping.get("option_behavior_options_policy")
        ),
        "max_candidates_per_position": _optional_non_negative_int(
            max_candidates_per_position,
            fallback=source_mapping.get("max_candidates_per_position"),
        ),
        "metadata": _metadata(source_mapping.get("metadata")),
    }


def _extract_positions(source: Mapping[str, Any]) -> Any:
    for key in (
        "positions",
        "open_positions",
        "options_positions",
        "existing_positions",
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


def _optional_non_negative_int(value: Any, *, fallback: Any) -> int | None:
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
    positions = source_args.get("positions")
    position_count = (
        len(positions)
        if isinstance(positions, Sequence) and not isinstance(positions, (str, bytes))
        else 0
    )

    return {
        "plan_date": _string_or_none(source_args.get("plan_date")),
        "market_regime": _string_or_none(source_args.get("market_regime")),
        "position_count": position_count,
        "has_regime_options_policy": isinstance(
            source_args.get("regime_options_policy"), Mapping
        ),
        "has_asset_behavior_options_policy": isinstance(
            source_args.get("asset_behavior_options_policy"), Mapping
        ),
        "has_option_behavior_options_policy": isinstance(
            source_args.get("option_behavior_options_policy"), Mapping
        ),
        "max_candidates_per_position": source_args.get("max_candidates_per_position"),
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

