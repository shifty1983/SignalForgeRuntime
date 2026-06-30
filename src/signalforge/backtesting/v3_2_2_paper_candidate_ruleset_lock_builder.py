from __future__ import annotations

import base64
import os
from pathlib import Path


OUT_DIR = Path(os.environ.get(
    "SIGNALFORGE_V3_2_2_PAPER_CANDIDATE_RULESET_LOCK_OUT_DIR",
    "artifacts/v3_2_2_paper_candidate_ruleset_lock_20230101_20260531",
))

SOURCE_MIRROR_DIR = Path(os.environ.get(
    "SIGNALFORGE_V3_2_2_PAPER_CANDIDATE_RULESET_LOCK_SOURCE_MIRROR_DIR",
    "artifacts/migrated_workflow_dry_run_20210601_20260531/stage1_artifact_mirror/17b_v3_2_2_paper_candidate_ruleset_lock",
))

LOCK_JSON_PATH = OUT_DIR / "signalforge_v3_2_2_paper_candidate_ruleset_lock.json"
LOCK_MD_PATH = OUT_DIR / "signalforge_v3_2_2_paper_candidate_ruleset_lock.md"

SOURCE_LOCK_JSON = SOURCE_MIRROR_DIR / "v3_2_2_paper_candidate_ruleset_lock.json"
SOURCE_LOCK_MD = SOURCE_MIRROR_DIR / "v3_2_2_paper_candidate_ruleset_lock.md"


def _copy_bytes(source: Path, destination: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(f"missing canonical Stage 20 lock source: {source}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(source.read_bytes())


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    _copy_bytes(SOURCE_LOCK_JSON, LOCK_JSON_PATH)
    _copy_bytes(SOURCE_LOCK_MD, LOCK_MD_PATH)

    print(LOCK_JSON_PATH.read_text(encoding="utf-8-sig"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
