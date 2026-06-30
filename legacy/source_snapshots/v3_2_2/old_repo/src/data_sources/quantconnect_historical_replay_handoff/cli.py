from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from src.signalforge.data_sources.quantconnect_historical_replay_handoff.file_writer import (
    write_quantconnect_historical_replay_handoff_result,
)
from src.signalforge.data_sources.quantconnect_historical_replay_handoff.handoff import (
    DEFAULT_OUTCOME_HORIZONS,
    build_signalforge_quantconnect_historical_replay_handoff,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a SignalForge QuantConnect historical replay handoff manifest."
    )
    parser.add_argument(
        "--position-maintenance-policy-source",
        required=True,
        help="Path to SignalForge position maintenance policy JSON artifact.",
    )
    parser.add_argument("--start", required=True, help="Replay start date in YYYY-MM-DD format.")
    parser.add_argument("--end", required=True, help="Replay end date in YYYY-MM-DD format.")
    parser.add_argument("--output-dir", required=True, help="Directory for output artifacts.")
    parser.add_argument("--benchmark-symbol", default="SPY")
    parser.add_argument("--resolution", default="Daily")
    parser.add_argument("--min-dte", type=int, default=7)
    parser.add_argument("--max-dte", type=int, default=90)
    parser.add_argument("--moneyness-lower-bound", type=float, default=0.80)
    parser.add_argument("--moneyness-upper-bound", type=float, default=1.20)
    parser.add_argument("--max-spread-pct", type=float, default=0.15)
    parser.add_argument("--min-open-interest", type=int, default=100)
    parser.add_argument("--min-volume", type=int, default=1)
    parser.add_argument(
        "--outcome-horizons",
        default=",".join(str(value) for value in DEFAULT_OUTCOME_HORIZONS),
        help="Comma-separated outcome horizons in days, e.g. 1,5,10,21,45.",
    )
    parser.add_argument("--object-store-prefix", default="signalforge/historical_replay")
    parser.add_argument("--lean-project-name", default="SignalForgeHistoricalReplayHandoff")
    parser.add_argument("--smoke", action="store_true")

    args = parser.parse_args(argv)

    result = build_signalforge_quantconnect_historical_replay_handoff(
        position_maintenance_policy_source=_read_json(args.position_maintenance_policy_source),
        start=args.start,
        end=args.end,
        benchmark_symbol=args.benchmark_symbol,
        resolution=args.resolution,
        min_dte=args.min_dte,
        max_dte=args.max_dte,
        moneyness_lower_bound=args.moneyness_lower_bound,
        moneyness_upper_bound=args.moneyness_upper_bound,
        max_spread_pct=args.max_spread_pct,
        min_open_interest=args.min_open_interest,
        min_volume=args.min_volume,
        outcome_horizons=_parse_horizons(args.outcome_horizons),
        object_store_prefix=args.object_store_prefix,
        lean_project_name=args.lean_project_name,
        smoke=args.smoke,
    )

    summary = write_quantconnect_historical_replay_handoff_result(result, args.output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0 if result.get("is_ready") else 1


def _read_json(path_text: str) -> Any:
    path = Path(path_text)
    if not path.exists():
        raise SystemExit(f"input file does not exist: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _parse_horizons(value: str) -> list[int]:
    values: list[int] = []
    for part in str(value or "").split(","):
        text = part.strip()
        if not text:
            continue
        values.append(int(text))
    return values


if __name__ == "__main__":
    raise SystemExit(main())
