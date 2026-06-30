from __future__ import annotations

import argparse
import json
from pathlib import Path

from signalforge.backtesting.historical_strategy_family_eligibility_enrichment import (
    build_historical_strategy_family_eligibility_enrichment_artifact,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enrich historical decision rows with regime/asset/options alignment and strategy-family eligibility."
    )
    parser.add_argument("--decision-rows", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--include-engine-artifacts",
        action="store_true",
        help="Embed full per-row alignment and eligibility artifacts for debugging. Usually omit this.",
    )

    args = parser.parse_args()

    summary = build_historical_strategy_family_eligibility_enrichment_artifact(
        decision_rows_path=Path(args.decision_rows),
        output_dir=Path(args.output_dir),
        include_engine_artifacts=bool(args.include_engine_artifacts),
    )

    print(json.dumps(summary, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
