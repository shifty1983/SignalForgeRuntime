from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_OLD_REPO = r"C:\Users\02011715\Documents\SignalForge\raw_data_layer"
DEFAULT_SEED_ROOT = r"C:\Users\02011715\Documents\SignalForge_v3_2_2_seed_bundle_20260628_180919"
DEFAULT_OUTPUT_ROOT = "legacy/source_snapshots/v3_2_2"


@dataclass(frozen=True)
class SnapshotFileRecord:
    source_type: str
    source_path: str
    snapshot_path: str
    relative_path: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class SourceSnapshotSummary:
    snapshot_root: str
    old_repo: str
    seed_root: str
    old_src_file_count: int
    artifact_builder_file_count: int
    copied_file_count: int
    manifest_path: str
    is_ready: bool
    blocker_count: int
    blockers: tuple[str, ...]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def copy_file(source: Path, destination: Path, source_type: str, relative_path: str) -> SnapshotFileRecord:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)

    return SnapshotFileRecord(
        source_type=source_type,
        source_path=str(source),
        snapshot_path=str(destination),
        relative_path=relative_path,
        size_bytes=destination.stat().st_size,
        sha256=sha256_file(destination),
    )


def iter_python_files(root: Path) -> Iterable[Path]:
    yield from sorted(root.rglob("*.py"))


def build_source_snapshot(
    *,
    old_repo: str | Path = DEFAULT_OLD_REPO,
    seed_root: str | Path = DEFAULT_SEED_ROOT,
    output_root: str | Path = DEFAULT_OUTPUT_ROOT,
) -> SourceSnapshotSummary:
    old_repo = Path(old_repo)
    old_src = old_repo / "src"
    seed_root = Path(seed_root)
    seed_artifacts = seed_root / "artifacts"
    output_root = Path(output_root)

    blockers: list[str] = []

    if not old_repo.is_dir():
        blockers.append("old_repo_missing")

    if not old_src.is_dir():
        blockers.append("old_src_missing")

    if not seed_root.is_dir():
        blockers.append("seed_root_missing")

    if not seed_artifacts.is_dir():
        blockers.append("seed_artifacts_missing")

    if blockers:
        return SourceSnapshotSummary(
            snapshot_root=str(output_root),
            old_repo=str(old_repo),
            seed_root=str(seed_root),
            old_src_file_count=0,
            artifact_builder_file_count=0,
            copied_file_count=0,
            manifest_path=str(output_root / "source_snapshot_manifest.json"),
            is_ready=False,
            blocker_count=len(blockers),
            blockers=tuple(blockers),
        )

    if output_root.exists():
        shutil.rmtree(output_root)

    old_src_files = list(iter_python_files(old_src))
    artifact_builder_files = list(iter_python_files(seed_artifacts))

    records: list[SnapshotFileRecord] = []

    for source in old_src_files:
        relative = source.relative_to(old_repo).as_posix()
        destination = output_root / "old_repo" / relative
        records.append(copy_file(source, destination, "old_repo_src_module", relative))

    for source in artifact_builder_files:
        relative = source.relative_to(seed_root).as_posix()
        destination = output_root / "artifact_builders" / relative
        records.append(copy_file(source, destination, "artifact_embedded_builder", relative))

    manifest_path = output_root / "source_snapshot_manifest.json"
    readme_path = output_root / "README.md"

    summary = SourceSnapshotSummary(
        snapshot_root=str(output_root),
        old_repo=str(old_repo),
        seed_root=str(seed_root),
        old_src_file_count=len(old_src_files),
        artifact_builder_file_count=len(artifact_builder_files),
        copied_file_count=len(records),
        manifest_path=str(manifest_path),
        is_ready=True,
        blocker_count=0,
        blockers=(),
    )

    manifest = {
        "summary": asdict(summary),
        "records": [asdict(record) for record in records],
    }

    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    readme_path.write_text(
        "\n".join(
            [
                "# SignalForge V3.2.2 Source Snapshot",
                "",
                "This folder preserves the legacy source files used to create the locked V3.2.2 backtesting artifacts.",
                "",
                "These files are intentionally stored as a snapshot first, before refactoring.",
                "",
                "## Contents",
                "",
                "- `old_repo/src/`: source modules from `SignalForge/raw_data_layer/src`.",
                "- `artifact_builders/artifacts/`: embedded artifact-builder scripts from the V3.2.2 seed bundle.",
                "- `source_snapshot_manifest.json`: copied-file manifest with SHA-256 hashes.",
                "",
                "## Migration role",
                "",
                "- Backtesting engines will be migrated into `src/signalforge/backtesting/`.",
                "- Reusable decision engines will be extracted into `src/signalforge/engines/`.",
                "- Runtime paper-trading orchestration will call the reusable engines, not the legacy snapshot directly.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    return summary


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Snapshot SignalForge legacy source files.")
    parser.add_argument("--old-repo", default=DEFAULT_OLD_REPO)
    parser.add_argument("--seed-root", default=DEFAULT_SEED_ROOT)
    parser.add_argument("--output-root", default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    summary = build_source_snapshot(
        old_repo=args.old_repo,
        seed_root=args.seed_root,
        output_root=args.output_root,
    )

    payload = asdict(summary)

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for key, value in payload.items():
            print(f"{key}: {value}")

    return 0 if summary.is_ready else 2


if __name__ == "__main__":
    raise SystemExit(main())




