from __future__ import annotations

import argparse
from collections.abc import Mapping
import json
import sys
from pathlib import Path
from typing import Any, Callable, Sequence

from src.signalforge.data_sources.market_price_history_import_file_writer import (
    write_signalforge_market_price_history_import_files,
)
from src.universe.universe import UniverseManager


CLI_SUMMARY_SCHEMA_VERSION = "signalforge_market_price_history_import_cli_summary.v1"
DEFAULT_CLI_SUMMARY_FILENAME = "signalforge_market_price_history_import_cli_summary.json"

WriterFunction = Callable[..., dict[str, Any]]


def main(
    argv: Sequence[str] | None = None,
    *,
    writer: WriterFunction = write_signalforge_market_price_history_import_files,
) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        source = _read_json(args.source)
    except FileNotFoundError:
        print(f"source file not found: {args.source}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as error:
        print(f"source file is not valid JSON: {error}", file=sys.stderr)
        return 2

    try:
        source = _with_cli_universe_symbols(source, args)
    except (FileNotFoundError, KeyError, TypeError, ValueError) as error:
        print(f"universe resolution failed: {error}", file=sys.stderr)
        return 2

    output_path = Path(args.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    writer_result = writer(source, output_dir=output_path)

    cli_summary_path = output_path / DEFAULT_CLI_SUMMARY_FILENAME
    cli_summary = _build_cli_summary(
        writer_result=writer_result,
        summary_path=cli_summary_path,
    )
    _write_json(cli_summary_path, cli_summary)

    print(json.dumps(cli_summary, indent=2, sort_keys=True))

    return 1 if cli_summary["status"] == "blocked" else 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Normalize local CSV/QuantConnect/manual market price rows into "
            "SignalForge market_price_history payloads. This command reads local "
            "JSON only. It does not call market-data vendors, QuantConnect, "
            "brokers, route orders, submit orders, model fills, perform live "
            "execution, model slippage, create automatic close/roll/defense "
            "orders, change strategy logic automatically, update parameters "
            "automatically, or pause strategies automatically."
        )
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Path to local JSON source containing quantconnect_history, market_price_history, price_rows, rows, payload, or flat fields.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where market price history import artifacts should be written.",
    )
    parser.add_argument(
        "--universe-config",
        default="config/universes.yaml",
        help="Path to SignalForge universes.yaml used by --universe or --watchlist.",
    )
    parser.add_argument(
        "--universe",
        action="append",
        default=[],
        help="Universe name from universes.yaml expected to be present in the imported price history. Can be repeated.",
    )
    parser.add_argument(
        "--watchlist",
        action="append",
        default=[],
        help="Watchlist name from universes.yaml expected to be present in the imported price history. Can be repeated.",
    )
    parser.add_argument(
        "--symbol",
        action="append",
        default=[],
        help="Additional expected symbol to enforce in the import coverage. Can be repeated.",
    )
    return parser


def _read_json(path: str) -> Any:
    with Path(path).open(encoding="utf-8") as file:
        return json.load(file)


def _with_cli_universe_symbols(source: Any, args: argparse.Namespace) -> Any:
    expected_symbols: set[str] = set()

    if args.universe or args.watchlist:
        manager = UniverseManager(args.universe_config)

        for universe in args.universe:
            expected_symbols.update(manager.get_universe(universe))

        for watchlist in args.watchlist:
            expected_symbols.update(manager.get_watchlist(watchlist))

    for symbol in args.symbol:
        cleaned = str(symbol).strip().upper()
        if cleaned:
            expected_symbols.add(cleaned)

    if not expected_symbols:
        return source

    if not isinstance(source, Mapping):
        raise TypeError("source must be a mapping when universe coverage is requested")

    enriched = dict(source)
    existing = enriched.get("universe_symbols")
    existing_symbols = []

    if isinstance(existing, list):
        existing_symbols = [str(item).strip().upper() for item in existing if str(item).strip()]

    enriched["universe_symbols"] = sorted(set(existing_symbols) | expected_symbols)
    enriched["universe_source"] = {
        "universes": list(args.universe),
        "watchlists": list(args.watchlist),
        "symbols": list(args.symbol),
        "universe_config": str(args.universe_config),
    }
    return enriched


def _build_cli_summary(
    *,
    writer_result: dict[str, Any],
    summary_path: Path,
) -> dict[str, Any]:
    summary = writer_result.get("summary", {})
    import_result = writer_result.get("import_result", {})

    return {
        "schema_version": CLI_SUMMARY_SCHEMA_VERSION,
        "operation_type": "signalforge_market_price_history_import_cli",
        "status": writer_result.get("status", "needs_review"),
        "output_dir": writer_result.get("output_dir"),
        "summary_path": str(summary_path),
        "files": writer_result.get("files", {}),
        "file_summary": writer_result.get("file_summary", {}),
        "contract": summary.get("contract"),
        "adapter_type": summary.get("adapter_type"),
        "source_kind": summary.get("source_kind"),
        "normalized_payload_summary": summary.get("normalized_payload_summary", {}),
        "price_history_summary": summary.get("price_history_summary", {}),
        "universe_symbol_coverage": summary.get("universe_symbol_coverage", {}),
        "validation_row_count": summary.get("validation_row_count"),
        "missing_required_field_count": summary.get("missing_required_field_count"),
        "missing_preferred_field_count": summary.get("missing_preferred_field_count"),
        "blocker_count": summary.get("blocker_count"),
        "warning_count": summary.get("warning_count"),
        "requires_manual_approval": import_result.get("requires_manual_approval") is True,
        "order_intent": import_result.get("order_intent"),
        "broker_order_id": import_result.get("broker_order_id"),
        "automatic_action": import_result.get("automatic_action"),
        "automatic_strategy_change": import_result.get("automatic_strategy_change"),
        "automatic_parameter_change": import_result.get("automatic_parameter_change"),
        "automatic_pause_action": import_result.get("automatic_pause_action"),
        "explicit_exclusions": list(writer_result.get("explicit_exclusions", [])),
    }


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

