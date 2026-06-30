from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path


MOVE_MAP = {
    "src/alignment": "src/signalforge/engines/alignment",
    "src/behavior": "src/signalforge/engines/behavior",
    "src/options": "src/signalforge/engines/options",
    "src/regime": "src/signalforge/engines/regime",
    "src/strategy_selection": "src/signalforge/engines/strategy_selection",
    "src/data_sources": "src/signalforge/data_sources",
}

IMPORT_REPLACEMENTS = [
    (r"\bfrom src\.alignment\b", "from src.signalforge.engines.alignment"),
    (r"\bimport src\.alignment\b", "import src.signalforge.engines.alignment"),
    (r"\bsrc\.alignment\.", "src.signalforge.engines.alignment."),

    (r"\bfrom src\.behavior\b", "from src.signalforge.engines.behavior"),
    (r"\bimport src\.behavior\b", "import src.signalforge.engines.behavior"),
    (r"\bsrc\.behavior\.", "src.signalforge.engines.behavior."),

    (r"\bfrom src\.options\b", "from src.signalforge.engines.options"),
    (r"\bimport src\.options\b", "import src.signalforge.engines.options"),
    (r"\bsrc\.options\.", "src.signalforge.engines.options."),

    (r"\bfrom src\.regime\b", "from src.signalforge.engines.regime"),
    (r"\bimport src\.regime\b", "import src.signalforge.engines.regime"),
    (r"\bsrc\.regime\.", "src.signalforge.engines.regime."),

    (r"\bfrom src\.strategy_selection\b", "from src.signalforge.engines.strategy_selection"),
    (r"\bimport src\.strategy_selection\b", "import src.signalforge.engines.strategy_selection"),
    (r"\bsrc\.strategy_selection\.", "src.signalforge.engines.strategy_selection."),

    (r"\bfrom src\.data_sources\b", "from src.signalforge.data_sources"),
    (r"\bimport src\.data_sources\b", "import src.signalforge.data_sources"),
    (r"\bsrc\.data_sources\.", "src.signalforge.data_sources."),
]


def iter_python_files(root: Path) -> list[Path]:
    ignored_parts = {".git", ".venv", "__pycache__", "artifacts"}
    files = []
    for path in root.rglob("*.py"):
        if any(part in ignored_parts for part in path.parts):
            continue
        files.append(path)
    return files


def ensure_init_files(path: Path) -> list[str]:
    created = []
    current = path
    while current.name != "src" and current.parent != current:
        init = current / "__init__.py"
        if not init.exists():
            init.write_text("", encoding="utf-8")
            created.append(str(init))
        current = current.parent
    return created


def move_tree(root: Path, source_rel: str, target_rel: str, apply: bool) -> dict:
    source = root / source_rel
    target = root / target_rel

    record = {
        "source": str(source),
        "target": str(target),
        "source_exists": source.exists(),
        "target_exists": target.exists(),
        "collisions": [],
        "moved_files": [],
        "created_init_files": [],
        "status": "not_started",
    }

    if not source.exists():
        record["status"] = "source_missing_skip"
        return record

    for src_file in source.rglob("*"):
        if not src_file.is_file():
            continue
        if "__pycache__" in src_file.parts:
            continue

        rel = src_file.relative_to(source)
        dst_file = target / rel

        if dst_file.exists():
            try:
                same = src_file.read_bytes() == dst_file.read_bytes()
            except OSError:
                same = False

            if not same:
                record["collisions"].append({
                    "source_file": str(src_file),
                    "target_file": str(dst_file),
                })

    if record["collisions"]:
        record["status"] = "blocked_by_collisions"
        return record

    if not apply:
        record["status"] = "dry_run_would_move"
        return record

    target.mkdir(parents=True, exist_ok=True)

    for src_file in source.rglob("*"):
        if not src_file.is_file():
            continue
        if "__pycache__" in src_file.parts:
            continue

        rel = src_file.relative_to(source)
        dst_file = target / rel
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src_file), str(dst_file))
        record["moved_files"].append(str(dst_file))

    # Remove empty source directories.
    for folder in sorted(source.rglob("*"), reverse=True):
        if folder.is_dir():
            try:
                folder.rmdir()
            except OSError:
                pass
    try:
        source.rmdir()
    except OSError:
        pass

    record["created_init_files"].extend(ensure_init_files(target))
    record["status"] = "moved"
    return record


def rewrite_imports(root: Path, apply: bool) -> list[dict]:
    records = []

    for path in iter_python_files(root):
        text = path.read_text(encoding="utf-8-sig")
        updated = text

        for pattern, replacement in IMPORT_REPLACEMENTS:
            updated = re.sub(pattern, replacement, updated)

        if updated != text:
            records.append({
                "path": str(path),
                "status": "updated" if apply else "dry_run_would_update",
            })
            if apply:
                path.write_text(updated, encoding="utf-8")

    return records


def remove_pycache(root: Path, apply: bool) -> list[dict]:
    records = []
    for path in root.rglob("__pycache__"):
        if path.is_dir():
            records.append({
                "path": str(path),
                "status": "removed" if apply else "dry_run_would_remove",
            })
            if apply:
                shutil.rmtree(path, ignore_errors=True)
    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--out", default="artifacts/refactor/clean_namespace_refactor_inventory.json")
    args = parser.parse_args()

    root = Path(args.root).resolve()

    move_records = [
        move_tree(root, source, target, args.apply)
        for source, target in MOVE_MAP.items()
    ]

    blocked = [
        record for record in move_records
        if record["status"] == "blocked_by_collisions"
    ]

    import_records = [] if blocked else rewrite_imports(root, args.apply)
    pycache_records = [] if blocked else remove_pycache(root, args.apply)

    inventory = {
        "artifact_type": "clean_namespace_refactor_inventory",
        "apply": args.apply,
        "root": str(root),
        "is_blocked": bool(blocked),
        "move_records": move_records,
        "import_rewrite_records": import_records,
        "pycache_records": pycache_records,
        "recommended_namespace": "src.signalforge",
    }

    out = root / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(inventory, indent=2), encoding="utf-8")

    print(json.dumps({
        "is_ready": not bool(blocked),
        "apply": args.apply,
        "blocked_move_count": len(blocked),
        "moved_or_planned_folder_count": len(move_records),
        "import_rewrite_count": len(import_records),
        "pycache_count": len(pycache_records),
        "inventory_path": str(out),
    }, indent=2))


if __name__ == "__main__":
    main()

