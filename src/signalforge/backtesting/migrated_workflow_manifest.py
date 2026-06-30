from __future__ import annotations

import importlib
import json
import re
from pkgutil import iter_modules
from typing import Any


KNOWN_REQUIRED_MODULES: dict[str, str] = {
    "historical_decision_rows": "signalforge.backtesting.historical_decision_rows",
    "historical_strategy_candidate_rows": "signalforge.backtesting.historical_strategy_candidate_rows_builder",
    "walk_forward_expectancy": "signalforge.backtesting.walk_forward_expectancy_builder",
    "walk_forward_expectancy_availability_safe": "signalforge.backtesting.walk_forward_expectancy_availability_safe_builder",
    "historical_strategy_selection_rows": "signalforge.backtesting.historical_strategy_selection_rows_builder",
    "historical_strategy_leg_selection_rows": "signalforge.backtesting.historical_strategy_leg_selection_rows_builder",
    "portfolio_position_sizing_replay": "signalforge.backtesting.portfolio_position_sizing_replay",
    "portfolio_selected_trade_sequence": "signalforge.backtesting.portfolio_selected_trade_sequence",
    "portfolio_value_ranked_allocator_v2": "signalforge.backtesting.portfolio_value_ranked_allocator_v2",
    "layer_field_carry_forward_enrichment_v2": "signalforge.backtesting.layer_field_carry_forward_enrichment_v2",
    "native_quote_join_v1": "signalforge.backtesting.v3_2_1_native_quote_join_v1",
    "native_quote_pnl_stress_v1": "signalforge.backtesting.v3_2_1_native_quote_pnl_stress_v1",
    "strategy_family_eligibility": "signalforge.engines.strategy_selection.strategy_family_eligibility",
    "data_source_inventory": "signalforge.data_sources.data_source_inventory",
    "spread_guardrail_rulebook": "signalforge.rulebooks.spread_guardrail",
    "prior_symbol_regime_state_rulebook": "signalforge.rulebooks.prior_symbol_regime_state",
    "v3_2_2_rulebook": "signalforge.rulebooks.v3_2_2",
    "runtime_execution_readiness_contract": "signalforge.runtime.execution.readiness_contract",
}


DISCOVERED_BACKTESTING_CATEGORIES: dict[str, list[str]] = {
    "quote_audit_or_attribution": [
        r"quote.*audit",
        r"quote.*attribution",
        r"attribution.*quote",
    ],
    "v3_2_2_pruning": [
        r"v3_2_2.*prun",
        r"v3_2_2.*prior",
        r"v3_2_2.*weak",
        r"prior.*prun",
        r"weak.*prior",
    ],
    "v3_2_2_ruleset_lock": [
        r"v3_2_2.*ruleset",
        r"ruleset.*lock",
        r"locked.*ruleset",
        r"v3_2_2.*lock",
        r"v3_2_2.*final",
        r"locked.*actions",
        r"canonical.*locked",
        r"reconciled.*canonical",
        r"v3_2.*locked.*actions",
    ],
}


ORDERED_WORKFLOW_STEPS: list[str] = [
    "historical_decision_rows",
    "historical_strategy_candidate_rows",
    "walk_forward_expectancy",
    "walk_forward_expectancy_availability_safe",
    "historical_strategy_selection_rows",
    "strategy_family_eligibility",
    "historical_strategy_leg_selection_rows",
    "portfolio_position_sizing_replay",
    "portfolio_selected_trade_sequence",
    "portfolio_value_ranked_allocator_v2",
    "layer_field_carry_forward_enrichment_v2",
    "native_quote_join_v1",
    "quote_audit_or_attribution",
    "v3_2_2_pruning",
    "v3_2_2_ruleset_lock",
    "native_quote_pnl_stress_v1",
    "runtime_execution_readiness_contract",
]


def _import_status(module_path: str) -> dict[str, Any]:
    try:
        importlib.import_module(module_path)
    except Exception as exc:  # pragma: no cover - surfaced in manifest
        return {
            "module": module_path,
            "import_ready": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

    return {
        "module": module_path,
        "import_ready": True,
        "error_type": None,
        "error": None,
    }


def _discover_package_modules(package_name: str) -> list[str]:
    package = importlib.import_module(package_name)
    package_paths = getattr(package, "__path__", [])

    return sorted(
        module_info.name
        for module_info in iter_modules(package_paths)
        if not module_info.name.startswith("_")
    )


def _find_backtesting_category(category: str, patterns: list[str]) -> dict[str, Any]:
    modules = _discover_package_modules("signalforge.backtesting")

    matches: list[str] = []
    for module_name in modules:
        if any(re.search(pattern, module_name, flags=re.IGNORECASE) for pattern in patterns):
            matches.append(module_name)

    import_checks = [
        _import_status(f"signalforge.backtesting.{module_name}")
        for module_name in matches
    ]

    return {
        "category": category,
        "matched_modules": matches,
        "match_count": len(matches),
        "import_checks": import_checks,
        "is_ready": bool(matches) and all(check["import_ready"] for check in import_checks),
    }


def build_migrated_workflow_manifest() -> dict[str, Any]:
    known_checks = {
        name: _import_status(module_path)
        for name, module_path in KNOWN_REQUIRED_MODULES.items()
    }

    discovered_checks = {
        category: _find_backtesting_category(category, patterns)
        for category, patterns in DISCOVERED_BACKTESTING_CATEGORIES.items()
    }

    execution_modules = _discover_package_modules("signalforge.runtime.execution")

    steps: list[dict[str, Any]] = []
    for step in ORDERED_WORKFLOW_STEPS:
        if step in known_checks:
            steps.append({
                "step": step,
                "resolution_type": "known_module",
                "is_ready": known_checks[step]["import_ready"],
                "details": known_checks[step],
            })
        else:
            discovered = discovered_checks[step]
            steps.append({
                "step": step,
                "resolution_type": "discovered_category",
                "is_ready": discovered["is_ready"],
                "details": discovered,
            })

    blockers: list[str] = []

    for name, check in known_checks.items():
        if not check["import_ready"]:
            blockers.append(f"{name}_import_failed")

    for category, check in discovered_checks.items():
        if not check["is_ready"]:
            blockers.append(f"{category}_not_resolved_or_import_failed")

    if not execution_modules:
        blockers.append("no_runtime_execution_modules_discovered")

    return {
        "adapter_type": "migrated_workflow_manifest_builder",
        "artifact_type": "signalforge_migrated_workflow_manifest",
        "candidate_id": "signalforge_v3_2_2_paper_candidate",
        "workflow_step_count": len(steps),
        "workflow_steps": steps,
        "known_required_module_count": len(known_checks),
        "discovered_category_count": len(discovered_checks),
        "runtime_execution_modules": execution_modules,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "is_ready": len(blockers) == 0,
        "readiness_scope": "source_migration_import_safety_and_workflow_coverage",
    }


def main() -> int:
    manifest = build_migrated_workflow_manifest()
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if manifest["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


