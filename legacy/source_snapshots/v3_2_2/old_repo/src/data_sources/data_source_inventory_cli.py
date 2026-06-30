from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Sequence

from src.signalforge.data_sources.data_source_inventory_file_writer import (
    write_signalforge_data_source_inventory_files,
)


CLI_SUMMARY_SCHEMA_VERSION = "signalforge_data_source_inventory_cli_summary.v1"
DEFAULT_CLI_SUMMARY_FILENAME = "signalforge_data_source_inventory_cli_summary.json"

WriterFunction = Callable[..., dict[str, Any]]


def main(
    argv: Sequence[str] | None = None,
    *,
    writer: WriterFunction = write_signalforge_data_source_inventory_files,
) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        source = _read_source(args.source)
    except FileNotFoundError:
        print(f"source file not found: {args.source}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as error:
        print(f"source file is not valid JSON: {error}", file=sys.stderr)
        return 2

    output_path = Path(args.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    writer_result = writer(source, output_dir=output_path)

    cli_summary_path = output_path / DEFAULT_CLI_SUMMARY_FILENAME
    cli_summary = _build_cli_summary(writer_result=writer_result, summary_path=cli_summary_path)
    _write_json(cli_summary_path, cli_summary)

    print(json.dumps(cli_summary, indent=2, sort_keys=True))

    return 1 if cli_summary["status"] == "blocked" else 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Write the SignalForge data-source inventory artifact. This command "
            "does not call brokers, route orders, submit orders, model fills, "
            "perform live execution, model slippage, create automatic close/roll/"
            "defense orders, change strategy logic automatically, update parameters "
            "automatically, or pause strategies automatically."
        )
    )
    parser.add_argument(
        "--source",
        default=None,
        help=(
            "Optional JSON source containing resolved_decisions. If omitted, "
            "the default unresolved inventory is written."
        ),
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where data-source inventory artifacts should be written.",
    )
    return parser


def _read_source(path: str | None) -> Any:
    if path is None:
        return {}
    with Path(path).open(encoding="utf-8") as file:
        return json.load(file)


def _build_cli_summary(
    *,
    writer_result: dict[str, Any],
    summary_path: Path,
) -> dict[str, Any]:
    summary = writer_result.get("summary", {})
    inventory = writer_result.get("inventory", {})

    return {
        "schema_version": CLI_SUMMARY_SCHEMA_VERSION,
        "operation_type": "signalforge_data_source_inventory_cli",
        "status": writer_result.get("status", "needs_review"),
        "output_dir": writer_result.get("output_dir"),
        "summary_path": str(summary_path),
        "files": writer_result.get("files", {}),
        "file_summary": writer_result.get("file_summary", {}),
        "module_summary": summary.get("module_summary", {}),
        "category_summary": summary.get("category_summary", {}),
        "open_decision_count": summary.get("open_decision_count"),
        "adapter_backlog_count": summary.get("adapter_backlog_count"),
        "recommended_build_order": summary.get("recommended_build_order", []),
        "requires_manual_approval": inventory.get("requires_manual_approval") is True,
        "order_intent": inventory.get("order_intent"),
        "broker_order_id": inventory.get("broker_order_id"),
        "automatic_action": inventory.get("automatic_action"),
        "automatic_strategy_change": inventory.get("automatic_strategy_change"),
        "automatic_parameter_change": inventory.get("automatic_parameter_change"),
        "automatic_pause_action": inventory.get("automatic_pause_action"),
        "explicit_exclusions": list(writer_result.get("explicit_exclusions", [])),
    }


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

