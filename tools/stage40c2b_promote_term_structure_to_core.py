from __future__ import annotations

import ast
import json
from pathlib import Path


REPO = Path(".").resolve()

SOURCE_TOOL = REPO / "tools/augment_repaired_candidates_with_term_structure.py"
CORE_PATH = REPO / "src/signalforge/engines/strategy_selection/term_structure_candidate_augmentation.py"
OUT = REPO / "artifacts/stage40c2b_term_structure_core_promotion"


def rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def is_stage12_wrapper(source: str) -> bool:
    return "Stage 12 tool shim for term-structure candidate augmentation" in source


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
        raise FileNotFoundError(f"Missing Stage 12 builder: {SOURCE_TOOL}")

    current_source = read(SOURCE_TOOL)

    backup_path = OUT / "augment_repaired_candidates_with_term_structure.py.before_stage40c2b"

    if is_stage12_wrapper(current_source):
        if not backup_path.exists():
            raise RuntimeError(
                "Stage 12 tool already appears to be a wrapper, but no Stage 40C2B backup exists."
            )
        original_source = read(backup_path)
    else:
        original_source = current_source
        write(backup_path, original_source)

    function_names = top_level_functions(original_source)

    core_source = (
        "# Auto-promoted by Stage 40C2B.\n"
        "# Core engine for Stage 12 term-structure candidate augmentation.\n"
        "# The tools/ script is now only a CLI compatibility shim.\n\n"
        + original_source.rstrip()
        + "\n"
    )

    wrapper_source = '''from __future__ import annotations

"""Stage 12 tool shim for term-structure candidate augmentation.

The implementation has been promoted to:
signalforge.engines.strategy_selection.term_structure_candidate_augmentation

This file remains so existing workflow commands keep working.
"""

from signalforge.engines.strategy_selection.term_structure_candidate_augmentation import *  # noqa: F401,F403
from signalforge.engines.strategy_selection import term_structure_candidate_augmentation as _core


if __name__ == "__main__":
    raise SystemExit(_core.main())
'''

    write(CORE_PATH, core_source)
    write(SOURCE_TOOL, wrapper_source)

    summary = {
        "adapter_type": "stage40c2b_term_structure_core_promotion_patcher",
        "artifact_type": "signalforge_stage40c2b_term_structure_core_promotion",
        "contract": "stage40c2b_term_structure_core_promotion",
        "is_ready": True,
        "source_tool": rel(SOURCE_TOOL),
        "core_path": rel(CORE_PATH),
        "backup_path": rel(backup_path),
        "promoted_function_count": len(function_names),
        "promoted_functions": function_names,
        "paths": {
            "summary_path": "artifacts/stage40c2b_term_structure_core_promotion/signalforge_stage40c2b_term_structure_core_promotion_summary.json",
            "backup_path": "artifacts/stage40c2b_term_structure_core_promotion/augment_repaired_candidates_with_term_structure.py.before_stage40c2b",
        },
    }

    write(
        OUT / "signalforge_stage40c2b_term_structure_core_promotion_summary.json",
        json.dumps(summary, indent=2, sort_keys=True),
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

