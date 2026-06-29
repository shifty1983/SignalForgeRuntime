from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REQUIRED_DRY_RUN_INPUT_PATTERNS = {
    "market_or_decision_source": [
        "data/**/*.json",
        "data/**/*.jsonl",
        "artifacts/**/*decision*.json",
        "artifacts/**/*decision*.jsonl",
    ],
    "strategy_candidate_or_selection_source": [
        "artifacts/**/*candidate*.json",
        "artifacts/**/*candidate*.jsonl",
        "artifacts/**/*selection*.json",
        "artifacts/**/*selection*.jsonl",
    ],
    "expectancy_source": [
        "artifacts/**/*expectancy*.json",
        "artifacts/**/*expectancy*.jsonl",
    ],
    "option_or_leg_source": [
        "artifacts/**/*option*.json",
        "artifacts/**/*option*.jsonl",
        "artifacts/**/*leg*.json",
        "artifacts/**/*leg*.jsonl",
    ],
    "portfolio_or_position_source": [
        "artifacts/**/*portfolio*.json",
        "artifacts/**/*portfolio*.jsonl",
        "artifacts/**/*position*.json",
        "artifacts/**/*position*.jsonl",
    ],
}


def _matches(patterns: list[str]) -> list[str]:
    found: list[str] = []
    for pattern in patterns:
        for path in Path(".").glob(pattern):
            if path.is_file():
                found.append(str(path))
    return sorted(set(found))


def build_dry_run_input_availability_manifest() -> dict[str, Any]:
    categories: dict[str, Any] = {}

    for category, patterns in REQUIRED_DRY_RUN_INPUT_PATTERNS.items():
        matches = _matches(patterns)
        categories[category] = {
            "patterns": patterns,
            "match_count": len(matches),
            "sample_matches": matches[:25],
            "is_available": len(matches) > 0,
        }

    blockers = [
        f"{category}_missing"
        for category, result in categories.items()
        if not result["is_available"]
    ]

    return {
        "adapter_type": "migrated_workflow_dry_run_input_availability_scanner",
        "artifact_type": "signalforge_migrated_workflow_dry_run_input_availability",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "categories": categories,
    }


def main() -> int:
    manifest = build_dry_run_input_availability_manifest()
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if manifest["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
