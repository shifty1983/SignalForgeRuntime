from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from src.signalforge.engines.strategy_selection.strategy_family_eligibility import (
    build_signalforge_strategy_family_eligibility,
)
from src.signalforge.engines.strategy_selection.strategy_family_eligibility_file_writer import (
    write_strategy_family_eligibility_result,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build SignalForge strategy family eligibility from regime/asset/options alignment."
    )
    parser.add_argument(
        "--alignment-source",
        required=True,
        help="Path to regime + asset + options alignment JSON artifact.",
    )
    parser.add_argument("--output-dir", required=True, help="Directory for output artifacts.")

    args = parser.parse_args(argv)

    result = build_signalforge_strategy_family_eligibility(
        alignment_source=_read_json(args.alignment_source),
    )

    summary = write_strategy_family_eligibility_result(result, args.output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0


def _read_json(path_text: str) -> Any:
    path = Path(path_text)
    if not path.exists():
        raise SystemExit(f"input file does not exist: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    raise SystemExit(main())



