from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from src.regime.regime_directional_policy import (
    build_signalforge_regime_directional_policy,
)
from src.regime.regime_directional_policy_file_writer import (
    write_regime_directional_policy_result,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build SignalForge regime directional policy from weekly regime artifacts."
    )

    parser.add_argument("--source", required=True, help="Path to weekly regime / market overlay JSON.")
    parser.add_argument("--output-dir", required=True, help="Directory for output artifacts.")

    args = parser.parse_args(argv)

    source_path = Path(args.source)
    if not source_path.exists():
        raise SystemExit(f"source file does not exist: {source_path}")

    source = _read_json(source_path)

    result = build_signalforge_regime_directional_policy(source)

    summary = write_regime_directional_policy_result(
        result=result,
        output_dir=args.output_dir,
    )

    summary_path = Path(summary["files"]["summary"])
    result_path = Path(summary["files"]["regime_directional_policy_result"])

    summary["file_summary"]["file_sizes"]["summary"] = (
        summary_path.stat().st_size if summary_path.exists() else 0
    )
    summary["file_summary"]["file_sizes"]["regime_directional_policy_result"] = (
        result_path.stat().st_size if result_path.exists() else 0
    )

    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, sort_keys=True, default=str))

    return 0 if result.get("status") in {"ready", "needs_review"} else 1


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
