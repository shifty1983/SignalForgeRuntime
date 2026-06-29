from __future__ import annotations

import argparse
import ast
import hashlib
import json
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class ImportRecord:
    import_type: str
    module: str | None
    names: tuple[str, ...]
    level: int


@dataclass(frozen=True)
class SourceFileNode:
    relative_path: str
    module_name: str
    size_bytes: int
    sha256: str
    definitions: tuple[str, ...]
    imports: tuple[ImportRecord, ...]
    internal_dependencies: tuple[str, ...]
    missing_internal_dependencies: tuple[str, ...]


@dataclass(frozen=True)
class MigrationSourceGraphSummary:
    source_root: str
    targets: tuple[str, ...]
    node_count: int
    internal_dependency_count: int
    missing_internal_dependency_count: int
    external_import_count: int
    is_ready: bool
    blocker_count: int
    blockers: tuple[str, ...]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def _module_name_from_relative_path(relative_path: str) -> str:
    path = Path(relative_path)
    without_suffix = path.with_suffix("")
    parts = list(without_suffix.parts)

    if parts and parts[-1] == "__init__":
        parts = parts[:-1]

    return ".".join(parts)


def _relative_path_from_module(source_root: Path, module_name: str) -> str | None:
    if module_name.startswith("src."):
        module_name = module_name[4:]

    module_path = Path(*module_name.split("."))

    py_path = source_root / module_path.with_suffix(".py")

    if py_path.is_file():
        return py_path.relative_to(source_root).as_posix()

    init_path = source_root / module_path / "__init__.py"

    if init_path.is_file():
        return init_path.relative_to(source_root).as_posix()

    return None


def _resolve_relative_module(current_module: str, level: int, module: str | None) -> str | None:
    if level <= 0:
        return module

    package_parts = current_module.split(".")[:-1]

    if level > 1:
        package_parts = package_parts[: -(level - 1)]

    if module:
        package_parts.extend(module.split("."))

    if not package_parts:
        return None

    return ".".join(package_parts)


def _parse_imports(tree: ast.AST) -> tuple[ImportRecord, ...]:
    imports: list[ImportRecord] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(
                    ImportRecord(
                        import_type="import",
                        module=alias.name,
                        names=(),
                        level=0,
                    )
                )

        elif isinstance(node, ast.ImportFrom):
            imports.append(
                ImportRecord(
                    import_type="from",
                    module=node.module,
                    names=tuple(alias.name for alias in node.names),
                    level=node.level,
                )
            )

    return tuple(imports)


def _parse_definitions(tree: ast.AST) -> tuple[str, ...]:
    definitions: list[str] = []

    for node in getattr(tree, "body", []):
        if isinstance(node, ast.ClassDef):
            definitions.append(f"class:{node.name}")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            definitions.append(f"function:{node.name}")

    return tuple(definitions)


def _candidate_modules(import_record: ImportRecord, current_module: str) -> list[str]:
    candidates: list[str] = []

    base_module = _resolve_relative_module(
        current_module=current_module,
        level=import_record.level,
        module=import_record.module,
    )

    if base_module:
        candidates.append(base_module)

    if import_record.import_type == "from":
        for name in import_record.names:
            if name == "*":
                continue

            if base_module:
                candidates.append(f"{base_module}.{name}")
            elif import_record.level:
                relative_base = _resolve_relative_module(
                    current_module=current_module,
                    level=import_record.level,
                    module=None,
                )

                if relative_base:
                    candidates.append(f"{relative_base}.{name}")

    return candidates


def _analyze_file(source_root: Path, relative_path: str) -> SourceFileNode:
    source_path = source_root / relative_path
    text = source_path.read_text(encoding="utf-8-sig")
    tree = ast.parse(text, filename=str(source_path))

    module_name = _module_name_from_relative_path(relative_path)
    imports = _parse_imports(tree)

    internal_dependencies: set[str] = set()
    missing_internal_dependencies: set[str] = set()

    internal_prefixes = (
        "src.",
        "backtesting.",
        "regime.",
        "options.",
        "strategy_selection.",
        "strategy.",
        "strategies.",
        "expected_value.",
        "portfolio_construction.",
        "optimizer.",
    )

    for import_record in imports:
        candidates = _candidate_modules(import_record, module_name)
        resolved_dependencies: list[str] = []

        for candidate in candidates:
            resolved = _relative_path_from_module(source_root, candidate)

            if resolved and resolved != relative_path:
                resolved_dependencies.append(resolved)

        if resolved_dependencies:
            internal_dependencies.update(resolved_dependencies)
            continue

        primary_candidate = _resolve_relative_module(
            current_module=module_name,
            level=import_record.level,
            module=import_record.module,
        )

        if primary_candidate and primary_candidate.startswith(internal_prefixes):
            missing_internal_dependencies.add(primary_candidate)

    return SourceFileNode(
        relative_path=relative_path,
        module_name=module_name,
        size_bytes=source_path.stat().st_size,
        sha256=_sha256_file(source_path),
        definitions=_parse_definitions(tree),
        imports=imports,
        internal_dependencies=tuple(sorted(internal_dependencies)),
        missing_internal_dependencies=tuple(sorted(missing_internal_dependencies)),
    )


