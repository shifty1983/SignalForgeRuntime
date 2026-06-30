from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any

from src.signalforge.engines.regime.fred_weekly_pipeline import build_signalforge_fred_weekly_regime_pipeline


DEFAULT_SOURCE = "artifacts/fred_regime_pipeline/signalforge_fred_regime_pipeline.json"
DEFAULT_OUTPUT_DIR = "artifacts/fred_historical_weekly_regime_pipeline"
DEFAULT_OUTPUT_FILE = "signalforge_fred_historical_weekly_regime_pipeline.json"
DEFAULT_ROWS_FILE = "signalforge_fred_historical_weekly_regime_rows.jsonl"
DEFAULT_SUMMARY_FILE = "signalforge_fred_historical_weekly_regime_pipeline_summary.json"

SCHEMA_VERSION = "signalforge_fred_historical_weekly_regime_pipeline.v1"
CLI_SCHEMA_VERSION = "signalforge_fred_historical_weekly_regime_pipeline_cli.v1"

EXPLICIT_EXCLUSIONS = [
    "broker_api_calls",
    "order_routing",
    "order_submission",
    "fills",
    "live_execution",
    "slippage_modeling",
    "automatic_close_orders",
    "automatic_roll_orders",
    "automatic_defense_orders",
    "automatic_strategy_changes",
    "automatic_parameter_changes",
    "automatic_pause_actions",
]


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    source_path = Path(args.source)
    source = _read_json(source_path)

    rows = _extract_regime_rows(source)
    rows = sorted(rows, key=lambda row: str(row.get("date") or ""))

    if not rows:
        result = _blocked_result(
            source_path=source_path,
            output_dir=Path(args.output_dir),
            reason="source regime_rows are required",
        )
        _write_outputs(result=result, rows=[], args=args)
        print(json.dumps(result["summary"], indent=2, sort_keys=True))
        return 1

    historical_rows: list[dict[str, Any]] = []
    blocked_items: list[dict[str, Any]] = []

    for index, row in enumerate(rows):
        as_of_date = str(row.get("date") or "")
        if not as_of_date:
            blocked_items.append({"index": index, "reason": "regime row missing date"})
            continue

        point_in_time_source = _point_in_time_source(
            source=source,
            regime_rows=rows[: index + 1],
        )

        weekly = build_signalforge_fred_weekly_regime_pipeline(
            point_in_time_source,
            periods=args.periods,
            inflation_yoy_periods=args.inflation_yoy_periods,
            weekly_lookback_days=args.weekly_lookback_days,
        )

        weekly_status = str(weekly.get("status") or "unknown")
        if weekly_status == "blocked":
            blocked_items.append(
                {
                    "index": index,
                    "as_of_date": as_of_date,
                    "blocked_reasons": list(_as_list(weekly.get("blocked_reasons"))),
                }
            )

        historical_rows.append(_row_from_weekly_result(index=index, weekly=weekly))

    status_counts = Counter(str(item.get("status") or "unknown") for item in historical_rows)
    label_counts = Counter(
        str(item.get("macro_regime_label") or "unknown") for item in historical_rows
    )
    planning_counts = Counter(
        str(item.get("weekly_planning_label") or "unknown") for item in historical_rows
    )

    ready_rows = [row for row in historical_rows if row.get("status") == "ready"]
    latest_ready = ready_rows[-1] if ready_rows else None

    status = "ready" if historical_rows and not blocked_items else "needs_review"
    if not historical_rows:
        status = "blocked"

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    result_path = output_dir / args.output_file
    rows_path = output_dir / args.rows_file
    summary_path = output_dir / args.summary_file

    result = {
        "artifact_type": "signalforge_fred_historical_weekly_regime_pipeline",
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "is_ready": status in {"ready", "needs_review"} and bool(ready_rows),
        "requires_manual_approval": True,
        "source_path": str(source_path),
        "source_artifact_type": source.get("artifact_type"),
        "source_status": source.get("status"),
        "source_regime_row_count": len(rows),
        "historical_weekly_row_count": len(historical_rows),
        "ready_weekly_row_count": len(ready_rows),
        "blocked_weekly_row_count": len(blocked_items),
        "latest_ready_weekly_regime_row": latest_ready,
        "status_counts": dict(sorted(status_counts.items())),
        "macro_regime_label_counts": dict(sorted(label_counts.items())),
        "weekly_planning_label_counts": dict(sorted(planning_counts.items())),
        "blocked_items": blocked_items,
        "historical_weekly_regime_rows": historical_rows,
        "paths": {
            "result_path": str(result_path),
            "rows_path": str(rows_path),
            "summary_path": str(summary_path),
        },
        "next_step": "historical_regime_date_map_or_regime_asset_options_alignment",
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }

    summary = _summary(result)
    result["summary"] = summary

    _write_json(result_path, result)
    _write_jsonl(rows_path, historical_rows)
    _write_json(summary_path, summary)

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if status != "blocked" else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a historical point-in-time weekly FRED regime artifact by "
            "running the existing weekly regime planner once per source regime row. "
            "Each iteration only receives regime rows through that as-of date, so it "
            "does not look ahead."
        )
    )
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--output-file", default=DEFAULT_OUTPUT_FILE)
    parser.add_argument("--rows-file", default=DEFAULT_ROWS_FILE)
    parser.add_argument("--summary-file", default=DEFAULT_SUMMARY_FILE)
    parser.add_argument("--periods", type=int, default=1)
    parser.add_argument("--inflation-yoy-periods", type=int, default=12)
    parser.add_argument("--weekly-lookback-days", type=int, default=7)
    return parser


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Source artifact not found: {path}")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"Source artifact must be a JSON object: {path}")
    return value


