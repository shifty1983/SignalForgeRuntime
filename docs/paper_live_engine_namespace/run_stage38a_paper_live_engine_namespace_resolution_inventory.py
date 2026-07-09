import importlib
import json
import py_compile
from pathlib import Path
from typing import Any, Dict, List


OUT_DIR = Path("docs/paper_live_engine_namespace")

ROLE_FILES = {
    "candidate_ingestion_adapter": "candidate_ingestion_adapter.py",
    "legacy_domain_facade": "legacy_domain_facade.py",
    "legacy_domain_snapshot_adapter": "legacy_domain_snapshot_adapter.py",
}

SEARCH_ROOTS = [
    Path("src/paper_live_engine"),
    Path("src/signalforge/paper_live_engine"),
    Path("src/signalforge/engines/paper_live_engine"),
    Path("src/signalforge/engines/paper_live"),
    Path("src"),
]

IMPORT_CANDIDATES = {
    "candidate_ingestion_adapter": [
        "paper_live_engine.candidate_ingestion_adapter",
        "signalforge.paper_live_engine.candidate_ingestion_adapter",
        "signalforge.engines.paper_live_engine.candidate_ingestion_adapter",
        "signalforge.engines.paper_live.candidate_ingestion_adapter",
    ],
    "legacy_domain_facade": [
        "paper_live_engine.legacy_domain_facade",
        "signalforge.paper_live_engine.legacy_domain_facade",
        "signalforge.engines.paper_live_engine.legacy_domain_facade",
        "signalforge.engines.paper_live.legacy_domain_facade",
    ],
    "legacy_domain_snapshot_adapter": [
        "paper_live_engine.legacy_domain_snapshot_adapter",
        "signalforge.paper_live_engine.legacy_domain_snapshot_adapter",
        "signalforge.engines.paper_live_engine.legacy_domain_snapshot_adapter",
        "signalforge.engines.paper_live.legacy_domain_snapshot_adapter",
    ],
}


def import_check(role: str, module_name: str) -> dict[str, Any]:
    try:
        module = importlib.import_module(module_name)
        return {
            "role": role,
            "module": module_name,
            "ok": True,
            "error_type": None,
            "error": None,
            "module_file": getattr(module, "__file__", None),
        }
    except Exception as exc:
        return {
            "role": role,
            "module": module_name,
            "ok": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "module_file": None,
        }


def compile_check(path: Path) -> dict[str, Any]:
    try:
        py_compile.compile(str(path), doraise=True)
        return {
            "path": str(path),
            "compile_ok": True,
            "compile_error": None,
        }
    except Exception as exc:
        return {
            "path": str(path),
            "compile_ok": False,
            "compile_error": str(exc),
        }


def package_row(root: Path) -> dict[str, Any]:
    return {
        "root": str(root),
        "exists": root.exists(),
        "is_dir": root.is_dir(),
        "init_exists": (root / "__init__.py").exists(),
        "python_file_count": len(list(root.glob("*.py"))) if root.exists() and root.is_dir() else 0,
    }


