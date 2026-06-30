from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from src.signalforge.engines.behavior.asset_multi_horizon_behavior import (
    DEFAULT_HORIZONS,
    _build_symbol_behavior,
    _clean_horizons,
    _extract_price_rows,
    _normalize_price_row,
)
from src.signalforge.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS


HISTORICAL_MULTI_HORIZON_SCHEMA_VERSION = "signalforge_historical_asset_multi_horizon_behavior.v1"
DEFAULT_SOURCE = (
    "artifacts/qc_replay_5y_behavior_inputs/"
    "signalforge_qc_replay_market_price_behavior_input.json"
)
DEFAULT_OUTPUT_DIR = "artifacts/historical_asset_multi_horizon_behavior"


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    source_path = Path(args.source)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    source = _read_json(source_path)
    contract_source = _read_json(Path(args.contract_source)) if args.contract_source else None
    symbols = _merge_symbols(args.symbol, args.symbols)

    result = build_historical_asset_multi_horizon_behavior(
        source=source,
        source_path=str(source_path),
        contract_source=contract_source,
        date_mode=args.date_mode,
        start_date=args.start_date,
        end_date=args.end_date,
        symbols=symbols,
        horizons=_parse_horizons(args.horizons),
        annualization_factor=args.annualization_factor,
        positive_return_threshold=args.positive_return_threshold,
        negative_return_threshold=args.negative_return_threshold,
        max_dates=args.max_dates,
        output_dir=output_dir,
    )

    print(json.dumps(result["summary"], indent=2, sort_keys=True, default=str))
    return 0 if result["summary"].get("status") in {"ready", "needs_review"} else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build historical point-in-time multi-horizon asset behavior rows "
            "from QC 5Y market price history. This is the historical/as-of companion "
            "to asset_multi_horizon_behavior_cli, which only emits the latest snapshot."
        )
    )
    parser.add_argument("--source", default=DEFAULT_SOURCE, help="Market price behavior input JSON.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Directory for output artifacts.")
    parser.add_argument(
        "--date-mode",
        choices=("all_market_dates", "month_end_market_dates", "contract_quote_dates"),
        default="all_market_dates",
    )
    parser.add_argument("--contract-source", default=None)
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--symbol", action="append", default=[])
    parser.add_argument("--symbols", default=None)
    parser.add_argument("--horizons", default=",".join(str(item) for item in DEFAULT_HORIZONS))
    parser.add_argument("--annualization-factor", type=int, default=252)
    parser.add_argument("--positive-return-threshold", type=float, default=0.02)
    parser.add_argument("--negative-return-threshold", type=float, default=-0.02)
    parser.add_argument("--max-dates", type=int, default=None)
    return parser


