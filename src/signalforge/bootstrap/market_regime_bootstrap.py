from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from signalforge.data.seed_bundle import resolve_seed_bundle_root


MARKET_SOURCE_RELATIVE_PATH = (
    "artifacts/qc_replay_5y_behavior_inputs/"
    "signalforge_qc_replay_option_behavior_input.jsonl"
)

REGIME_SOURCE_RELATIVE_PATH = (
    "artifacts/qc_replay_5y_historical_regime_date_map/"
    "signalforge_historical_regime_date_map.json"
)

DEFAULT_MARKET_OUTPUT = "data/runtime/market/underlying_daily.jsonl"
DEFAULT_REGIME_OUTPUT = "data/runtime/regime/regime_latest_snapshot.json"


@dataclass(frozen=True)
class MarketRegimeBootstrapSummary:
    seed_bundle_root: str | None
    market_source_path: str | None
    regime_source_path: str | None
    market_output_path: str
    regime_output_path: str
    is_ready: bool
    source_option_row_count: int
    market_row_count: int
    market_symbol_count: int
    market_date_count: int
    price_conflict_group_count: int
    regime_date_map_count: int
    latest_regime_quote_date: str | None
    latest_regime_state: str | None
    blocker_count: int
    blockers: tuple[str, ...]


def _read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            value = json.loads(line)
            if isinstance(value, dict):
                yield value


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    midpoint = len(ordered) // 2

    if len(ordered) % 2:
        return ordered[midpoint]

    return (ordered[midpoint - 1] + ordered[midpoint]) / 2.0


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _build_market_rows(source_path: Path) -> tuple[list[dict[str, Any]], int, int]:
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    source_row_count = 0

    for row in _read_jsonl(source_path):
        source_row_count += 1

        symbol = row.get("underlying_symbol")
        quote_date = row.get("quote_date")
        underlying_price = _safe_float(row.get("underlying_price"))

        if not symbol or not quote_date or underlying_price is None:
            continue

        key = (str(symbol), str(quote_date))
        group = groups.setdefault(
            key,
            {
                "symbol": str(symbol),
                "date": str(quote_date),
                "prices": [],
                "source_option_contract_row_count": 0,
                "option_contract_volume": 0.0,
            },
        )

        group["prices"].append(underlying_price)
        group["source_option_contract_row_count"] += 1

        volume = _safe_float(row.get("volume"))
        if volume is not None:
            group["option_contract_volume"] += volume

    market_rows: list[dict[str, Any]] = []
    price_conflict_group_count = 0

    for (symbol, quote_date), group in sorted(groups.items()):
        prices = group["prices"]

        if not prices:
            continue

        min_price = min(prices)
        max_price = max(prices)

        if abs(max_price - min_price) > 0.000001:
            price_conflict_group_count += 1

        market_rows.append(
            {
                "symbol": symbol,
                "date": quote_date,
                "close": round(_median(prices), 6),
                "source_price_min": round(min_price, 6),
                "source_price_max": round(max_price, 6),
                "source_option_contract_row_count": int(group["source_option_contract_row_count"]),
                "option_contract_volume": round(float(group["option_contract_volume"]), 6),
                "source": "signalforge_qc_replay_option_behavior_input.underlying_price",
            }
        )

    return market_rows, source_row_count, price_conflict_group_count


def _build_regime_snapshot(source_path: Path) -> tuple[dict[str, Any], int, str | None, str | None]:
    payload = json.loads(source_path.read_text(encoding="utf-8-sig"))
    items = payload.get("date_map_items") or []

    if not isinstance(items, list) or not items:
        return {}, 0, None, None

    latest = sorted(items, key=lambda item: str(item.get("quote_date") or ""))[-1]

    latest_quote_date = latest.get("quote_date")
    latest_regime_state = latest.get("regime_state")

    snapshot = {
        "contract": "regime_latest_snapshot",
        "source": REGIME_SOURCE_RELATIVE_PATH,
        "source_artifact_type": payload.get("artifact_type"),
        "source_schema_version": payload.get("schema_version"),
        "source_quote_date_count": payload.get("quote_date_count"),
        "source_mapped_quote_date_count": payload.get("mapped_quote_date_count"),
        "latest_quote_date": latest_quote_date,
        "latest_regime_date": latest.get("regime_date"),
        "latest_regime_state": latest_regime_state,
        "latest_risk_environment": latest.get("risk_environment"),
        "latest_macro_regime": latest.get("macro_regime"),
        "latest_macro_regime_label": latest.get("macro_regime_label"),
        "latest_policy_regime_label": latest.get("policy_regime_label"),
        "latest_volatility_regime": latest.get("volatility_regime"),
        "latest_weekly_planning_label": latest.get("weekly_planning_label"),
        "latest_weekly_context_status": latest.get("weekly_context_status"),
        "latest_item": latest,
    }

    return snapshot, len(items), str(latest_quote_date), str(latest_regime_state)


