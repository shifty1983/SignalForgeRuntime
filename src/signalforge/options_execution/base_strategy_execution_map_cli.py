from __future__ import annotations

import argparse
from pathlib import Path

from src.signalforge.options_execution.base_strategy_execution_map import (
    load_json,
    validate_base_strategy_execution_map,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    config_path = Path(args.config)
    output_dir = Path(args.output_dir)

    config = load_json(config_path)
    summary = validate_base_strategy_execution_map(config)

    summary["input_path"] = str(config_path)
    summary["paths"] = {
        "summary_path": str(
            output_dir / "signalforge_options_execution_base_map_summary.json"
        )
    }

    write_json(
        output_dir / "signalforge_options_execution_base_map_summary.json",
        summary,
    )

    print(summary)
    return 0 if summary["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