def build_historical_asset_multi_horizon_behavior(
    *,
    source: Mapping[str, Any],
    source_path: str,
    contract_source: Mapping[str, Any] | None,
    date_mode: str,
    start_date: str | None,
    end_date: str | None,
    symbols: Sequence[str] | None,
    horizons: Sequence[int],
    annualization_factor: int,
    positive_return_threshold: float,
    negative_return_threshold: float,
    max_dates: int | None,
    output_dir: Path,
) -> dict[str, Any]:
    rows = _extract_price_rows(source)
    if not rows:
        return _write_blocked(output_dir=output_dir, reason="source contains no price rows", source_path=source_path)

    clean_horizons = _clean_horizons(horizons)
    if not clean_horizons:
        return _write_blocked(output_dir=output_dir, reason="at least one positive horizon is required", source_path=source_path)

    symbol_filter = _normalize_symbols(symbols)
    normalized_rows: list[dict[str, Any]] = []
    skipped_source_rows: list[dict[str, Any]] = []

    for row_index, row in enumerate(rows):
        normalized = _normalize_price_row(row)
        if normalized is None:
            skipped_source_rows.append({"row_index": row_index, "reason": "price row missing symbol, timestamp, or price"})
            continue
        if symbol_filter is not None and normalized["symbol"] not in symbol_filter:
            continue
        parsed = _parse_date(normalized.get("timestamp"))
        if parsed is None:
            skipped_source_rows.append({"row_index": row_index, "reason": "unparseable timestamp"})
            continue
        normalized["date"] = parsed.isoformat()
        normalized["date_value"] = parsed
        normalized_rows.append(normalized)

    if not normalized_rows:
        return _write_blocked(output_dir=output_dir, reason="no usable market price rows after normalization/filtering", source_path=source_path)

    normalized_rows.sort(key=lambda row: (row["date_value"], row["symbol"]))
    market_dates = sorted({row["date_value"] for row in normalized_rows})
    target_dates = _target_dates(
        date_mode=date_mode,
        market_dates=market_dates,
        contract_source=contract_source,
        start_date=start_date,
        end_date=end_date,
    )
    if max_dates is not None:
        target_dates = target_dates[: max(0, max_dates)]

    if not target_dates:
        return _write_blocked(output_dir=output_dir, reason="no target as-of dates selected", source_path=source_path)

    rows_path = output_dir / "signalforge_historical_asset_multi_horizon_behavior_rows.jsonl"
    result_path = output_dir / "signalforge_historical_asset_multi_horizon_behavior.json"
    summary_path = output_dir / "signalforge_historical_asset_multi_horizon_behavior_summary.json"

    rows_by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    row_index = 0
    emitted_count = 0
    skipped_asof_symbol_count = 0
    ready_dates: list[str] = []
    confirmation_counts: Counter[str] = Counter()
    trend_consistency_counts: Counter[str] = Counter()

    with rows_path.open("w", encoding="utf-8") as handle:
        for as_of_date in target_dates:
            while row_index < len(normalized_rows) and normalized_rows[row_index]["date_value"] <= as_of_date:
                row = dict(normalized_rows[row_index])
                row.pop("date_value", None)
                rows_by_symbol[row["symbol"]].append(row)
                row_index += 1

            emitted_this_date = 0
            for symbol in sorted(rows_by_symbol):
                history = rows_by_symbol[symbol]
                if len(history) <= max(clean_horizons):
                    skipped_asof_symbol_count += 1
                    continue

                try:
                    behavior = _build_symbol_behavior(
                        symbol=symbol,
                        history=history,
                        horizons=clean_horizons,
                        annualization_factor=annualization_factor,
                        positive_return_threshold=positive_return_threshold,
                        negative_return_threshold=negative_return_threshold,
                    )
                except ValueError:
                    skipped_asof_symbol_count += 1
                    continue
                behavior["artifact_type"] = "historical_asset_multi_horizon_behavior_row"
                behavior["schema_version"] = "signalforge_historical_asset_multi_horizon_behavior_row.v1"
                behavior["as_of_date"] = as_of_date.isoformat()
                behavior["historical_replay_mode"] = True
                behavior["source_artifact_type"] = source.get("artifact_type")
                behavior["source_status"] = source.get("status")
                behavior["source_price_rows_asof_count"] = sum(len(items) for items in rows_by_symbol.values())

                handle.write(json.dumps(behavior, sort_keys=True, default=str) + "\n")
                emitted_count += 1
                emitted_this_date += 1
                confirmation_counts[str(behavior.get("multi_horizon_confirmation") or "unknown")] += 1
                trend_consistency_counts[str(behavior.get("trend_consistency") or "unknown")] += 1

            if emitted_this_date:
                ready_dates.append(as_of_date.isoformat())

    warning_items = []
    if skipped_source_rows:
        warning_items.append({"reason": "some source price rows were skipped", "skipped_source_row_count": len(skipped_source_rows)})
    source_status = _clean_text(source.get("status"))
    if source_status not in {None, "ready"}:
        warning_items.append({"reason": "market price source is not ready", "source_status": source_status})

    status = "blocked" if emitted_count == 0 else ("needs_review" if warning_items else "ready")

    result = {
        "artifact_type": "signalforge_historical_asset_multi_horizon_behavior",
        "schema_version": HISTORICAL_MULTI_HORIZON_SCHEMA_VERSION,
        "status": status,
        "is_ready": status in {"ready", "needs_review"},
        "requires_manual_approval": True,
        "contract": "historical_asset_multi_horizon_behavior",
        "adapter_type": "historical_asset_multi_horizon_behavior_builder",
        "source_path": source_path,
        "source_artifact_type": source.get("artifact_type"),
        "source_status": source.get("status"),
        "date_mode": date_mode,
        "start_date": start_date,
        "end_date": end_date,
        "input_market_date_min": market_dates[0].isoformat() if market_dates else None,
        "input_market_date_max": market_dates[-1].isoformat() if market_dates else None,
        "target_as_of_date_count": len(target_dates),
        "target_as_of_date_min": target_dates[0].isoformat() if target_dates else None,
        "target_as_of_date_max": target_dates[-1].isoformat() if target_dates else None,
        "historical_asset_multi_horizon_behavior_row_count": emitted_count,
        "skipped_asof_symbol_count": skipped_asof_symbol_count,
        "selected_symbol_count": len({row["symbol"] for row in normalized_rows}),
        "source_price_row_count": len(normalized_rows),
        "skipped_source_row_count": len(skipped_source_rows),
        "ready_as_of_date_count": len(ready_dates),
        "first_ready_as_of_date": ready_dates[0] if ready_dates else None,
        "last_ready_as_of_date": ready_dates[-1] if ready_dates else None,
        "horizons": list(clean_horizons),
        "annualization_factor": annualization_factor,
        "positive_return_threshold": positive_return_threshold,
        "negative_return_threshold": negative_return_threshold,
        "confirmation_counts": dict(sorted(confirmation_counts.items())),
        "trend_consistency_counts": dict(sorted(trend_consistency_counts.items())),
        "files": {"result": str(result_path), "summary": str(summary_path), "rows": str(rows_path)},
        "blocker_items": [],
        "warning_items": warning_items,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }
    summary = _summary_from_result(result)
    result["summary"] = summary

    result_path.write_text(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return {"result": result, "summary": summary}


def _target_dates(*, date_mode: str, market_dates: Sequence[date], contract_source: Mapping[str, Any] | None, start_date: str | None, end_date: str | None) -> list[date]:
    start = _parse_date(start_date) if start_date else None
    end = _parse_date(end_date) if end_date else None
    if date_mode == "all_market_dates":
        dates = list(market_dates)
    elif date_mode == "month_end_market_dates":
        by_month: dict[tuple[int, int], date] = {}
        for item in market_dates:
            by_month[(item.year, item.month)] = item
        dates = sorted(by_month.values())
    elif date_mode == "contract_quote_dates":
        if contract_source is None:
            raise SystemExit("--contract-source is required when --date-mode contract_quote_dates")
        dates = _contract_quote_dates(contract_source)
    else:
        raise SystemExit(f"unsupported date mode: {date_mode}")
    if start is not None:
        dates = [item for item in dates if item >= start]
    if end is not None:
        dates = [item for item in dates if item <= end]
    return sorted(set(dates))


def _contract_quote_dates(source: Mapping[str, Any]) -> list[date]:
    rows = source.get("contract_outcome_snapshots") or source.get("rows") or []
    dates: set[date] = set()
    if isinstance(rows, Sequence) and not isinstance(rows, (str, bytes, bytearray)):
        for row in rows:
            if isinstance(row, Mapping):
                parsed = _parse_date(row.get("quote_date") or row.get("date"))
                if parsed is not None:
                    dates.add(parsed)
    return sorted(dates)


def _summary_from_result(result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "artifact_type": result.get("artifact_type"),
        "schema_version": result.get("schema_version"),
        "operation_type": "historical_asset_multi_horizon_behavior_cli",
        "status": result.get("status"),
        "is_ready": result.get("is_ready"),
        "source_path": result.get("source_path"),
        "source_artifact_type": result.get("source_artifact_type"),
        "source_status": result.get("source_status"),
        "date_mode": result.get("date_mode"),
        "input_market_date_min": result.get("input_market_date_min"),
        "input_market_date_max": result.get("input_market_date_max"),
        "target_as_of_date_count": result.get("target_as_of_date_count"),
        "target_as_of_date_min": result.get("target_as_of_date_min"),
        "target_as_of_date_max": result.get("target_as_of_date_max"),
        "ready_as_of_date_count": result.get("ready_as_of_date_count"),
        "first_ready_as_of_date": result.get("first_ready_as_of_date"),
        "last_ready_as_of_date": result.get("last_ready_as_of_date"),
        "selected_symbol_count": result.get("selected_symbol_count"),
        "source_price_row_count": result.get("source_price_row_count"),
        "historical_asset_multi_horizon_behavior_row_count": result.get("historical_asset_multi_horizon_behavior_row_count"),
        "skipped_asof_symbol_count": result.get("skipped_asof_symbol_count"),
        "skipped_source_row_count": result.get("skipped_source_row_count"),
        "confirmation_counts": result.get("confirmation_counts"),
        "trend_consistency_counts": result.get("trend_consistency_counts"),
        "blocker_count": len(result.get("blocker_items", [])),
        "warning_count": len(result.get("warning_items", [])),
        "files": dict(result.get("files", {})),
        "explicit_exclusions": list(result.get("explicit_exclusions", [])),
    }


def _write_blocked(*, output_dir: Path, reason: str, source_path: str) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / "signalforge_historical_asset_multi_horizon_behavior.json"
    summary_path = output_dir / "signalforge_historical_asset_multi_horizon_behavior_summary.json"
    rows_path = output_dir / "signalforge_historical_asset_multi_horizon_behavior_rows.jsonl"
    rows_path.write_text("", encoding="utf-8")
    result = {
        "artifact_type": "signalforge_historical_asset_multi_horizon_behavior",
        "schema_version": HISTORICAL_MULTI_HORIZON_SCHEMA_VERSION,
        "status": "blocked",
        "is_ready": False,
        "source_path": source_path,
        "files": {"result": str(result_path), "summary": str(summary_path), "rows": str(rows_path)},
        "blocker_items": [{"reason": reason}],
        "warning_items": [],
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }
    summary = _summary_from_result(result)
    result["summary"] = summary
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return {"result": result, "summary": summary}


def _read_json(path: Path) -> Any:
    if not path.exists():
        raise SystemExit(f"input file does not exist: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _parse_horizons(value: str | Sequence[int]) -> list[int]:
    if isinstance(value, str):
        return [int(item.strip()) for item in value.split(",") if item.strip()]
    return [int(item) for item in value]


def _parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def _merge_symbols(repeated_symbols: Sequence[str], comma_symbols: str | None) -> list[str] | None:
    merged: list[str] = []
    for symbol in repeated_symbols:
        cleaned = str(symbol).strip().upper()
        if cleaned:
            merged.append(cleaned)
    if comma_symbols:
        for symbol in comma_symbols.split(","):
            cleaned = symbol.strip().upper()
            if cleaned:
                merged.append(cleaned)
    unique = sorted(set(merged))
    return unique or None


def _normalize_symbols(symbols: Sequence[str] | None) -> set[str] | None:
    if not symbols:
        return None
    return {str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()}


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text.lower() if text else None


if __name__ == "__main__":
    raise SystemExit(main())
