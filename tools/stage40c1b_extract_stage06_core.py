from __future__ import annotations

import ast
import json
from pathlib import Path


REPO = Path(".").resolve()

BT_PATH = REPO / "src/signalforge/backtesting/historical_decision_rows.py"
REGIME_CORE_PATH = REPO / "src/signalforge/engines/regime/historical_weekly_regime_index.py"
BEHAVIOR_CORE_PATH = REPO / "src/signalforge/engines/behavior/historical_decision_rows_core.py"
OUT = REPO / "artifacts/stage40c1b_stage06_core_extraction_patch"

REGIME_FUNCTIONS = {
    "_row_date",
    "build_weekly_regime_index",
    "lookup_asof_weekly_regime",
}


def rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def top_level_functions(source: str) -> list[str]:
    tree = ast.parse(source)
    funcs = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs.append((node.lineno, node.name))
    return [name for _, name in sorted(funcs)]


def is_stage06_shim(source: str) -> bool:
    return "Backtesting shim for Stage 06 historical decision rows" in source


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    if not BT_PATH.exists():
        raise FileNotFoundError(f"Missing backtesting file: {BT_PATH}")

    current_source = read(BT_PATH)

    if is_stage06_shim(current_source):
        backup_path = OUT / "historical_decision_rows.py.before_stage40c1b"
        if not backup_path.exists():
            raise RuntimeError(
                "Backtesting file already appears to be a Stage 06 shim, "
                "but no Stage 40C1B backup exists. Restore original file before rerunning."
            )
        original_source = read(backup_path)
    else:
        original_source = current_source
        backup_path = OUT / "historical_decision_rows.py.before_stage40c1b"
        write(backup_path, original_source)

    function_names = top_level_functions(original_source)

    behavior_core_source = (
        "# Auto-promoted by Stage 40C1B.\n"
        "# Core behavior/decision-context implementation for Stage 06 historical decision rows.\n"
        "# Backtesting should call this module instead of owning this logic.\n\n"
        + original_source.rstrip()
        + "\n"
    )

    regime_imports = []
    for name in sorted(REGIME_FUNCTIONS):
        if name in function_names:
            regime_imports.append(name)

    regime_core_source = (
        "from __future__ import annotations\n\n"
        '"""Core regime facade for Stage 06 historical weekly regime lookup logic."""\n\n'
        "from signalforge.engines.behavior.historical_decision_rows_core import (\n"
        + "".join(f"    {name},\n" for name in regime_imports)
        + ")\n\n"
        "__all__ = [\n"
        + "".join(f'    "{name}",\n' for name in regime_imports)
        + "]\n"
    )

    shim_lines = [
        "from __future__ import annotations",
        "",
        '"""Backtesting shim for Stage 06 historical decision rows.',
        "",
        "Stage 06 logic has been promoted into core engine namespaces.",
        "This module remains for existing CLI/artifact compatibility.",
        '"""',
        "",
        "import signalforge.engines.behavior.historical_decision_rows_core as _decision_core",
        "import signalforge.engines.regime.historical_weekly_regime_index as _regime_core",
        "",
        "",
    ]

    for name in function_names:
        target = "_regime_core" if name in REGIME_FUNCTIONS else "_decision_core"
        shim_lines.extend(
            [
                f"def {name}(*args, **kwargs):",
                f"    return {target}.{name}(*args, **kwargs)",
                "",
                "",
            ]
        )

    shim_source = "\n".join(shim_lines).rstrip() + "\n"

    write(BEHAVIOR_CORE_PATH, behavior_core_source)
    write(REGIME_CORE_PATH, regime_core_source)
    write(BT_PATH, shim_source)

    summary = {
        "adapter_type": "stage40c1b_stage06_core_extraction_patcher",
        "artifact_type": "signalforge_stage40c1b_stage06_core_extraction_patch",
        "contract": "stage40c1b_stage06_core_extraction_patch",
        "is_ready": True,
        "source_backtesting_file": rel(BT_PATH),
        "backup_path": rel(backup_path),
        "behavior_core_path": rel(BEHAVIOR_CORE_PATH),
        "regime_core_path": rel(REGIME_CORE_PATH),
        "wrapper_function_count": len(function_names),
        "wrapper_functions": function_names,
        "regime_facade_functions": regime_imports,
        "paths": {
            "summary_path": "artifacts/stage40c1b_stage06_core_extraction_patch/signalforge_stage40c1b_stage06_core_extraction_patch_summary.json",
            "backup_path": "artifacts/stage40c1b_stage06_core_extraction_patch/historical_decision_rows.py.before_stage40c1b",
        },
    }

    write(
        OUT / "signalforge_stage40c1b_stage06_core_extraction_patch_summary.json",
        json.dumps(summary, indent=2, sort_keys=True),
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
