from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from src.strategy_selection.contract_final_decision_record import build_signalforge_contract_final_decision_record
from src.strategy_selection.contract_final_decision_record_file_writer import write_contract_final_decision_record_result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build SignalForge contract final decision record from final contract review export and explicit decisions."
    )
    parser.add_argument(
        "--contract-final-review-source",
        required=True,
        help="Path to contract final review export JSON artifact.",
    )
    parser.add_argument(
        "--decision-source",
        required=True,
        help="Path to explicit contract final decision JSON file.",
    )
    parser.add_argument("--output-dir", required=True, help="Directory for output artifacts.")

    args = parser.parse_args(argv)

    result = build_signalforge_contract_final_decision_record(
        contract_final_review_source=_read_json(args.contract_final_review_source),
        decision_source=_read_json(args.decision_source),
    )

    summary = write_contract_final_decision_record_result(result, args.output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0


def _read_json(path_text: str) -> Any:
    path = Path(path_text)
    if not path.exists():
        raise SystemExit(f"input file does not exist: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    raise SystemExit(main())
