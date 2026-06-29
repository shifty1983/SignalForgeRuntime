# SignalForge V3.2.2 Source Snapshot

This folder preserves the legacy source files used to create the locked V3.2.2 backtesting artifacts.

These files are intentionally stored as a snapshot first, before refactoring.

## Contents

- `old_repo/src/`: source modules from `SignalForge/raw_data_layer/src`.
- `artifact_builders/artifacts/`: embedded artifact-builder scripts from the V3.2.2 seed bundle.
- `source_snapshot_manifest.json`: copied-file manifest with SHA-256 hashes.

## Migration role

- Backtesting engines will be migrated into `src/signalforge/backtesting/`.
- Reusable decision engines will be extracted into `src/signalforge/engines/`.
- Runtime paper-trading orchestration will call the reusable engines, not the legacy snapshot directly.
