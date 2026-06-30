from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.signalforge.data_sources.quantconnect_backtest_result_transport_decode.decoder import (
    decode_signalforge_backtest_result_transport,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Decode SignalForge replay files from QuantConnect backtest-read runtime statistics transport."
    )
    parser.add_argument("--backtest-read-source", required=True)
    parser.add_argument("--output-dir", required=True)

    args = parser.parse_args()

    source = _read_json(Path(args.backtest_read_source))

    result = decode_signalforge_backtest_result_transport(
        backtest_read_source=source,
        output_dir=args.output_dir,
    )

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("is_ready") else 1


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"backtest read source does not exist: {path}")

    value = json.loads(path.read_text(encoding="utf-8-sig"))

    if not isinstance(value, dict):
        raise SystemExit(f"backtest read source is not a JSON object: {path}")

    return value


if __name__ == "__main__":
    raise SystemExit(main())
