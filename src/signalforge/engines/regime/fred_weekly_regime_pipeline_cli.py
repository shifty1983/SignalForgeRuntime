from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from signalforge.engines.regime.fred_weekly_pipeline import build_signalforge_fred_weekly_regime_pipeline


DEFAULT_SOURCE = "artifacts/fred_regime_pipeline/signalforge_fred_regime_pipeline.json"
DEFAULT_OUTPUT_DIR = "artifacts/fred_weekly_regime_pipeline"
DEFAULT_OUTPUT_FILE = "signalforge_fred_weekly_regime_pipeline.json"
DEFAULT_SUMMARY_FILE = "signalforge_fred_weekly_regime_pipeline_summary.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the SignalForge FRED-backed weekly regime planning artifact."
    )
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--output-file", default=DEFAULT_OUTPUT_FILE)
    parser.add_argument("--summary-file", default=DEFAULT_SUMMARY_FILE)
    parser.add_argument("--periods", type=int, default=1)
    parser.add_argument("--inflation-yoy-periods", type=int, default=12)
    parser.add_argument("--weekly-lookback-days", type=int, default=7)
    args = parser.parse_args(argv)

    source_path = Path(args.source)
    if not source_path.exists():
        raise FileNotFoundError(f"Source artifact not found: {source_path}")

    source = json.loads(source_path.read_text(encoding="utf-8"))
    result = build_signalforge_fred_weekly_regime_pipeline(
        source,
        periods=args.periods,
        inflation_yoy_periods=args.inflation_yoy_periods,
        weekly_lookback_days=args.weekly_lookback_days,
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / args.output_file
    summary_path = output_dir / args.summary_file

    output_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    summary_path.write_text(
        json.dumps(_summary(result), indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "status": result.get("status"),
                "as_of_date": result.get("as_of_date"),
                "macro_regime_label": result.get("macro_regime_label"),
                "macro_regime": result.get("macro_regime"),
                "macro_regime_score": result.get("macro_regime_score"),
                "macro_regime_confidence": result.get("macro_regime_confidence"),
                "policy_regime_label": result.get("policy_regime_label"),
                "weekly_planning_label": result.get("weekly_planning_label"),
                "requires_manual_approval": result.get("requires_manual_approval"),
                "output_path": str(output_path),
                "summary_path": str(summary_path),
            },
            indent=2,
            sort_keys=True,
        )
    )

    return 0 if result.get("status") != "blocked" else 1


def _summary(result: dict[str, Any]) -> dict[str, Any]:
    options_policy = result.get("latest_regime_options_policy")
    if not isinstance(options_policy, dict):
        options_policy = {}

    asset_policy = result.get("latest_regime_asset_class_policy")
    if not isinstance(asset_policy, dict):
        asset_policy = {}

    return {
        "artifact_type": "signalforge_fred_weekly_regime_pipeline_summary",
        "source_artifact_type": result.get("artifact_type"),
        "schema_version": result.get("schema_version"),
        "status": result.get("status"),
        "is_ready": result.get("is_ready"),
        "as_of_date": result.get("as_of_date"),
        "week_start_date": result.get("week_start_date"),
        "week_end_date": result.get("week_end_date"),
        "monthly_macro_date": result.get("monthly_macro_date"),
        "macro_regime_label": result.get("macro_regime_label"),
        "macro_regime": result.get("macro_regime"),
        "macro_regime_score": result.get("macro_regime_score"),
        "macro_regime_confidence": result.get("macro_regime_confidence"),
        "macro_regime_drivers": result.get("macro_regime_drivers"),
        "policy_regime_label": result.get("policy_regime_label"),
        "weekly_planning_label": result.get("weekly_planning_label"),
        "weekly_risk_environment": result.get("weekly_risk_environment"),
        "weekly_volatility_regime": result.get("weekly_volatility_regime"),
        "weekly_liquidity_regime": result.get("weekly_liquidity_regime"),
        "weekly_rates_regime": result.get("weekly_rates_regime"),
        "latest_options_policy_status": options_policy.get("status"),
        "latest_asset_class_policy_status": asset_policy.get("status"),
        "requires_manual_approval": result.get("requires_manual_approval"),
        "monthly_macro_row_count": result.get("monthly_macro_row_count"),
        "source_row_count": result.get("source_row_count"),
        "normalized_row_count": result.get("normalized_row_count"),
        "warning_count": len(result.get("warnings") or []),
        "blocked_reason_count": len(result.get("blocked_reasons") or []),
    }


if __name__ == "__main__":
    raise SystemExit(main())




