from __future__ import annotations

import ast
import json
from pathlib import Path


REPO = Path(".").resolve()

SOURCE_TOOL = REPO / "tools/build_v13_v21_selector_candidate_input.py"
CORE_PATH = REPO / "src/signalforge/engines/strategy_selection/selector_candidate_input.py"
OUT = REPO / "artifacts/stage40c3e_selector_candidate_input_core_promotion"


def rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def is_stage15_wrapper(source: str) -> bool:
    return "Stage 15 tool shim for selector candidate input" in source


def top_level_functions(source: str) -> list[str]:
    tree = ast.parse(source)
    funcs = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs.append((node.lineno, node.name))
    return [name for _, name in sorted(funcs)]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    if not SOURCE_TOOL.exists():
        raise FileNotFoundError(f"Missing Stage 15 tool: {SOURCE_TOOL}")

    current_source = read(SOURCE_TOOL)
    backup_path = OUT / "build_v13_v21_selector_candidate_input.py.before_stage40c3e"

    if is_stage15_wrapper(current_source):
        if not backup_path.exists():
            raise RuntimeError(
                "Stage 15 tool already appears to be a wrapper, but no Stage 40C3E backup exists."
            )
        original_source = read(backup_path)
    else:
        original_source = current_source
        write(backup_path, original_source)

    function_names = top_level_functions(original_source)

    core_source = (
        "# Auto-promoted by Stage 40C3E.\n"
        "# Core engine for Stage 15 selector / leg-selection candidate input.\n"
        "# The tools/ script is now only a CLI compatibility shim.\n\n"
        + original_source.rstrip()
        + "\n"
    )

    wrapper_source = '''from __future__ import annotations

"""Stage 15 tool shim for selector candidate input.

The implementation has been promoted to:
signalforge.engines.strategy_selection.selector_candidate_input

This file remains so existing workflow commands keep working.
"""

from signalforge.engines.strategy_selection.selector_candidate_input import *  # noqa: F401,F403
from signalforge.engines.strategy_selection import selector_candidate_input as _core


if __name__ == "__main__":
    raise SystemExit(_core.main())
'''

    write(CORE_PATH, core_source)
    write(SOURCE_TOOL, wrapper_source)

    summary = {
        "adapter_type": "stage40c3e_selector_candidate_input_core_promotion_patcher",
        "artifact_type": "signalforge_stage40c3e_selector_candidate_input_core_promotion",
        "contract": "stage40c3e_selector_candidate_input_core_promotion",
        "is_ready": True,
        "source_tool": rel(SOURCE_TOOL),
        "core_path": rel(CORE_PATH),
        "backup_path": rel(backup_path),
        "promoted_function_count": len(function_names),
        "promoted_functions": function_names,
        "paths": {
            "summary_path": "artifacts/stage40c3e_selector_candidate_input_core_promotion/signalforge_stage40c3e_selector_candidate_input_core_promotion_summary.json",
            "backup_path": "artifacts/stage40c3e_selector_candidate_input_core_promotion/build_v13_v21_selector_candidate_input.py.before_stage40c3e",
        },
    }

    write(
        OUT / "signalforge_stage40c3e_selector_candidate_input_core_promotion_summary.json",
        json.dumps(summary, indent=2, sort_keys=True),
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
