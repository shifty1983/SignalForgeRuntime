from __future__ import annotations

import json
from pathlib import Path
from typing import Any


OLD_ARTIFACT_ROOT = Path(
    r"C:\Users\02011715\Documents\SignalForge\raw_data_layer\artifacts"
)


ARTIFACT_GROUPS = {
    "historical_decision_rows": {
        "folder_patterns": ["historical_decision_rows_20210601_20260531"],
        "required_name_tokens": ["historical_decision_rows"],
    },
    "historical_strategy_candidate_rows": {
        "folder_patterns": ["historical_strategy_candidate_rows_20210601_20260531"],
        "required_name_tokens": ["historical_strategy_candidate_rows"],
    },
    "walk_forward_expectancy": {
        "folder_patterns": [
            "walk_forward_expectancy_safe_20210601_20260531",
            "walk_forward_expectancy_20210601_20260531",
        ],
        "required_name_tokens": ["walk_forward_expectancy"],
    },
    "historical_strategy_selection_rows": {
        "folder_patterns": ["historical_strategy_selection_rows_20210601_20260531"],
        "required_name_tokens": ["historical_strategy_selection_rows"],
    },
    "historical_strategy_leg_selection_rows": {
        "folder_patterns": ["historical_strategy_leg_selection_rows_20210601_20260531"],
        "required_name_tokens": ["historical_strategy_leg_selection_rows"],
    },
    "portfolio_position_sizing_replay": {
        "folder_patterns": ["portfolio_position_sizing_replay_20210601_20260531"],
        "required_name_tokens": ["portfolio_position_sizing_replay"],
    },
    "portfolio_selected_trade_sequence": {
        "folder_patterns": ["portfolio_selected_trade_sequence_20210601_20260531"],
        "required_name_tokens": ["portfolio_selected_trade_sequence"],
    },
    "layer_field_carry_forward_enrichment_v2": {
        "folder_patterns": [
            "layer_field_carry_forward_enrichment_v2",
            "carry_forward_enrichment",
            "field_carry_forward",
        ],
        "required_name_tokens": ["carry", "enrichment", "layer"],
    },
    "quote_join": {
        "folder_patterns": [
            "v3_2_1_native_quote_join_v1",
            "native_quote_join",
            "quote_join",
        ],
        "required_name_tokens": ["quote"],
    },
    "quote_attribution": {
        "folder_patterns": [
            "v3_2_1_native_quote_attribution_v1",
            "native_quote_attribution",
            "quote_attribution",
        ],
        "required_name_tokens": ["attribution"],
    },
    "v3_2_2_pruning": {
        "folder_patterns": [
            "v3_2_2_symbol_regime_walkforward_prune_stress_v1",
            "symbol_regime_walkforward_prune",
            "prune",
        ],
        "required_name_tokens": ["prune"],
    },
    "ruleset_lock": {
        "folder_patterns": [
            "v3_2_reconciled_canonical_from_v2_locked_actions",
            "locked_actions",
            "canonical",
        ],
        "required_name_tokens": ["locked", "canonical"],
    },
    "stress_validation": {
        "folder_patterns": [
            "portfolio_robustness_stress_validation_20210601_20260531",
            "portfolio_robustness_stress_validation",
            "native_quote_pnl_stress",
        ],
        "required_name_tokens": ["stress"],
    },
}


def _candidate_folders(folder_patterns: list[str]) -> list[Path]:
    if not OLD_ARTIFACT_ROOT.exists():
        return []

    folders: list[Path] = []
    for folder in OLD_ARTIFACT_ROOT.iterdir():
        if not folder.is_dir():
            continue

        lower_name = folder.name.lower()
        if any(pattern.lower() in lower_name for pattern in folder_patterns):
            folders.append(folder)

    return sorted(folders)


def _scan_files(folder: Path, required_name_tokens: list[str]) -> dict[str, list[str]]:
    jsonl_files: list[str] = []
    json_files: list[str] = []

    for path in folder.rglob("*"):
        if not path.is_file():
            continue

        lower_name = path.name.lower()
        if not any(token.lower() in lower_name for token in required_name_tokens):
            continue

        if path.suffix.lower() == ".jsonl":
            jsonl_files.append(str(path))
        elif path.suffix.lower() == ".json":
            json_files.append(str(path))

    return {
        "jsonl_files": sorted(jsonl_files),
        "json_files": sorted(json_files),
    }


def build_exact_artifact_path_manifest() -> dict[str, Any]:
    groups: dict[str, Any] = {}

    for group_name, config in ARTIFACT_GROUPS.items():
        folders = _candidate_folders(config["folder_patterns"])

        folder_results: list[dict[str, Any]] = []
        all_jsonl: list[str] = []
        all_json: list[str] = []

        for folder in folders:
            files = _scan_files(folder, config["required_name_tokens"])
            all_jsonl.extend(files["jsonl_files"])
            all_json.extend(files["json_files"])
            folder_results.append({
                "folder": str(folder),
                **files,
            })

        groups[group_name] = {
            "folder_patterns": config["folder_patterns"],
            "required_name_tokens": config["required_name_tokens"],
            "folder_count": len(folders),
            "jsonl_count": len(set(all_jsonl)),
            "json_count": len(set(all_json)),
            "sample_jsonl_files": sorted(set(all_jsonl))[:20],
            "sample_json_files": sorted(set(all_json))[:20],
            "folders": folder_results,
            "has_row_file": len(set(all_jsonl)) > 0,
            "has_json_file": len(set(all_json)) > 0,
        }

    blockers: list[str] = []
    for group_name, group in groups.items():
        if group_name in {
            "historical_decision_rows",
            "historical_strategy_candidate_rows",
            "walk_forward_expectancy",
            "historical_strategy_selection_rows",
            "historical_strategy_leg_selection_rows",
            "portfolio_position_sizing_replay",
            "portfolio_selected_trade_sequence",
            "layer_field_carry_forward_enrichment_v2",
        }:
            if not group["has_row_file"]:
                blockers.append(f"{group_name}_row_file_missing")
            if not group["has_json_file"]:
                blockers.append(f"{group_name}_summary_or_json_missing")

    return {
        "adapter_type": "migrated_workflow_exact_artifact_path_manifest_builder",
        "artifact_type": "signalforge_migrated_workflow_exact_artifact_path_manifest",
        "old_artifact_root": str(OLD_ARTIFACT_ROOT),
        "groups": groups,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "is_ready": len(blockers) == 0,
    }


def main() -> int:
    manifest = build_exact_artifact_path_manifest()
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if manifest["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
