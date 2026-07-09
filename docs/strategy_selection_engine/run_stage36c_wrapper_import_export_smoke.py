import importlib

pairs = [
    (
        "signalforge.options_execution.strategy_structure_availability_v21",
        "signalforge.engines.strategy_selection.strategy_structure_availability_v21",
    ),
    (
        "signalforge.options_execution.resolved_strategy_execution_rules_v21",
        "signalforge.engines.strategy_selection.resolved_strategy_execution_rules_v21",
    ),
    (
        "signalforge.options_execution.execution_qualified_historical_strategy_candidates_v21",
        "signalforge.engines.strategy_selection.execution_qualified_historical_strategy_candidates_v21",
    ),
    (
        "signalforge.options_execution.repaired_historical_strategy_candidates_v13_v21",
        "signalforge.engines.strategy_selection.repaired_historical_strategy_candidates_v13_v21",
    ),
]

for old_module, new_module in pairs:
    old = importlib.import_module(old_module)
    new = importlib.import_module(new_module)

    print(f"import_ok: {old_module} -> {new_module}")

    old_public = {name for name in dir(old) if not name.startswith("_")}
    new_public = {name for name in dir(new) if not name.startswith("_")}

    missing = sorted(new_public - old_public)
    print(f"public_export_missing_count: {len(missing)}")

    if missing:
        print(missing[:20])
        raise SystemExit(1)