def main() -> None:
    blockers: List[str] = []
    warnings: List[str] = []

    package_rows = [package_row(root) for root in SEARCH_ROOTS]

    file_rows: List[Dict[str, Any]] = []
    compile_rows: List[Dict[str, Any]] = []

    for role, filename in ROLE_FILES.items():
        found_paths = sorted(set(Path("src").rglob(filename)))

        if not found_paths:
            warnings.append(f"role_file_not_found_{role}_{filename}")

        for path in found_paths:
            file_row = {
                "role": role,
                "filename": filename,
                "path": str(path),
                "exists": path.exists(),
                "parent": str(path.parent),
                "parent_init_exists": (path.parent / "__init__.py").exists(),
                "size_bytes": path.stat().st_size if path.exists() else None,
            }
            file_rows.append(file_row)
            compile_rows.append({
                "role": role,
                **compile_check(path),
            })

    import_rows = []

    for role, modules in IMPORT_CANDIDATES.items():
        for module_name in modules:
            import_rows.append(import_check(role, module_name))

    resolved_roles = sorted({
        row["role"]
        for row in import_rows
        if row["ok"] is True
    })

    found_file_roles = sorted({
        row["role"]
        for row in file_rows
        if row["exists"] is True
    })

    unresolved_import_roles = sorted(set(ROLE_FILES) - set(resolved_roles))
    missing_file_roles = sorted(set(ROLE_FILES) - set(found_file_roles))

    failed_compile_rows = [
        row for row in compile_rows
        if row["compile_ok"] is not True
    ]

    if failed_compile_rows:
        blockers.append(f"paper_live_bridge_compile_failures_{[row['path'] for row in failed_compile_rows]}")

    recommendation = (
        "create_or_restore_namespace_wrappers"
        if found_file_roles and unresolved_import_roles
        else "locate_or_rebuild_missing_bridge_modules"
        if missing_file_roles
        else "no_namespace_action_required"
    )

    warnings.append("stage38a_is_read_only_no_code_moved")
    warnings.append("optional_bridge_namespace_inventory_only")
    warnings.append("expectancy_handoff_is_closed_and_not_blocked_by_optional_bridge_namespace")

    summary = {
        "adapter_type": "paper_live_engine_namespace_resolution_inventory_builder",
        "artifact_type": "signalforge_paper_live_engine_namespace_resolution_inventory",
        "contract": "paper_live_engine_namespace_resolution_inventory",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "package_root_count": len(package_rows),
        "role_count": len(ROLE_FILES),
        "found_file_role_count": len(found_file_roles),
        "resolved_import_role_count": len(resolved_roles),
        "unresolved_import_roles": unresolved_import_roles,
        "missing_file_roles": missing_file_roles,
        "compile_row_count": len(compile_rows),
        "compile_ok_count": sum(1 for row in compile_rows if row["compile_ok"]),
        "recommendation": recommendation,
        "paper_order_created": False,
        "live_order_created": False,
        "live_trade_supported": False,
        "next_step": "stage38b_create_namespace_wrappers_or_restore_missing_bridge_modules",
    }

    summary_path = OUT_DIR / "signalforge_stage38a_paper_live_engine_namespace_resolution_inventory_summary.json"
    package_rows_path = OUT_DIR / "signalforge_stage38a_paper_live_engine_namespace_package_rows.jsonl"
    file_rows_path = OUT_DIR / "signalforge_stage38a_paper_live_engine_namespace_file_rows.jsonl"
    import_rows_path = OUT_DIR / "signalforge_stage38a_paper_live_engine_namespace_import_rows.jsonl"
    compile_rows_path = OUT_DIR / "signalforge_stage38a_paper_live_engine_namespace_compile_rows.jsonl"
    md_path = OUT_DIR / "signalforge_stage38a_paper_live_engine_namespace_resolution_inventory.md"

    summary_path.write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")

    for path, rows in [
        (package_rows_path, package_rows),
        (file_rows_path, file_rows),
        (import_rows_path, import_rows),
        (compile_rows_path, compile_rows),
    ]:
        with path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, default=str) + "\n")

    md = [
        "# Stage 38A Paper Live Engine Namespace Resolution Inventory",
        "",
        f"- is_ready: {summary['is_ready']}",
        f"- blocker_count: {summary['blocker_count']}",
        f"- found_file_role_count: {summary['found_file_role_count']} / {summary['role_count']}",
        f"- resolved_import_role_count: {summary['resolved_import_role_count']} / {summary['role_count']}",
        f"- unresolved_import_roles: `{summary['unresolved_import_roles']}`",
        f"- missing_file_roles: `{summary['missing_file_roles']}`",
        f"- compile_ok_count: {summary['compile_ok_count']} / {summary['compile_row_count']}",
        f"- recommendation: `{summary['recommendation']}`",
        f"- paper_order_created: {summary['paper_order_created']}",
        f"- live_order_created: {summary['live_order_created']}",
        f"- live_trade_supported: {summary['live_trade_supported']}",
    ]

    if blockers:
        md.extend(["", "## Blockers", ""])
        for blocker in blockers:
            md.append(f"- {blocker}")

    if warnings:
        md.extend(["", "## Warnings", ""])
        for warning in warnings:
            md.append(f"- {warning}")

    md_path.write_text("\n".join(md), encoding="utf-8")

    print("\n--- Stage 38A paper live engine namespace resolution inventory compact ---")
    for key in [
        "is_ready",
        "blocker_count",
        "warning_count",
        "package_root_count",
        "role_count",
        "found_file_role_count",
        "resolved_import_role_count",
        "compile_row_count",
        "compile_ok_count",
        "recommendation",
        "paper_order_created",
        "live_order_created",
        "live_trade_supported",
    ]:
        print(f"{key}: {summary[key]}")

    print(f"summary_path: {summary_path}")
    print(f"package_rows_path: {package_rows_path}")
    print(f"file_rows_path: {file_rows_path}")
    print(f"import_rows_path: {import_rows_path}")
    print(f"compile_rows_path: {compile_rows_path}")
    print(f"md_path: {md_path}")

    print("\n--- Stage 38A package rows compact ---")
    print("root\texists\tis_dir\tinit_exists\tpython_file_count")
    for row in package_rows:
        print(f"{row['root']}\t{row['exists']}\t{row['is_dir']}\t{row['init_exists']}\t{row['python_file_count']}")

    print("\n--- Stage 38A file rows compact ---")
    print("role\tpath\tparent_init_exists\tsize_bytes")
    for row in file_rows:
        print(f"{row['role']}\t{row['path']}\t{row['parent_init_exists']}\t{row['size_bytes']}")

    print("\n--- Stage 38A import rows compact ---")
    print("role\tmodule\tok\terror\tfile")
    for row in import_rows:
        print(f"{row['role']}\t{row['module']}\t{row['ok']}\t{row['error']}\t{row['module_file']}")

    if blockers:
        print("\n--- Stage 38A blockers ---")
        for blocker in blockers:
            print(blocker)
        raise SystemExit(1)

    if warnings:
        print("\n--- Stage 38A warnings ---")
        for warning in warnings:
            print(warning)


if __name__ == "__main__":
    main()
