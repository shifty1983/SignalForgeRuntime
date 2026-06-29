from __future__ import annotations

import argparse
import json

from src.backtesting.historical_decision_rows_term_structure_enrichment_builder import (
    build_historical_decision_rows_term_structure_enrichment_artifact,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Enrich historical decision rows with option term-structure fields."
    )
    parser.add_argument("--decision-rows", required=True)
    parser.add_argument("--term-structure-rows", required=True)
    parser.add_argument("--output-dir", required=True)

    args = parser.parse_args()

    summary = build_historical_decision_rows_term_structure_enrichment_artifact(
        decision_rows_path=args.decision_rows,
        term_structure_rows_path=args.term_structure_rows,
        output_dir=args.output_dir,
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary.get("is_ready") else 1


if __name__ == "__main__":
    raise SystemExit(main())
