from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from src.signalforge.engines.alignment.regime_asset_options_alignment import (
    build_signalforge_regime_asset_options_alignment,
)
from src.signalforge.engines.alignment.regime_asset_options_alignment_file_writer import (
    write_regime_asset_options_alignment_result,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build SignalForge regime + asset + options policy alignment."
    )
    parser.add_argument("--regime-source", required=True, help="Path to regime JSON artifact.")
    parser.add_argument("--asset-behavior-source", required=True, help="Path to asset behavior JSON artifact.")
    parser.add_argument("--options-behavior-source", required=True, help="Path to unified Options Behavior JSON artifact.")
    parser.add_argument("--output-dir", required=True, help="Directory for output artifacts.")

    args = parser.parse_args(argv)

    result = build_signalforge_regime_asset_options_alignment(
        regime_source=_read_json(args.regime_source),
        asset_behavior_source=_read_json(args.asset_behavior_source),
        options_behavior_source=_read_json(args.options_behavior_source),
    )

    summary = write_regime_asset_options_alignment_result(result, args.output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0


def _read_json(path_text: str) -> Any:
    path = Path(path_text)
    if not path.exists():
        raise SystemExit(f"input file does not exist: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    raise SystemExit(main())

