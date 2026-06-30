from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from signalforge.data.seed_bundle import resolve_seed_bundle_root


SEARCH_ROOTS: tuple[str, ...] = (
    "artifacts/v3_2_2_symbol_regime_walkforward_prune_stress_v1_20230101_20260531",
    "artifacts/qc_replay_5y_matrix_enriched_contract_outcomes",
    "artifacts/historical_decision_rows_20210601_20260531",
    "artifacts/v3_2_1_native_quote_pnl_stress_v1_20230101_20260531",
    "artifacts/v3_2_1_native_quote_join_v1_20230101_20260531",
)

FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "symbol": ("symbol", "underlying", "underlying_symbol", "ticker"),
    "regime_state": ("regime_state", "regime", "regime_type", "market_regime_state"),
    "entry_date": ("entry_date", "open_date", "signal_date", "decision_date", "date"),
    "close_date": ("close_date", "exit_date", "outcome_date", "close_or_outcome_date"),
    "pnl": ("pnl", "net_pnl", "total_pnl", "total_pnl_dollars", "realized_pnl", "native_quote_pnl"),
    "strategy": ("strategy", "strategy_family", "strategy_name", "strategy_structure"),
    "quantity": ("quantity", "contracts", "contract_count", "position_size"),
    "capital_label": ("capital_label", "account_label", "capital_scenario", "capital"),
}

REQUIRED_CANONICAL_FIELDS: tuple[str, ...] = tuple(FIELD_ALIASES.keys())


@dataclass(frozen=True)
class ClosedOutcomeFileCandidate:
    relative_path: str
    suffix: str
    size_bytes: int
    sampled_record_count: int
    matched_canonical_fields: tuple[str, ...]
    missing_canonical_fields: tuple[str, ...]
    field_score: int
    has_required_core_fields: bool
    read_warning: str | None


@dataclass(frozen=True)
class ClosedOutcomeDiscovery:
    seed_bundle_root: str | None
    is_ready: bool
    search_root_count: int
    existing_search_root_count: int
    candidate_file_count: int
    viable_candidate_count: int
    best_candidate: ClosedOutcomeFileCandidate | None
    candidates: tuple[ClosedOutcomeFileCandidate, ...]
    missing_search_roots: tuple[str, ...]


def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _iter_jsonl_records(path: Path, sample_limit: int) -> tuple[list[dict[str, Any]], str | None]:
    records: list[dict[str, Any]] = []
    warning: str | None = None

    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            for line in handle:
                if len(records) >= sample_limit:
                    break

                line = line.strip()
                if not line:
                    continue

                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    warning = "jsonl_decode_warning"
                    continue

                if isinstance(value, dict):
                    records.append(value)
    except OSError as exc:
        return [], f"read_error:{exc.__class__.__name__}"

    return records, warning


def _walk_dict_records(value: Any, out: list[dict[str, Any]], sample_limit: int) -> None:
    if len(out) >= sample_limit:
        return

    if isinstance(value, dict):
        out.append(value)
        for child in value.values():
            _walk_dict_records(child, out, sample_limit)
            if len(out) >= sample_limit:
                return
    elif isinstance(value, list):
        for item in value:
            _walk_dict_records(item, out, sample_limit)
            if len(out) >= sample_limit:
                return


def _iter_json_records(path: Path, sample_limit: int, max_json_bytes: int) -> tuple[list[dict[str, Any]], str | None]:
    if path.stat().st_size > max_json_bytes:
        return [], "json_file_too_large_for_discovery"

    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return [], "json_decode_error"
    except OSError as exc:
        return [], f"read_error:{exc.__class__.__name__}"

    records: list[dict[str, Any]] = []
    _walk_dict_records(value, records, sample_limit)
    return records, None


def _record_keys(records: Iterable[dict[str, Any]]) -> set[str]:
    keys: set[str] = set()

    for record in records:
        keys.update(str(key) for key in record.keys())

    return keys


def _matched_fields(keys: set[str]) -> tuple[str, ...]:
    matched: list[str] = []

    for canonical, aliases in FIELD_ALIASES.items():
        if any(alias in keys for alias in aliases):
            matched.append(canonical)

    return tuple(matched)


