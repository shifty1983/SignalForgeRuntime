from __future__ import annotations

import ast
import json
from pathlib import Path


REPO = Path(".").resolve()

SOURCE_BUILDER = REPO / "src/signalforge/backtesting/historical_strategy_leg_selection_rows_builder.py"
CORE_PATH = REPO / "src/signalforge/engines/strategy_selection/leg_selection.py"
OUT = REPO / "artifacts/stage40c3b_leg_selection_core_promotion"


def rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def is_stage16_wrapper(source: str) -> bool:
    return "Stage 16 backtesting shim for historical strategy leg selection rows" in source


def top_level_functions(source: str) -> list[str]:
    tree = ast.parse(source)
    funcs = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs.append((node.lineno, node.name))
    return [name for _, name in sorted(funcs)]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    if not SOURCE_BUILDER.exists():
        raise FileNotFoundError(f"Missing Stage 16 builder: {SOURCE_BUILDER}")

    current_source = read(SOURCE_BUILDER)
    backup_path = OUT / "historical_strategy_leg_selection_rows_builder.py.before_stage40c3b"

    if is_stage16_wrapper(current_source):
        if not backup_path.exists():
            raise RuntimeError(
                "Stage 16 builder already appears to be a wrapper, but no Stage 40C3B backup exists."
            )
        original_source = read(backup_path)
    else:
        original_source = current_source
        write(backup_path, original_source)

    function_names = top_level_functions(original_source)

    core_source = (
        "# Auto-promoted by Stage 40C3B.\n"
        "# Core engine for Stage 16 historical/options leg selection.\n"
        "# Backtesting should call this module instead of owning leg-selection logic.\n\n"
        + original_source.rstrip()
        + "\n"
    )

    wrapper_lines = [
        "from __future__ import annotations",
        "",
        '"""Stage 16 backtesting shim for historical strategy leg selection rows.',
        "",
        "The implementation has been promoted to:",
        "signalforge.engines.strategy_selection.leg_selection",
        "",
        "This file remains for existing CLI/artifact compatibility.",
        '"""',
        "",
        "import signalforge.engines.strategy_selection.leg_selection as _core",
        "",
        "",
    ]

    for name in function_names:
        wrapper_lines.extend(
            [
                f"def {name}(*args, **kwargs):",
                f"    return _core.{name}(*args, **kwargs)",
                "",
                "",
            ]
        )

    wrapper_lines.extend(
        [
            "__all__ = [",
            *[f'    "{name}",' for name in function_names],
            "]",
            "",
        ]
    )

    wrapper_source = "\n".join(wrapper_lines).rstrip() + "\n"

    write(CORE_PATH, core_source)
    write(SOURCE_BUILDER, wrapper_source)

    summary = {
        "adapter_type": "stage40c3b_leg_selection_core_promotion_patcher",
        "artifact_type": "signalforge_stage40c3b_leg_selection_core_promotion",
        "contract": "stage40c3b_leg_selection_core_promotion",
        "is_ready": True,
        "source_builder": rel(SOURCE_BUILDER),
        "core_path": rel(CORE_PATH),
        "backup_path": rel(backup_path),
        "promoted_function_count": len(function_names),
        "promoted_functions": function_names,
        "paths": {
            "summary_path": "artifacts/stage40c3b_leg_selection_core_promotion/signalforge_stage40c3b_leg_selection_core_promotion_summary.json",
            "backup_path": "artifacts/stage40c3b_leg_selection_core_promotion/historical_strategy_leg_selection_rows_builder.py.before_stage40c3b",
        },
    }

    write(
        OUT / "signalforge_stage40c3b_leg_selection_core_promotion_summary.json",
        json.dumps(summary, indent=2, sort_keys=True),
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
