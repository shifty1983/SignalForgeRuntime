from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from src.signalforge.engines.behavior.asset_directional_stance import (
    build_signalforge_asset_directional_stance,
)
from src.signalforge.engines.behavior.asset_directional_stance_file_writer import (
    write_asset_directional_stance_result,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build SignalForge instrument directional stance from asset behavior "
            "selection and regime directional policy artifacts."
        )
    )

    parser.add_argument(
        "--asset-behavior-selection",
        required=True,
        help="Path to signalforge_asset_behavior_selection.json.",
    )
    parser.add_argument(
        "--regime-directional-policy",
        required=True,
        help="Path to signalforge_regime_directional_policy.json.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory for output artifacts.",
    )
    parser.add_argument(
        "--symbol",
        action="append",
        default=[],
        help="Optional symbol filter. Can be repeated.",
    )
    parser.add_argument(
        "--symbols",
        default=None,
        help="Optional comma-separated symbol filter.",
    )

    args = parser.parse_args(argv)

    asset_behavior_selection_path = Path(args.asset_behavior_selection)
    regime_directional_policy_path = Path(args.regime_directional_policy)

    if not asset_behavior_selection_path.exists():
        raise SystemExit(
            f"asset behavior selection file does not exist: {asset_behavior_selection_path}"
        )

    if not regime_directional_policy_path.exists():
        raise SystemExit(
            f"regime directional policy file does not exist: {regime_directional_policy_path}"
        )

    asset_behavior_selection = _read_json(asset_behavior_selection_path)
    regime_directional_policy = _read_json(regime_directional_policy_path)
    symbols = _merge_symbols(args.symbol, args.symbols)

    result = build_signalforge_asset_directional_stance(
        asset_behavior_selection,
        regime_directional_policy,
        symbols=symbols,
    )

    summary = write_asset_directional_stance_result(
        result=result,
        output_dir=args.output_dir,
    )

    summary_path = Path(summary["files"]["summary"])
    result_path = Path(summary["files"]["asset_directional_stance_result"])

    summary["file_summary"]["file_sizes"]["summary"] = (
        summary_path.stat().st_size if summary_path.exists() else 0
    )
    summary["file_summary"]["file_sizes"]["asset_directional_stance_result"] = (
        result_path.stat().st_size if result_path.exists() else 0
    )

    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, sort_keys=True, default=str))

    return 0 if result.get("status") in {"ready", "needs_review"} else 1


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _merge_symbols(
    repeated_symbols: Sequence[str],
    comma_symbols: str | None,
) -> list[str] | None:
    merged: list[str] = []

    for symbol in repeated_symbols:
        cleaned = str(symbol).strip().upper()
        if cleaned:
            merged.append(cleaned)

    if comma_symbols:
        for symbol in comma_symbols.split(","):
            cleaned = symbol.strip().upper()
            if cleaned:
                merged.append(cleaned)

    unique = sorted(set(merged))
    return unique or None


if __name__ == "__main__":
    raise SystemExit(main())