def analyze_candidate_file(
    *,
    path: Path,
    seed_root: Path,
    sample_limit: int,
    max_json_bytes: int,
) -> ClosedOutcomeFileCandidate:
    suffix = path.suffix.lower()

    if suffix == ".jsonl":
        records, warning = _iter_jsonl_records(path, sample_limit)
    elif suffix == ".json":
        records, warning = _iter_json_records(path, sample_limit, max_json_bytes)
    else:
        records, warning = [], "unsupported_suffix"

    keys = _record_keys(records)
    matched = _matched_fields(keys)
    missing = tuple(field for field in REQUIRED_CANONICAL_FIELDS if field not in matched)

    return ClosedOutcomeFileCandidate(
        relative_path=_rel(path, seed_root),
        suffix=suffix,
        size_bytes=path.stat().st_size,
        sampled_record_count=len(records),
        matched_canonical_fields=matched,
        missing_canonical_fields=missing,
        field_score=len(matched),
        has_required_core_fields=len(missing) == 0,
        read_warning=warning,
    )


def _candidate_files(root: Path) -> list[Path]:
    files: list[Path] = []

    for suffix in ("*.jsonl", "*.json"):
        files.extend(path for path in root.rglob(suffix) if path.is_file())

    return sorted(files)


def build_closed_outcomes_discovery(
    seed_bundle: str | Path | None = None,
    *,
    sample_limit: int = 5000,
    max_json_bytes: int = 50_000_000,
) -> ClosedOutcomeDiscovery:
    seed_root = resolve_seed_bundle_root(seed_bundle)

    if seed_root is None:
        return ClosedOutcomeDiscovery(
            seed_bundle_root=None,
            is_ready=False,
            search_root_count=len(SEARCH_ROOTS),
            existing_search_root_count=0,
            candidate_file_count=0,
            viable_candidate_count=0,
            best_candidate=None,
            candidates=tuple(),
            missing_search_roots=SEARCH_ROOTS,
        )

    existing_roots: list[Path] = []
    missing_roots: list[str] = []

    for rel_root in SEARCH_ROOTS:
        root = seed_root / rel_root
        if root.exists():
            existing_roots.append(root)
        else:
            missing_roots.append(rel_root)

    candidates: list[ClosedOutcomeFileCandidate] = []

    for root in existing_roots:
        for path in _candidate_files(root):
            candidates.append(
                analyze_candidate_file(
                    path=path,
                    seed_root=seed_root,
                    sample_limit=sample_limit,
                    max_json_bytes=max_json_bytes,
                )
            )

    candidates_sorted = tuple(
        sorted(
            candidates,
            key=lambda candidate: (
                candidate.has_required_core_fields,
                candidate.field_score,
                candidate.sampled_record_count,
                candidate.size_bytes,
            ),
            reverse=True,
        )
    )

    viable = tuple(candidate for candidate in candidates_sorted if candidate.has_required_core_fields)

    return ClosedOutcomeDiscovery(
        seed_bundle_root=str(seed_root),
        is_ready=len(viable) > 0,
        search_root_count=len(SEARCH_ROOTS),
        existing_search_root_count=len(existing_roots),
        candidate_file_count=len(candidates_sorted),
        viable_candidate_count=len(viable),
        best_candidate=viable[0] if viable else candidates_sorted[0] if candidates_sorted else None,
        candidates=candidates_sorted,
        missing_search_roots=tuple(missing_roots),
    )


def discovery_to_dict(discovery: ClosedOutcomeDiscovery) -> dict[str, Any]:
    return asdict(discovery)


def write_discovery(discovery: ClosedOutcomeDiscovery, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(discovery_to_dict(discovery), indent=2, sort_keys=True), encoding="utf-8")
    return path


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Discover closed-outcome source files in the V3.2.2 seed bundle.")
    parser.add_argument("--seed-bundle", default=None)
    parser.add_argument("--sample-limit", type=int, default=5000)
    parser.add_argument("--output", default="artifacts/closed_outcomes_discovery.json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    discovery = build_closed_outcomes_discovery(
        args.seed_bundle,
        sample_limit=args.sample_limit,
    )
    write_discovery(discovery, args.output)

    if args.json:
        print(json.dumps(discovery_to_dict(discovery), indent=2, sort_keys=True))
    else:
        print(f"seed_bundle_root: {discovery.seed_bundle_root}")
        print(f"is_ready: {discovery.is_ready}")
        print(f"candidate_file_count: {discovery.candidate_file_count}")
        print(f"viable_candidate_count: {discovery.viable_candidate_count}")
        print(f"output: {args.output}")
        if discovery.best_candidate:
            print(f"best_candidate: {discovery.best_candidate.relative_path}")

    return 0 if discovery.is_ready else 2


if __name__ == "__main__":
    raise SystemExit(main())


