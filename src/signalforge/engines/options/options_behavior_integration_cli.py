from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from src.signalforge.engines.options.options_behavior_integration import (
    build_signalforge_options_behavior_integration,
)
from src.signalforge.engines.options.options_behavior_integration_file_writer import (
    write_options_behavior_integration_result,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a unified SignalForge Options Behavior integration artifact."
    )
    parser.add_argument("--iv-history-source", required=True, help="Path to IV history snapshot JSON.")
    parser.add_argument("--iv-expansion-source", required=True, help="Path to IV expansion/contraction JSON.")
    parser.add_argument(
        "--volatility-risk-premium-source",
        required=True,
        help="Path to option volatility risk premium JSON.",
    )
    parser.add_argument("--gamma-concentration-source", required=True, help="Path to gamma concentration JSON.")
    parser.add_argument("--theta-sensitivity-source", required=True, help="Path to theta sensitivity JSON.")
    parser.add_argument(
        "--source-readiness-source",
        required=False,
        default=None,
        help="Optional path to option behavior source readiness JSON.",
    )
    parser.add_argument(
        "--supplemental-options-source",
        required=False,
        default=None,
        help="Optional path to supplemental skew/term/liquidity options behavior JSON.",
    )
    parser.add_argument("--output-dir", required=True, help="Directory for output artifacts.")

    args = parser.parse_args(argv)

    result = build_signalforge_options_behavior_integration(
        iv_history_source=_read_json(args.iv_history_source),
        iv_expansion_source=_read_json(args.iv_expansion_source),
        volatility_risk_premium_source=_read_json(args.volatility_risk_premium_source),
        gamma_concentration_source=_read_json(args.gamma_concentration_source),
        theta_sensitivity_source=_read_json(args.theta_sensitivity_source),
        source_readiness_source=_read_json(args.source_readiness_source)
        if args.source_readiness_source
        else None,
        supplemental_options_source=_read_json(args.supplemental_options_source)
        if args.supplemental_options_source
        else None,
    )

    summary = write_options_behavior_integration_result(result, args.output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0


def _read_json(path_text: str) -> Any:
    path = Path(path_text)
    if not path.exists():
        raise SystemExit(f"input file does not exist: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    raise SystemExit(main())


