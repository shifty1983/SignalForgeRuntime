from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from src.signalforge.engines.strategy_selection.contract_final_review_export import build_signalforge_contract_final_review_export
from src.signalforge.engines.strategy_selection.contract_final_review_export_file_writer import write_contract_final_review_export_result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build SignalForge contract final review export from contract candidate review export."
    )
    parser.add_argument(
        "--contract-candidate-review-export-source",
        required=True,
        help="Path to contract candidate review export JSON artifact.",
    )
    parser.add_argument("--output-dir", required=True, help="Directory for output artifacts.")
    parser.add_argument("--max-contract-final-review-items", type=int, default=25)

    args = parser.parse_args(argv)

    result = build_signalforge_contract_final_review_export(
        contract_candidate_review_export_source=_read_json(args.contract_candidate_review_export_source),
        max_contract_final_review_items=args.max_contract_final_review_items,
    )

    summary = write_contract_final_review_export_result(result, args.output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0


def _read_json(path_text: str) -> Any:
    path = Path(path_text)
    if not path.exists():
        raise SystemExit(f"input file does not exist: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    raise SystemExit(main())
