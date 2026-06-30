from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from src.signalforge.engines.options.option_gamma_concentration import (
    DEFAULT_EXPIRATION_CLUSTER_SHARE_THRESHOLD,
    DEFAULT_LOW_TOTAL_GAMMA_THRESHOLD,
    DEFAULT_STRIKE_CLUSTER_SHARE_THRESHOLD,
    build_signalforge_option_gamma_concentration,
)
from src.signalforge.engines.options.option_gamma_concentration_file_writer import (
    write_option_gamma_concentration_result,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build SignalForge option gamma concentration behavior classifications."
    )
    parser.add_argument(
        "--option-source",
        required=True,
        help="Path to option rows JSON.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory for output artifacts.",
    )
    parser.add_argument(
        "--strike-cluster-share-threshold",
        type=float,
        default=DEFAULT_STRIKE_CLUSTER_SHARE_THRESHOLD,
        help="Minimum share of gamma weight at one strike to flag strike clustering.",
    )
    parser.add_argument(
        "--expiration-cluster-share-threshold",
        type=float,
        default=DEFAULT_EXPIRATION_CLUSTER_SHARE_THRESHOLD,
        help="Minimum share of gamma weight at one expiration to flag expiration clustering.",
    )
    parser.add_argument(
        "--low-total-gamma-threshold",
        type=float,
        default=DEFAULT_LOW_TOTAL_GAMMA_THRESHOLD,
        help="Total gamma-weight threshold below which gamma is classified as low.",
    )

    args = parser.parse_args(argv)

    option_source = _read_json(args.option_source)
    result = build_signalforge_option_gamma_concentration(
        option_source,
        strike_cluster_share_threshold=args.strike_cluster_share_threshold,
        expiration_cluster_share_threshold=args.expiration_cluster_share_threshold,
        low_total_gamma_threshold=args.low_total_gamma_threshold,
    )

    summary = write_option_gamma_concentration_result(result, args.output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))

    return 0


def _read_json(path_text: str) -> Any:
    path = Path(path_text)
    if not path.exists():
        raise SystemExit(f"input file does not exist: {path}")

    return json.loads(path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    raise SystemExit(main())
