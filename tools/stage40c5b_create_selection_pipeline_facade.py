from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any


REPO = Path(".").resolve()
OUT = REPO / "artifacts/stage40c5b_selection_pipeline_facade"

PIPELINE_PATH = REPO / "src/signalforge/engines/strategy_selection/selection_pipeline.py"

SOURCE_MODULES = [
    REPO / "src/signalforge/engines/strategy_selection/selection_decision.py",
    REPO / "src/signalforge/engines/strategy_selection/selection_report.py",
    REPO / "src/signalforge/engines/strategy_selection/selector.py",
    REPO / "src/signalforge/engines/strategy_selection/rules.py",
    REPO / "src/signalforge/engines/strategy_selection/allocation.py",
    REPO / "src/signalforge/engines/strategy_selection/portfolio_candidate_input.py",
]


def rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def public_functions(path: Path) -> list[str]:
    if not path.exists():
        return []

    tree = ast.parse(read(path), filename=str(path))
    names = []

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                names.append(node.name)

    return names


def module_name(path: Path) -> str:
    return rel(path).replace("src/signalforge/", "signalforge/").replace("/", ".").removesuffix(".py")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    if PIPELINE_PATH.exists():
        backup_path = OUT / "selection_pipeline.py.before_stage40c5b"
        if not backup_path.exists():
            write(backup_path, read(PIPELINE_PATH))
    else:
        backup_path = None

    module_reports = []
    exported_names = []

    for path in SOURCE_MODULES:
        funcs = public_functions(path)
        module_reports.append({
            "path": rel(path),
            "module": module_name(path),
            "exists": path.exists(),
            "public_function_count": len(funcs),
            "public_functions": funcs,
        })
        exported_names.extend(funcs)

    unique_exported_names = sorted(set(exported_names))

    source = '''from __future__ import annotations

"""Core strategy-selection pipeline facade.

Stage 19 uses this module as the stable core entry point for strategy-selection
pipeline behavior. It intentionally consolidates existing core helpers instead
of reimplementing selection logic.

The historical backtesting builder may continue to call the lower-level helpers
directly, but paper/live code should prefer this facade when it needs the full
selection pipeline namespace.
"""

from signalforge.engines.strategy_selection.selection_decision import *  # noqa: F401,F403
from signalforge.engines.strategy_selection.selection_report import *  # noqa: F401,F403
from signalforge.engines.strategy_selection.selector import *  # noqa: F401,F403
from signalforge.engines.strategy_selection.rules import *  # noqa: F401,F403
from signalforge.engines.strategy_selection.allocation import *  # noqa: F401,F403
from signalforge.engines.strategy_selection.portfolio_candidate_input import *  # noqa: F401,F403


__all__ = [
'''

    for name in unique_exported_names:
        source += f'    "{name}",\n'

    source += ''']
'''

    write(PIPELINE_PATH, source)

    summary = {
        "adapter_type": "stage40c5b_selection_pipeline_facade_builder",
        "artifact_type": "signalforge_stage40c5b_selection_pipeline_facade",
        "contract": "stage40c5b_selection_pipeline_facade",
        "is_ready": True,
        "pipeline_path": rel(PIPELINE_PATH),
        "backup_path": rel(backup_path) if backup_path else None,
        "source_module_count": len(SOURCE_MODULES),
        "exported_public_function_count": len(unique_exported_names),
        "source_modules": module_reports,
        "paths": {
            "summary_path": "artifacts/stage40c5b_selection_pipeline_facade/signalforge_stage40c5b_selection_pipeline_facade_summary.json",
        },
    }

    write(
        OUT / "signalforge_stage40c5b_selection_pipeline_facade_summary.json",
        json.dumps(summary, indent=2, sort_keys=True),
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
