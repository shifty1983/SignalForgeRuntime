from __future__ import annotations

import ast
import json
from pathlib import Path


REPO = Path(".").resolve()
OUT = REPO / "artifacts/stage40c4b_expectancy_core_promotion"

PROMOTIONS = [
    {
        "source": REPO / "src/signalforge/backtesting/walk_forward_expectancy_builder.py",
        "core": REPO / "src/signalforge/engines/strategy_selection/expectancy.py",
        "marker": "Stage 18 backtesting shim for walk-forward expectancy",
        "label": "walk_forward_expectancy",
    },
    {
        "source": REPO / "src/signalforge/backtesting/walk_forward_expectancy_availability_safe_builder.py",
        "core": REPO / "src/signalforge/engines/strategy_selection/expectancy_availability_safe.py",
        "marker": "Stage 18 backtesting shim for availability-safe walk-forward expectancy",
        "label": "walk_forward_expectancy_availability_safe",
    },
]


def rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


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


def promote_one(spec: dict) -> dict:
    source_path: Path = spec["source"]
    core_path: Path = spec["core"]
    marker: str = spec["marker"]
    label: str = spec["label"]

    if not source_path.exists():
        raise FileNotFoundError(f"Missing Stage 18 source builder: {source_path}")

    current_source = read(source_path)
    backup_path = OUT / f"{source_path.name}.before_stage40c4b"

    if marker in current_source:
        if not backup_path.exists():
            raise RuntimeError(
                f"{rel(source_path)} already appears to be a wrapper, but no backup exists."
            )
        original_source = read(backup_path)
    else:
        original_source = current_source
        write(backup_path, original_source)

    function_names = top_level_functions(original_source)

    core_source = (
        "# Auto-promoted by Stage 40C4B.\n"
        f"# Core engine for Stage 18 {label}.\n"
        "# Backtesting should call this module instead of owning expectancy logic.\n\n"
        + original_source.rstrip()
        + "\n"
    )

    module_name = rel(core_path).replace("src/signalforge/", "signalforge/").replace("/", ".").removesuffix(".py")

    wrapper_lines = [
        "from __future__ import annotations",
        "",
        f'"""{marker}.',
        "",
        "The implementation has been promoted to:",
        module_name,
        "",
        "This file remains for existing CLI/artifact compatibility.",
        '"""',
        "",
        f"import {module_name} as _core",
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

    write(core_path, core_source)
    write(source_path, wrapper_source)

    return {
        "label": label,
        "source": rel(source_path),
        "core": rel(core_path),
        "backup": rel(backup_path),
        "promoted_function_count": len(function_names),
        "promoted_functions": function_names,
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    reports = [promote_one(spec) for spec in PROMOTIONS]

    summary = {
        "adapter_type": "stage40c4b_expectancy_core_promotion_patcher",
        "artifact_type": "signalforge_stage40c4b_expectancy_core_promotion",
        "contract": "stage40c4b_expectancy_core_promotion",
        "is_ready": True,
        "promotion_count": len(reports),
        "promotions": reports,
        "paths": {
            "summary_path": "artifacts/stage40c4b_expectancy_core_promotion/signalforge_stage40c4b_expectancy_core_promotion_summary.json",
        },
    }

    write(
        OUT / "signalforge_stage40c4b_expectancy_core_promotion_summary.json",
        json.dumps(summary, indent=2, sort_keys=True),
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