def build_market_regime_bootstrap(
    *,
    seed_bundle: str | Path | None = None,
    market_output_path: str | Path = DEFAULT_MARKET_OUTPUT,
    regime_output_path: str | Path = DEFAULT_REGIME_OUTPUT,
) -> MarketRegimeBootstrapSummary:
    seed_root = resolve_seed_bundle_root(seed_bundle)
    market_output = Path(market_output_path)
    regime_output = Path(regime_output_path)

    blockers: list[str] = []

    if seed_root is None:
        return MarketRegimeBootstrapSummary(
            seed_bundle_root=None,
            market_source_path=None,
            regime_source_path=None,
            market_output_path=str(market_output),
            regime_output_path=str(regime_output),
            is_ready=False,
            source_option_row_count=0,
            market_row_count=0,
            market_symbol_count=0,
            market_date_count=0,
            price_conflict_group_count=0,
            regime_date_map_count=0,
            latest_regime_quote_date=None,
            latest_regime_state=None,
            blocker_count=1,
            blockers=("seed_bundle_missing",),
        )

    market_source = seed_root / MARKET_SOURCE_RELATIVE_PATH
    regime_source = seed_root / REGIME_SOURCE_RELATIVE_PATH

    if not market_source.is_file():
        blockers.append("market_source_missing")

    if not regime_source.is_file():
        blockers.append("regime_source_missing")

    if blockers:
        return MarketRegimeBootstrapSummary(
            seed_bundle_root=str(seed_root),
            market_source_path=str(market_source),
            regime_source_path=str(regime_source),
            market_output_path=str(market_output),
            regime_output_path=str(regime_output),
            is_ready=False,
            source_option_row_count=0,
            market_row_count=0,
            market_symbol_count=0,
            market_date_count=0,
            price_conflict_group_count=0,
            regime_date_map_count=0,
            latest_regime_quote_date=None,
            latest_regime_state=None,
            blocker_count=len(blockers),
            blockers=tuple(blockers),
        )

    market_rows, source_option_row_count, price_conflict_group_count = _build_market_rows(market_source)
    regime_snapshot, regime_date_map_count, latest_regime_quote_date, latest_regime_state = _build_regime_snapshot(regime_source)

    if not market_rows:
        blockers.append("no_market_rows_written")

    if not regime_snapshot:
        blockers.append("no_regime_snapshot_written")

    market_output.parent.mkdir(parents=True, exist_ok=True)
    with market_output.open("w", encoding="utf-8") as handle:
        for row in market_rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    regime_output.parent.mkdir(parents=True, exist_ok=True)
    regime_output.write_text(json.dumps(regime_snapshot, indent=2, sort_keys=True), encoding="utf-8")

    return MarketRegimeBootstrapSummary(
        seed_bundle_root=str(seed_root),
        market_source_path=str(market_source),
        regime_source_path=str(regime_source),
        market_output_path=str(market_output),
        regime_output_path=str(regime_output),
        is_ready=not blockers,
        source_option_row_count=source_option_row_count,
        market_row_count=len(market_rows),
        market_symbol_count=len({row["symbol"] for row in market_rows}),
        market_date_count=len({row["date"] for row in market_rows}),
        price_conflict_group_count=price_conflict_group_count,
        regime_date_map_count=regime_date_map_count,
        latest_regime_quote_date=latest_regime_quote_date,
        latest_regime_state=latest_regime_state,
        blocker_count=len(blockers),
        blockers=tuple(blockers),
    )


def summary_to_dict(summary: MarketRegimeBootstrapSummary) -> dict[str, Any]:
    return asdict(summary)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap runtime market and regime files.")
    parser.add_argument("--seed-bundle", default=None)
    parser.add_argument("--market-output", default=DEFAULT_MARKET_OUTPUT)
    parser.add_argument("--regime-output", default=DEFAULT_REGIME_OUTPUT)
    parser.add_argument("--summary-output", default="artifacts/market_regime_bootstrap_summary.json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    summary = build_market_regime_bootstrap(
        seed_bundle=args.seed_bundle,
        market_output_path=args.market_output,
        regime_output_path=args.regime_output,
    )

    summary_path = Path(args.summary_output)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary_to_dict(summary), indent=2, sort_keys=True), encoding="utf-8")

    if args.json:
        print(json.dumps(summary_to_dict(summary), indent=2, sort_keys=True))
    else:
        print(f"is_ready: {summary.is_ready}")
        print(f"market_row_count: {summary.market_row_count}")
        print(f"market_symbol_count: {summary.market_symbol_count}")
        print(f"market_date_count: {summary.market_date_count}")
        print(f"regime_date_map_count: {summary.regime_date_map_count}")
        print(f"latest_regime_quote_date: {summary.latest_regime_quote_date}")
        print(f"latest_regime_state: {summary.latest_regime_state}")
        print(f"blocker_count: {summary.blocker_count}")

    return 0 if summary.is_ready else 2


if __name__ == "__main__":
    raise SystemExit(main())




