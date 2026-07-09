from __future__ import annotations

import ast
import json
from pathlib import Path


REPO = Path(".").resolve()
OUT = REPO / "artifacts/stage40c6b_pruned_selection_core_promotion"

SOURCE = REPO / "src/signalforge/backtesting/historical_strategy_selection_cohort_risk_cli.py"
CORE = REPO / "src/signalforge/engines/strategy_selection/pruned_selection.py"


def rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def is_stage21_wrapper(source: str) -> bool:
    return "Stage 21 backtesting shim for cohort-risk / pruned strategy selection" in source


def top_level_functions(source: str) -> list[str]:
    tree = ast.parse(source)
    funcs = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs.append((node.lineno, node.name))
    return [name for _, name in sorted(funcs)]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    if not SOURCE.exists():
        raise FileNotFoundError(f"Missing Stage 21 source file: {SOURCE}")

    current_source = read(SOURCE)
    backup_path = OUT / "historical_strategy_selection_cohort_risk_cli.py.before_stage40c6b"

    if is_stage21_wrapper(current_source):
        if not backup_path.exists():
            raise RuntimeError(
                "Stage 21 source already appears to be a wrapper, but no Stage 40C6B backup exists."
            )
        original_source = read(backup_path)
    else:
        original_source = current_source
        write(backup_path, original_source)

    function_names = top_level_functions(original_source)

    core_source = (
        "# Auto-promoted by Stage 40C6B.\n"
        "# Core engine for Stage 21 cohort-risk / pruned strategy selection.\n"
        "# Backtesting should call this module instead of owning post-expectancy pruning logic.\n\n"
        + original_source.rstrip()
        + "\n"
    )

    wrapper_source = '''from __future__ import annotations

"""Stage 21 backtesting shim for cohort-risk / pruned strategy selection.

The implementation has been promoted to:
signalforge.engines.strategy_selection.pruned_selection

This file remains so existing workflow commands keep working.
"""

from signalforge.engines.strategy_selection.pruned_selection import *  # noqa: F401,F403
from signalforge.engines.strategy_selection import pruned_selection as _core


if __name__ == "__main__":
    raise SystemExit(_core.main())
'''

    write(CORE, core_source)
    write(SOURCE, wrapper_source)

    summary = {
        "adapter_type": "stage40c6b_pruned_selection_core_promotion_patcher",
        "artifact_type": "signalforge_stage40c6b_pruned_selection_core_promotion",
        "contract": "stage40c6b_pruned_selection_core_promotion",
        "is_ready": True,
        "source": rel(SOURCE),
        "core_path": rel(CORE),
        "backup_path": rel(backup_path),
        "promoted_function_count": len(function_names),
        "promoted_functions": function_names,
        "paths": {
            "summary_path": "artifacts/stage40c6b_pruned_selection_core_promotion/signalforge_stage40c6b_pruned_selection_core_promotion_summary.json",
            "backup_path": "artifacts/stage40c6b_pruned_selection_core_promotion/historical_strategy_selection_cohort_risk_cli.py.before_stage40c6b",
        },
    }

    write(
        OUT / "signalforge_stage40c6b_pruned_selection_core_promotion_summary.json",
        json.dumps(summary, indent=2, sort_keys=True),
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