def _extract_regime_rows(source: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = source.get("regime_rows")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
        return []
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def _point_in_time_source(
    *,
    source: Mapping[str, Any],
    regime_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    output = deepcopy(dict(source))
    output["regime_rows"] = [dict(row) for row in regime_rows]
    output["regime_row_count"] = len(regime_rows)
    output["latest_date"] = regime_rows[-1].get("date") if regime_rows else None

    latest_ready = None
    for row in reversed(regime_rows):
        if row.get("regime_label"):
            latest_ready = dict(row)
            break
    output["latest_ready_regime_row"] = latest_ready
    return output


def _row_from_weekly_result(*, index: int, weekly: Mapping[str, Any]) -> dict[str, Any]:
    options_policy = weekly.get("latest_regime_options_policy")
    if not isinstance(options_policy, Mapping):
        options_policy = {}

    asset_policy = weekly.get("latest_regime_asset_class_policy")
    if not isinstance(asset_policy, Mapping):
        asset_policy = {}

    return {
        "artifact_type": "signalforge_fred_historical_weekly_regime_row",
        "row_index": index,
        "status": weekly.get("status"),
        "is_ready": weekly.get("is_ready"),
        "as_of_date": weekly.get("as_of_date"),
        "week_start_date": weekly.get("week_start_date"),
        "week_end_date": weekly.get("week_end_date"),
        "macro_regime_source_date": weekly.get("macro_regime_source_date"),
        "macro_base_selection_reason": weekly.get("macro_base_selection_reason"),
        "macro_regime_label": weekly.get("macro_regime_label"),
        "macro_regime": weekly.get("macro_regime"),
        "macro_regime_score": weekly.get("macro_regime_score"),
        "macro_regime_confidence": weekly.get("macro_regime_confidence"),
        "macro_regime_drivers": weekly.get("macro_regime_drivers"),
        "source_macro_regime_label": weekly.get("source_macro_regime_label"),
        "policy_regime_label": weekly.get("policy_regime_label"),
        "weekly_planning_label": weekly.get("weekly_planning_label"),
        "weekly_review_reasons": list(_as_list(weekly.get("weekly_review_reasons"))),
        "weekly_overlay_date": weekly.get("weekly_overlay_date"),
        "weekly_risk_environment": weekly.get("weekly_risk_environment"),
        "weekly_rates_regime": weekly.get("weekly_rates_regime"),
        "weekly_liquidity_regime": weekly.get("weekly_liquidity_regime"),
        "weekly_volatility_regime": weekly.get("weekly_volatility_regime"),
        "weekly_event_risk": weekly.get("weekly_event_risk"),
        "latest_options_policy_status": options_policy.get("status"),
        "latest_asset_class_policy_status": asset_policy.get("status"),
        "requires_manual_approval": weekly.get("requires_manual_approval"),
        "warning_count": len(_as_list(weekly.get("warnings"))),
        "blocked_reason_count": len(_as_list(weekly.get("blocked_reasons"))),
        "warnings": list(_as_list(weekly.get("warnings"))),
        "blocked_reasons": list(_as_list(weekly.get("blocked_reasons"))),
    }


def _blocked_result(*, source_path: Path, output_dir: Path, reason: str) -> dict[str, Any]:
    result_path = output_dir / DEFAULT_OUTPUT_FILE
    rows_path = output_dir / DEFAULT_ROWS_FILE
    summary_path = output_dir / DEFAULT_SUMMARY_FILE
    summary = {
        "schema_version": CLI_SCHEMA_VERSION,
        "operation_type": "signalforge_fred_historical_weekly_regime_pipeline_cli",
        "status": "blocked",
        "is_ready": False,
        "source_path": str(source_path),
        "historical_weekly_row_count": 0,
        "ready_weekly_row_count": 0,
        "blocked_weekly_row_count": 1,
        "blocked_reason_count": 1,
        "blocked_reasons": [reason],
        "paths": {
            "result_path": str(result_path),
            "rows_path": str(rows_path),
            "summary_path": str(summary_path),
        },
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }
    return {
        "artifact_type": "signalforge_fred_historical_weekly_regime_pipeline",
        "schema_version": SCHEMA_VERSION,
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "source_path": str(source_path),
        "historical_weekly_regime_rows": [],
        "blocked_items": [{"reason": reason}],
        "summary": summary,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _summary(result: Mapping[str, Any]) -> dict[str, Any]:
    latest = result.get("latest_ready_weekly_regime_row")
    if not isinstance(latest, Mapping):
        latest = {}

    return {
        "schema_version": CLI_SCHEMA_VERSION,
        "operation_type": "signalforge_fred_historical_weekly_regime_pipeline_cli",
        "status": result.get("status"),
        "is_ready": result.get("is_ready"),
        "source_path": result.get("source_path"),
        "source_artifact_type": result.get("source_artifact_type"),
        "source_status": result.get("source_status"),
        "source_regime_row_count": result.get("source_regime_row_count"),
        "historical_weekly_row_count": result.get("historical_weekly_row_count"),
        "ready_weekly_row_count": result.get("ready_weekly_row_count"),
        "blocked_weekly_row_count": result.get("blocked_weekly_row_count"),
        "latest_ready_as_of_date": latest.get("as_of_date"),
        "latest_ready_macro_regime_label": latest.get("macro_regime_label"),
        "latest_ready_policy_regime_label": latest.get("policy_regime_label"),
        "latest_ready_weekly_planning_label": latest.get("weekly_planning_label"),
        "latest_ready_weekly_risk_environment": latest.get("weekly_risk_environment"),
        "status_counts": result.get("status_counts"),
        "macro_regime_label_counts": result.get("macro_regime_label_counts"),
        "weekly_planning_label_counts": result.get("weekly_planning_label_counts"),
        "blocked_reason_count": len(_as_list(result.get("blocked_items"))),
        "paths": result.get("paths"),
        "next_step": result.get("next_step"),
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _write_outputs(*, result: dict[str, Any], rows: list[dict[str, Any]], args: argparse.Namespace) -> None:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / args.output_file, result)
    _write_jsonl(output_dir / args.rows_file, rows)
    _write_json(output_dir / args.summary_file, result["summary"])


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, sort_keys=True, default=str) + "\n")


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


if __name__ == "__main__":
    raise SystemExit(main())
