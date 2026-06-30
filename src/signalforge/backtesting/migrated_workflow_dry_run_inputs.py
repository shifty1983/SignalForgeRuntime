from __future__ import annotations

import json
from pathlib import Path
from typing import Any


EXCLUDED_NAME_FRAGMENTS = (
    "migration_source_graph",
    "source_graph",
    "bootstrap_summary",
    "cli_contract",
    "dry_run_input_availability",
    "debug",
    "manifest",
)


STRICT_DRY_RUN_ARTIFACT_CONTRACTS = {
    "historical_decision_rows": [
        "signalforge_historical_decision_rows.jsonl",
        "signalforge_historical_decision_rows_summary.json",
    ],
    "historical_strategy_candidate_rows": [
        "signalforge_historical_strategy_candidate_rows.jsonl",
        "signalforge_historical_strategy_candidate_rows_summary.json",
    ],
    "walk_forward_expectancy": [
        "signalforge_walk_forward_expectancy_rows.jsonl",
        "signalforge_walk_forward_expectancy_summary.json",
    ],
    "historical_strategy_selection_rows": [
        "signalforge_historical_strategy_selection_rows.jsonl",
        "signalforge_historical_strategy_selection_rows_summary.json",
    ],
    "historical_strategy_leg_selection_rows": [
        "signalforge_historical_strategy_leg_selection_rows.jsonl",
        "signalforge_historical_strategy_leg_selection_rows_summary.json",
    ],
    "portfolio_position_sizing_replay": [
        "signalforge_portfolio_position_sizing_replay_rows.jsonl",
        "signalforge_portfolio_position_sizing_replay_summary.json",
    ],
    "portfolio_selected_trade_sequence": [
        "signalforge_portfolio_selected_trade_sequence_rows.jsonl",
        "signalforge_portfolio_selected_trade_sequence_summary.json",
    ],
    "quote_join_or_attribution": [
        "quote",
        "attribution",
    ],
    "stress_validation": [
        "stress",
    ],
}


def _is_excluded(path: Path) -> bool:
    value = str(path).lower()
    return any(fragment in value for fragment in EXCLUDED_NAME_FRAGMENTS)


def _candidate_roots() -> list[Path]:
    roots = [Path("artifacts"), Path("data")]

    legacy_old_repo = Path(
        r"C:\Users\02011715\Documents\SignalForge\raw_data_layer\artifacts"
    )
    if legacy_old_repo.exists():
        roots.append(legacy_old_repo)

    return roots


def _find_exact_or_keyword_matches(tokens: list[str]) -> list[str]:
    matches: list[str] = []

    for root in _candidate_roots():
        if not root.exists():
            continue

        for path in root.rglob("*"):
            if not path.is_file():
                continue

            if path.suffix.lower() not in {".json", ".jsonl"}:
                continue

            if _is_excluded(path):
                continue

            name = path.name.lower()
            full = str(path).lower()

            for token in tokens:
                token_lower = token.lower()

                if token_lower.endswith((".json", ".jsonl")):
                    if name == token_lower:
                        matches.append(str(path))
                else:
                    if token_lower in full:
                        matches.append(str(path))

    return sorted(set(matches))


def build_dry_run_input_availability_manifest() -> dict[str, Any]:
    categories: dict[str, Any] = {}

    for category, tokens in STRICT_DRY_RUN_ARTIFACT_CONTRACTS.items():
        matches = _find_exact_or_keyword_matches(tokens)
        categories[category] = {
            "contract_tokens": tokens,
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
        "adapter_type": "migrated_workflow_strict_dry_run_input_availability_scanner",
        "artifact_type": "signalforge_migrated_workflow_strict_dry_run_input_availability",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "categories": categories,
        "candidate_roots": [str(root) for root in _candidate_roots()],
        "excluded_name_fragments": list(EXCLUDED_NAME_FRAGMENTS),
    }


def main() -> int:
    manifest = build_dry_run_input_availability_manifest()
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if manifest["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())




