from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from src.signalforge.engines.options.options_behavior_orats_gap_review import (
    build_signalforge_options_behavior_orats_gap_review,
)
from src.signalforge.engines.options.options_behavior_orats_gap_review_file_writer import (
    write_options_behavior_orats_gap_review_result,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build SignalForge Options Behavior ORATS-aligned gap review."
    )
    parser.add_argument(
        "--option-source",
        help="Optional path to option rows/source JSON for field coverage analysis.",
    )
    parser.add_argument(
        "--signalforge-capabilities",
        help="Optional path to JSON declaring implemented Options Behavior capabilities.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory for output artifacts.",
    )
    parser.add_argument(
        "--include-single-name-event-premium",
        action="store_true",
        help="Treat event premium as in scope instead of deferred for ETF MVP.",
    )

    args = parser.parse_args(argv)

    option_source = _read_optional_json(args.option_source)
    signalforge_capabilities = _read_optional_json(args.signalforge_capabilities)

    result = build_signalforge_options_behavior_orats_gap_review(
        option_source,
        signalforge_capabilities=signalforge_capabilities,
        etf_first=not args.include_single_name_event_premium,
    )

    summary = write_options_behavior_orats_gap_review_result(
        result,
        args.output_dir,
    )

    print(json.dumps(summary, indent=2, sort_keys=True, default=str))

    return 0


def _read_optional_json(path_text: str | None) -> Any:
    if not path_text:
        return None

    path = Path(path_text)
    if not path.exists():
        raise SystemExit(f"input file does not exist: {path}")

    return json.loads(path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    raise SystemExit(main())

