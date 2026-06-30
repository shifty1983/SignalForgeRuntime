from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from signalforge.engines.behavior.asset_behavior_selection import (
    build_signalforge_asset_behavior_selection,
)
from signalforge.engines.behavior.asset_behavior_selection_file_writer import (
    write_asset_behavior_selection_result,
)
from signalforge.engines.behavior.universe_asset_class_map import (
    load_asset_class_map_from_universe_config,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build SignalForge asset behavior selection from asset behavior artifacts."
    )

    parser.add_argument("--source", required=True, help="Path to asset behavior JSON.")
    parser.add_argument("--output-dir", required=True, help="Directory for output artifacts.")
    parser.add_argument(
        "--regime-source",
        default=None,
        help="Optional path to weekly regime / market overlay JSON.",
    )
    parser.add_argument(
        "--universe-config",
        default=None,
        help="Optional config/universes.yaml path used to derive symbol asset classes.",
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
    parser.add_argument(
        "--asset-class",
        action="append",
        default=[],
        help="Optional symbol asset-class mapping like SPY=equities. Can be repeated.",
    )
    parser.add_argument(
        "--asset-class-map",
        default=None,
        help="Optional JSON file containing {symbol: asset_class}.",
    )

    args = parser.parse_args(argv)

    source_path = Path(args.source)
    if not source_path.exists():
        raise SystemExit(f"source file does not exist: {source_path}")

    asset_behavior_source = _read_json(source_path)
    regime_source = _read_optional_json(args.regime_source)
    symbols = _merge_symbols(args.symbol, args.symbols)
    asset_class_by_symbol = _load_asset_class_map(
        universe_config=args.universe_config,
        path=args.asset_class_map,
        repeated_pairs=args.asset_class,
    )

    result = build_signalforge_asset_behavior_selection(
        asset_behavior_source,
        regime_source=regime_source,
        asset_class_by_symbol=asset_class_by_symbol,
        symbols=symbols,
    )

    summary = write_asset_behavior_selection_result(
        result=result,
        output_dir=args.output_dir,
    )

    summary_path = Path(summary["files"]["summary"])
    result_path = Path(summary["files"]["selection_result"])

    summary["file_summary"]["file_sizes"]["summary"] = (
        summary_path.stat().st_size if summary_path.exists() else 0
    )
    summary["file_summary"]["file_sizes"]["selection_result"] = (
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


def _read_optional_json(path_text: str | None) -> Any | None:
    if not path_text:
        return None

    path = Path(path_text)
    if not path.exists():
        raise SystemExit(f"regime source file does not exist: {path}")

    return _read_json(path)


def _merge_symbols(repeated_symbols: Sequence[str], comma_symbols: str | None) -> list[str] | None:
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


def _load_asset_class_map(
    *,
    universe_config: str | None,
    path: str | None,
    repeated_pairs: Sequence[str],
) -> dict[str, str]:
    mapping: dict[str, str] = {}

    if universe_config:
        mapping.update(load_asset_class_map_from_universe_config(universe_config))

    if path:
        map_path = Path(path)
        if not map_path.exists():
            raise SystemExit(f"asset class map file does not exist: {map_path}")

        loaded = _read_json(map_path)
        if not isinstance(loaded, dict):
            raise SystemExit("asset class map must be a JSON object")

        for symbol, asset_class in loaded.items():
            cleaned_symbol = str(symbol).strip().upper()
            cleaned_asset_class = str(asset_class).strip().lower()
            if cleaned_symbol and cleaned_asset_class:
                mapping[cleaned_symbol] = cleaned_asset_class

    for pair in repeated_pairs:
        if "=" not in pair:
            raise SystemExit(f"asset-class must use SYMBOL=asset_class format: {pair}")

        symbol, asset_class = pair.split("=", 1)
        cleaned_symbol = symbol.strip().upper()
        cleaned_asset_class = asset_class.strip().lower()

        if cleaned_symbol and cleaned_asset_class:
            mapping[cleaned_symbol] = cleaned_asset_class

    return mapping


if __name__ == "__main__":
    raise SystemExit(main())




