from __future__ import annotations

from signalforge.backtesting.migrated_workflow_artifact_paths import (
    build_exact_artifact_path_manifest,
)


def test_exact_artifact_path_manifest_builds():
    manifest = build_exact_artifact_path_manifest()

    assert manifest["adapter_type"] == "migrated_workflow_exact_artifact_path_manifest_builder"
    assert "groups" in manifest
    assert "blockers" in manifest




