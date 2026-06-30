from __future__ import annotations

import argparse
import ast
import json
import shutil
from dataclasses import dataclass, asdict
from pathlib import Path


EXCLUDED_PREFIXES = (
    "src.backtesting",
    "src.live",
    "src.live_trading",
    "src.paper",
    "src.paper_trading",
    "src.runtime",
    "src.broker",
    "src.ibkr",
    "src.execution_runtime",
)

ALLOWED_PREFIX = "src."


@dataclass(frozen=True)
class ModuleRecord:
    module: str
    source_path: str
    target_path: str
    status: str


def module_to_candidates(old_root: Path, module: str) -> list[Path]:
    """
    Convert src.foo.bar into possible files:
      old_root/src/foo/bar.py
      old_root/src/foo/bar/__init__.py
    """
    rel = Path(*module.split("."))
    return [
        old_root / f"{rel}.py",
        old_root / rel / "__init__.py",
    ]


def path_to_module(old_root: Path, path: Path) -> str:
    rel = path.relative_to(old_root).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def resolve_module_path(old_root: Path, module: str) -> Path | None:
    for candidate in module_to_candidates(old_root, module):
        if candidate.exists():
            return candidate
    return None


def imports_from_file(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    found: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(ALLOWED_PREFIX):
                    found.add(alias.name)

        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith(ALLOWED_PREFIX):
                found.add(node.module)

    return found


def is_excluded(module: str) -> bool:
    return module.startswith(EXCLUDED_PREFIXES)


def ensure_package_inits(old_root: Path, new_root: Path, copied_paths: set[Path]) -> list[ModuleRecord]:
    records: list[ModuleRecord] = []

    for copied in list(copied_paths):
        rel = copied.relative_to(new_root)
        current = new_root / rel.parent

        while current != new_root:
            if current.name == "__pycache__":
                break

            init_target = current / "__init__.py"
            init_source = old_root / init_target.relative_to(new_root)

            if not init_target.exists():
                init_target.parent.mkdir(parents=True, exist_ok=True)

                init_target.write_text("", encoding="utf-8")
                status = "created_empty_package_init"

                records.append(
                    ModuleRecord(
                        module=path_to_module(new_root, init_target),
                        source_path=str(init_source),
                        target_path=str(init_target),
                        status=status,
                    )
                )

            current = current.parent

    return records


def collect_dependency_closure(old_root: Path, anchors: list[str]) -> tuple[set[str], list[ModuleRecord]]:
    queue = list(anchors)
    seen: set[str] = set()
    records: list[ModuleRecord] = []

    while queue:
        module = queue.pop(0)

        if module in seen:
            continue

        seen.add(module)

        if is_excluded(module):
            records.append(
                ModuleRecord(
                    module=module,
                    source_path="",
                    target_path="",
                    status="excluded_runtime_or_backtesting_dependency",
                )
            )
            continue

        source = resolve_module_path(old_root, module)

        if source is None:
            records.append(
                ModuleRecord(
                    module=module,
                    source_path="",
                    target_path="",
                    status="missing_source_file",
                )
            )
            continue

        records.append(
            ModuleRecord(
                module=module,
                source_path=str(source),
                target_path="",
                status="included",
            )
        )

        for imported in sorted(imports_from_file(source)):
            if imported not in seen:
                queue.append(imported)

    included = {r.module for r in records if r.status == "included"}
    return included, records


def copy_modules(old_root: Path, new_root: Path, modules: set[str], apply: bool) -> list[ModuleRecord]:
    records: list[ModuleRecord] = []
    copied_paths: set[Path] = set()

    for module in sorted(modules):
        source = resolve_module_path(old_root, module)
        if source is None:
            continue

        target = new_root / source.relative_to(old_root)

        if apply:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied_paths.add(target)
            status = "copied"
        else:
            status = "dry_run_would_copy"

        records.append(
            ModuleRecord(
                module=module,
                source_path=str(source),
                target_path=str(target),
                status=status,
            )
        )

    if apply:
        records.extend(ensure_package_inits(old_root, new_root, copied_paths))

    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--old-root", required=True)
    parser.add_argument("--new-root", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--anchor",
        action="append",
        required=True,
        help="Python module path, for example src.signalforge.engines.strategy_selection.strategy_family_eligibility",
    )
    parser.add_argument(
        "--inventory-out",
        default="artifacts/engine_stack_migration_inventory.json",
    )

    args = parser.parse_args()

    old_root = Path(args.old_root).resolve()
    new_root = Path(args.new_root).resolve()

    modules, dependency_records = collect_dependency_closure(old_root, args.anchor)
    copy_records = copy_modules(old_root, new_root, modules, args.apply)

    inventory = {
        "migration_scope": "deterministic_engine_stack_from_strategy_family_eligibility_anchor",
        "old_root": str(old_root),
        "new_root": str(new_root),
        "apply": args.apply,
        "anchors": args.anchor,
        "included_module_count": len(modules),
        "dependency_records": [asdict(r) for r in dependency_records],
        "copy_records": [asdict(r) for r in copy_records],
        "excluded_records": [
            asdict(r)
            for r in dependency_records
            if r.status == "excluded_runtime_or_backtesting_dependency"
        ],
        "missing_records": [
            asdict(r)
            for r in dependency_records
            if r.status == "missing_source_file"
        ],
    }

    inventory_path = new_root / args.inventory_out
    inventory_path.parent.mkdir(parents=True, exist_ok=True)
    inventory_path.write_text(json.dumps(inventory, indent=2), encoding="utf-8")

    print(json.dumps({
        "is_ready": True,
        "apply": args.apply,
        "included_module_count": len(modules),
        "excluded_dependency_count": len(inventory["excluded_records"]),
        "missing_dependency_count": len(inventory["missing_records"]),
        "inventory_path": str(inventory_path),
    }, indent=2))


if __name__ == "__main__":
    main()
