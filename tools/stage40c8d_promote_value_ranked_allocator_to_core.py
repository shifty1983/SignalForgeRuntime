from __future__ import annotations

import ast
import json
from pathlib import Path


REPO = Path(".").resolve()
OUT = REPO / "artifacts/stage40c8d_value_ranked_allocator_core_promotion"

CORE_PACKAGE = REPO / "src/signalforge/engines/portfolio_construction"

PROMOTIONS = [
    {
        "label": "value_ranked_allocator_v2",
        "source": REPO / "src/signalforge/backtesting/portfolio_value_ranked_allocator_v2.py",
        "core": REPO / "src/signalforge/engines/portfolio_construction/value_ranked_allocator_v2.py",
        "marker": "Stage 24A backtesting shim for value-ranked allocator v2",
        "wrapper_mode": "function_wrappers",
    },
    {
        "label": "value_ranked_allocator_current",
        "source": REPO / "src/signalforge/backtesting/portfolio_value_ranked_allocator_v2_1_cli.py",
        "core": REPO / "src/signalforge/engines/portfolio_construction/value_ranked_allocator.py",
        "marker": "Stage 24A backtesting shim for value-ranked allocator",
        "wrapper_mode": "cli_star_wrapper",
    },
]


IMPORT_REPLACEMENTS = {
    "signalforge.backtesting.portfolio_value_ranked_allocator_v2": "signalforge.engines.portfolio_construction.value_ranked_allocator_v2",
    "src.signalforge.backtesting.portfolio_value_ranked_allocator_v2": "src.signalforge.engines.portfolio_construction.value_ranked_allocator_v2",
}


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


def module_name(path: Path) -> str:
    return rel(path).replace("src/signalforge/", "signalforge/").replace("/", ".").removesuffix(".py")


def apply_core_import_replacements(source: str) -> str:
    out = source
    for old, new in IMPORT_REPLACEMENTS.items():
        out = out.replace(old, new)
    return out


def is_wrapper(source: str, marker: str) -> bool:
    return marker in source


def function_wrapper_source(marker: str, core_module: str, function_names: list[str]) -> str:
    lines = [
        "from __future__ import annotations",
        "",
        f'"""{marker}.',
        "",
        "The implementation has been promoted to:",
        core_module,
        "",
        "This file remains so existing backtesting imports keep working.",
        '"""',
        "",
        f"import {core_module} as _core",
        "",
        "",
    ]

    for name in function_names:
        lines.extend(
            [
                f"def {name}(*args, **kwargs):",
                f"    return _core.{name}(*args, **kwargs)",
                "",
                "",
            ]
        )

    lines.extend(
        [
            "__all__ = [",
            *[f'    "{name}",' for name in function_names],
            "]",
            "",
        ]
    )

    return "\n".join(lines).rstrip() + "\n"


def cli_star_wrapper_source(marker: str, core_module: str) -> str:
    return f'''from __future__ import annotations

"""{marker}.

The implementation has been promoted to:
{core_module}

This file remains so existing CLI commands keep working.
"""

from {core_module} import *  # noqa: F401,F403
from signalforge.engines.portfolio_construction import value_ranked_allocator as _core


if __name__ == "__main__":
    raise SystemExit(_core.main())
'''


def promote_one(spec: dict) -> dict:
    source_path: Path = spec["source"]
    core_path: Path = spec["core"]
    marker: str = spec["marker"]
    label: str = spec["label"]

    if not source_path.exists():
        raise FileNotFoundError(f"Missing source file for {label}: {source_path}")

    current_source = read(source_path)
    backup_path = OUT / f"{source_path.name}.before_stage40c8d"

    if is_wrapper(current_source, marker):
        if not backup_path.exists():
            raise RuntimeError(
                f"{rel(source_path)} already appears to be a wrapper, but no backup exists."
            )
        original_source = read(backup_path)
    else:
        original_source = current_source
        write(backup_path, original_source)

    function_names = top_level_functions(original_source)
    core_module = module_name(core_path)

    core_source = (
        "# Auto-promoted by Stage 40C8D.\n"
        f"# Core engine for Stage 24A {label}.\n"
        "# Backtesting should call this module instead of owning value-ranked allocation logic.\n\n"
        + apply_core_import_replacements(original_source).rstrip()
        + "\n"
    )

    if spec["wrapper_mode"] == "function_wrappers":
        wrapper_source = function_wrapper_source(marker, core_module, function_names)
    elif spec["wrapper_mode"] == "cli_star_wrapper":
        wrapper_source = cli_star_wrapper_source(marker, core_module)
    else:
        raise ValueError(f"Unknown wrapper mode: {spec['wrapper_mode']}")

    write(core_path, core_source)
    write(source_path, wrapper_source)

    return {
        "label": label,
        "source": rel(source_path),
        "core_path": rel(core_path),
        "backup_path": rel(backup_path),
        "wrapper_mode": spec["wrapper_mode"],
        "promoted_function_count": len(function_names),
        "promoted_functions": function_names,
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    CORE_PACKAGE.mkdir(parents=True, exist_ok=True)

    init_path = CORE_PACKAGE / "__init__.py"
    if not init_path.exists():
        write(init_path, "")

    reports = [promote_one(spec) for spec in PROMOTIONS]

    summary = {
        "adapter_type": "stage40c8d_value_ranked_allocator_core_promotion_patcher",
        "artifact_type": "signalforge_stage40c8d_value_ranked_allocator_core_promotion",
        "contract": "stage40c8d_value_ranked_allocator_core_promotion",
        "is_ready": True,
        "promotion_count": len(reports),
        "core_package": rel(CORE_PACKAGE),
        "core_init_path": rel(init_path),
        "promotions": reports,
        "paths": {
            "summary_path": "artifacts/stage40c8d_value_ranked_allocator_core_promotion/signalforge_stage40c8d_value_ranked_allocator_core_promotion_summary.json",
        },
    }

    write(
        OUT / "signalforge_stage40c8d_value_ranked_allocator_core_promotion_summary.json",
        json.dumps(summary, indent=2, sort_keys=True),
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
