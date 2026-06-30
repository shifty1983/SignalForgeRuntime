from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

import polars as pl

from src.common.paths import raw_macro_dir
from src.signalforge.engines.regime.fred_pipeline import build_signalforge_fred_regime_pipeline


CLI_SUMMARY_SCHEMA_VERSION = "signalforge_fred_regime_pipeline_cli.v1"


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.source:
        source = _read_json(args.source)
    else:
        source = {"macro_rows": _read_macro_parquet_rows(Path(args.macro_dir) if args.macro_dir else raw_macro_dir() / args.source_name)}

    result = build_signalforge_fred_regime_pipeline(
        source,
        periods=args.periods,
        inflation_yoy_periods=args.inflation_yoy_periods,
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    result_path = output_dir / "signalforge_fred_regime_pipeline.json"
    summary_path = output_dir / "signalforge_fred_regime_pipeline_summary.json"

    summary = _summary(result=result, result_path=result_path, summary_path=summary_path)

    _write_json(result_path, result)
    _write_json(summary_path, summary)

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if result.get("status") == "blocked" else 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a SignalForge FRED macro regime artifact from local normalized "
            "FRED macro rows or local parquet files. This command does not call FRED, "
            "brokers, route orders, submit orders, model fills, perform live execution, "
            "model slippage, or create automatic strategy/parameter actions."
        )
    )
    parser.add_argument("--source", help="Optional local JSON containing macro_rows/fred_rows/rows/payload.")
    parser.add_argument(
        "--macro-dir",
        help="Optional macro parquet root. Defaults to data/raw/macro/fred when --source is omitted.",
    )
    parser.add_argument("--source-name", default="fred", help="Macro source folder name under data/raw/macro.")
    parser.add_argument("--output-dir", required=True, help="Directory for regime artifacts.")
    parser.add_argument("--periods", type=int, default=3, help="Lookback periods for macro momentum.")
    parser.add_argument("--inflation-yoy-periods", type=int, default=12, help="Lookback periods for inflation YoY calculation.")
    return parser


def _read_macro_parquet_rows(root: Path) -> list[dict[str, Any]]:
    if not root.exists():
        raise FileNotFoundError(f"Macro parquet directory not found: {root}")

    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.parquet")):
        df = pl.read_parquet(path)
        rows.extend(df.to_dicts())

    if not rows:
        raise ValueError(f"No macro parquet rows found under: {root}")

    return rows


def _summary(*, result: dict[str, Any], result_path: Path, summary_path: Path) -> dict[str, Any]:
    latest = result.get("latest_ready_regime_row") or {}
    policy = result.get("latest_regime_options_policy") or {}
    return {
        "schema_version": CLI_SUMMARY_SCHEMA_VERSION,
        "operation_type": "signalforge_fred_regime_pipeline_cli",
        "status": result.get("status"),
        "result_path": str(result_path),
        "summary_path": str(summary_path),
        "regime_row_count": result.get("regime_row_count", 0),
        "latest_date": result.get("latest_date"),
        "latest_ready_date": latest.get("date"),
        "latest_regime_label": latest.get("regime_label"),
        "latest_risk_environment": latest.get("risk_environment"),
        "latest_regime_risk_bias": latest.get("regime_risk_bias"),
        "latest_policy_status": policy.get("status"),
        "warning_count": len(result.get("warnings", [])),
        "blocked_reason_count": len(result.get("blocked_reasons", [])),
        "explicit_exclusions": list(result.get("explicit_exclusions", [])),
    }


def _read_json(path: str) -> Any:
    with Path(path).open(encoding="utf-8") as file:
        return json.load(file)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