def build_migration_source_graph(
    *,
    source_root: str | Path,
    targets: Iterable[str],
) -> dict[str, Any]:
    source_root = Path(source_root)
    target_list = tuple(str(target).replace("\\", "/") for target in targets)

    blockers: list[str] = []

    if not source_root.is_dir():
        blockers.append("source_root_missing")

    missing_targets = [
        target
        for target in target_list
        if not (source_root / target).is_file()
    ]

    if missing_targets:
        blockers.append("target_files_missing")

    if blockers:
        summary = MigrationSourceGraphSummary(
            source_root=str(source_root),
            targets=target_list,
            node_count=0,
            internal_dependency_count=0,
            missing_internal_dependency_count=0,
            external_import_count=0,
            is_ready=False,
            blocker_count=len(blockers),
            blockers=tuple(blockers),
        )

        return {
            "summary": asdict(summary),
            "nodes": [],
            "missing_targets": missing_targets,
        }

    nodes: dict[str, SourceFileNode] = {}
    queue: deque[str] = deque(target_list)

    while queue:
        relative_path = queue.popleft()

        if relative_path in nodes:
            continue

        node = _analyze_file(source_root, relative_path)
        nodes[relative_path] = node

        for dependency in node.internal_dependencies:
            if dependency not in nodes:
                queue.append(dependency)

    internal_dependency_count = sum(len(node.internal_dependencies) for node in nodes.values())
    missing_internal_dependency_count = sum(len(node.missing_internal_dependencies) for node in nodes.values())

    external_import_count = 0

    for node in nodes.values():
        for import_record in node.imports:
            candidates = _candidate_modules(import_record, node.module_name)

            if not any(_relative_path_from_module(source_root, candidate) for candidate in candidates):
                external_import_count += 1

    summary = MigrationSourceGraphSummary(
        source_root=str(source_root),
        targets=target_list,
        node_count=len(nodes),
        internal_dependency_count=internal_dependency_count,
        missing_internal_dependency_count=missing_internal_dependency_count,
        external_import_count=external_import_count,
        is_ready=missing_internal_dependency_count == 0,
        blocker_count=1 if missing_internal_dependency_count else 0,
        blockers=("missing_internal_dependencies",) if missing_internal_dependency_count else (),
    )

    return {
        "summary": asdict(summary),
        "nodes": [asdict(nodes[key]) for key in sorted(nodes)],
        "missing_targets": [],
    }


def write_markdown_report(graph: dict[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    summary = graph["summary"]
    nodes = graph["nodes"]

    lines = [
        "# Historical Decision Rows Migration Source Graph",
        "",
        "## Summary",
        "",
        f"- Source root: `{summary['source_root']}`",
        f"- Targets: `{', '.join(summary['targets'])}`",
        f"- Node count: {summary['node_count']}",
        f"- Internal dependency count: {summary['internal_dependency_count']}",
        f"- Missing internal dependency count: {summary['missing_internal_dependency_count']}",
        f"- External import count: {summary['external_import_count']}",
        f"- Is ready: {summary['is_ready']}",
        "",
        "## Files in migration cut",
        "",
    ]

    for node in nodes:
        lines.append(f"### `{node['relative_path']}`")
        lines.append("")
        lines.append(f"- Module: `{node['module_name']}`")
        lines.append(f"- Size bytes: {node['size_bytes']}")
        lines.append(f"- SHA-256: `{node['sha256']}`")
        lines.append(f"- Definitions: {', '.join(node['definitions']) if node['definitions'] else '(none)'}")
        lines.append(f"- Internal dependencies: {len(node['internal_dependencies'])}")
        lines.append(f"- Missing internal dependencies: {len(node['missing_internal_dependencies'])}")

        if node["internal_dependencies"]:
            lines.append("")
            lines.append("Internal dependencies:")
            for dependency in node["internal_dependencies"]:
                lines.append(f"- `{dependency}`")

        if node["missing_internal_dependencies"]:
            lines.append("")
            lines.append("Missing internal dependencies:")
            for dependency in node["missing_internal_dependencies"]:
                lines.append(f"- `{dependency}`")

        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")

    return path


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze a legacy source migration dependency graph.")
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--targets", nargs="+", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--markdown", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    graph = build_migration_source_graph(
        source_root=args.source_root,
        targets=args.targets,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(graph, indent=2, sort_keys=True), encoding="utf-8")

    write_markdown_report(graph, args.markdown)

    if args.json:
        print(json.dumps(graph["summary"], indent=2, sort_keys=True))
    else:
        for key, value in graph["summary"].items():
            print(f"{key}: {value}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
