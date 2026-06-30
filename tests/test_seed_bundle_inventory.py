from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from signalforge.data.seed_bundle import (
    REQUIRED_DIRECTORIES,
    REQUIRED_FILES,
    build_seed_bundle_inventory,
    resolve_seed_bundle_root,
)


def rel_path(value: str) -> Path:
    return Path(*value.replace("\\", "/").split("/"))


def test_missing_seed_bundle_reports_not_ready(tmp_path: Path):
    missing_root = tmp_path / "does_not_exist"

    inventory = build_seed_bundle_inventory(missing_root)

    assert not inventory.is_ready
    assert inventory.bundle_root is None
    assert inventory.missing_directory_count == len(REQUIRED_DIRECTORIES)
    assert inventory.missing_file_count == len(REQUIRED_FILES)


def test_minimal_complete_seed_bundle_reports_ready():
    # Use a short repo-local temp path because Windows temp paths can exceed
    # MAX_PATH once long artifact names are appended.
    root = Path(".tmp_seed_bundle_test")

    if root.exists():
        shutil.rmtree(root)

    try:
        root.mkdir()

        for rel_dir in REQUIRED_DIRECTORIES:
            (root / rel_path(rel_dir)).mkdir(parents=True, exist_ok=True)

        for rel_file in REQUIRED_FILES:
            file_path = root / rel_path(rel_file)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text("{}", encoding="utf-8")

        inventory = build_seed_bundle_inventory(root)

        assert inventory.is_ready
        assert inventory.bundle_root == str(root)
        assert inventory.missing_directory_count == 0
        assert inventory.missing_file_count == 0
        assert inventory.file_count >= len(REQUIRED_FILES)

    finally:
        if root.exists():
            shutil.rmtree(root)


def test_local_seed_bundle_is_ready_when_available():
    root = resolve_seed_bundle_root()

    if root is None:
        pytest.skip("No local V3.2.2 seed bundle found.")

    inventory = build_seed_bundle_inventory(root)

    assert inventory.is_ready
    assert inventory.missing_directory_count == 0
    assert inventory.missing_file_count == 0
    assert inventory.file_count > 0
    assert inventory.total_size_bytes > 0

