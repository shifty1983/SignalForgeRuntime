from __future__ import annotations

import ast
import json
from pathlib import Path


REPO = Path(".").resolve()
OUT = REPO / "artifacts/stage40c7b_selected_trade_sequence_core_promotion"

SOURCE = REPO / "src/signalforge/backtesting/portfolio_selected_trade_sequence.py"
CORE = REPO / "src/signalforge/engines/portfolio_construction/selected_trade_sequence.py"
CORE_PACKAGE = REPO / "src/signalforge/engines/portfolio_construction"


def rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def is_stage23_wrapper(source: str) -> bool:
    return "Stage 23 backtesting shim for selected trade sequence" in source


def top_level_functions(source: str) -> list[str]:
    tree = ast.parse(source)
    funcs = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs.append((node.lineno, node.name))
    return [name for _, name in sorted(funcs)]


def module_name(path: Path) -> str:
    return rel(path).replace("src/signalforge/", "signalforge/").replace("/", ".").removesuffix(".py")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    CORE_PACKAGE.mkdir(parents=True, exist_ok=True)

    init_path = CORE_PACKAGE / "__init__.py"
    if not init_path.exists():
        write(init_path, "")

    if not SOURCE.exists():
        raise FileNotFoundError(f"Missing Stage 23 source builder: {SOURCE}")

    current_source = read(SOURCE)
    backup_path = OUT / "portfolio_selected_trade_sequence.py.before_stage40c7b"

    if is_stage23_wrapper(current_source):
        if not backup_path.exists():
            raise RuntimeError(
                "Stage 23 source already appears to be a wrapper, but no Stage 40C7B backup exists."
            )
        original_source = read(backup_path)
    else:
        original_source = current_source
        write(backup_path, original_source)

    function_names = top_level_functions(original_source)

    core_source = (
        "# Auto-promoted by Stage 40C7B.\n"
        "# Core engine for Stage 23 selected trade sequence construction.\n"
        "# Backtesting should call this module instead of owning selected-trade-sequence logic.\n\n"
        + original_source.rstrip()
        + "\n"
    )

    core_module = module_name(CORE)

    wrapper_lines = [
        "from __future__ import annotations",
        "",
        '"""Stage 23 backtesting shim for selected trade sequence.',
        "",
        "The implementation has been promoted to:",
        core_module,
        "",
        "This file remains so existing backtesting imports and CLI commands keep working.",
        '"""',
        "",
        f"import {core_module} as _core",
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

    write(CORE, core_source)
    write(SOURCE, wrapper_source)

    summary = {
        "adapter_type": "stage40c7b_selected_trade_sequence_core_promotion_patcher",
        "artifact_type": "signalforge_stage40c7b_selected_trade_sequence_core_promotion",
        "contract": "stage40c7b_selected_trade_sequence_core_promotion",
        "is_ready": True,
        "source": rel(SOURCE),
        "core_path": rel(CORE),
        "core_package": rel(CORE_PACKAGE),
        "core_init_path": rel(init_path),
        "backup_path": rel(backup_path),
        "promoted_function_count": len(function_names),
        "promoted_functions": function_names,
        "paths": {
            "summary_path": "artifacts/stage40c7b_selected_trade_sequence_core_promotion/signalforge_stage40c7b_selected_trade_sequence_core_promotion_summary.json",
            "backup_path": "artifacts/stage40c7b_selected_trade_sequence_core_promotion/portfolio_selected_trade_sequence.py.before_stage40c7b",
        },
    }

    write(
        OUT / "signalforge_stage40c7b_selected_trade_sequence_core_promotion_summary.json",
        json.dumps(summary, indent=2, sort_keys=True),
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
