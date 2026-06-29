from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from src.strategy_selection.contract_decision_review_audit import build_signalforge_contract_decision_review_audit
from src.strategy_selection.contract_decision_review_audit_file_writer import write_contract_decision_review_audit_result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build SignalForge contract decision review audit from contract final decision record."
    )
    parser.add_argument(
        "--contract-final-decision-record-source",
        required=True,
        help="Path to contract final decision record JSON artifact.",
    )
    parser.add_argument("--output-dir", required=True, help="Directory for output artifacts.")

    args = parser.parse_args(argv)

    result = build_signalforge_contract_decision_review_audit(
        contract_final_decision_record_source=_read_json(args.contract_final_decision_record_source),
    )

    summary = write_contract_decision_review_audit_result(result, args.output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0


def _read_json(path_text: str) -> Any:
    path = Path(path_text)
    if not path.exists():
        raise SystemExit(f"input file does not exist: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    raise SystemExit(main())
