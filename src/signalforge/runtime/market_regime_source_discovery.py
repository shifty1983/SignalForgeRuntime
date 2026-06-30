from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from signalforge.data.seed_bundle import resolve_seed_bundle_root


SEARCH_ROOTS_BY_LAYER: dict[str, tuple[str, ...]] = {
    "market": (
        "artifacts/qc_replay_5y_behavior_inputs",
        "artifacts/qc_replay_5y_market_price_behavior",
        "data/manual",
    ),
    "regime": (
        "artifacts/qc_replay_5y_historical_regime_date_map",
        "artifacts/qc_replay_5y_behavior_inputs",
    ),
}

FIELD_ALIASES_BY_LAYER: dict[str, dict[str, tuple[str, ...]]] = {
    "market": {
        "symbol": ("symbol", "underlying", "underlying_symbol", "ticker"),
        "date": ("date", "decision_date", "bar_date", "quote_date", "asof_date", "as_of_date"),
        "open": ("open", "open_price"),
        "high": ("high", "high_price"),
        "low": ("low", "low_price"),
        "close": ("close", "close_price", "adjusted_close", "underlying_close", "price"),
        "volume": ("volume", "share_volume"),
    },
    "regime": {
        "date": ("date", "regime_date", "decision_date", "asof_date", "as_of_date"),
        "regime_state": ("regime_state", "regime", "market_regime_state", "macro_regime", "dominant_regime"),
    },
}

REQUIRED_FIELDS_BY_LAYER: dict[str, tuple[str, ...]] = {
    "market": ("symbol", "date", "close"),
    "regime": ("date", "regime_state"),
}


@dataclass(frozen=True)
class LayerSourceCandidate:
    layer: str
    relative_path: str
    suffix: str
    size_bytes: int
    sampled_record_count: int
    matched_fields: tuple[str, ...]
    missing_required_fields: tuple[str, ...]
    field_score: int
    has_required_fields: bool
    read_warning: str | None


@dataclass(frozen=True)
class MarketRegimeSourceDiscovery:
    seed_bundle_root: str | None
    is_ready: bool
    candidate_file_count: int
    viable_market_candidate_count: int
    viable_regime_candidate_count: int
    best_market_candidate: LayerSourceCandidate | None
    best_regime_candidate: LayerSourceCandidate | None
    candidates: tuple[LayerSourceCandidate, ...]
    missing_search_roots: tuple[str, ...]
    blocker_count: int
    blockers: tuple[str, ...]


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


def _matched_fields(layer: str, keys: set[str]) -> tuple[str, ...]:
    matched: list[str] = []

    for canonical, aliases in FIELD_ALIASES_BY_LAYER[layer].items():
        if any(alias in keys for alias in aliases):
            matched.append(canonical)

    return tuple(matched)


def _candidate_files(root: Path) -> list[Path]:
    files: list[Path] = []

    for suffix in ("*.jsonl", "*.json"):
        files.extend(path for path in root.rglob(suffix) if path.is_file())

    return sorted(files)


def analyze_candidate_file(
    *,
    layer: str,
    path: Path,
    seed_root: Path,
    sample_limit: int,
    max_json_bytes: int,
) -> LayerSourceCandidate:
    suffix = path.suffix.lower()

    if suffix == ".jsonl":
        records, warning = _iter_jsonl_records(path, sample_limit)
    elif suffix == ".json":
        records, warning = _iter_json_records(path, sample_limit, max_json_bytes)
    else:
        records, warning = [], "unsupported_suffix"

    keys = _record_keys(records)
    matched = _matched_fields(layer, keys)
    required = REQUIRED_FIELDS_BY_LAYER[layer]
    missing = tuple(field for field in required if field not in matched)

    return LayerSourceCandidate(
        layer=layer,
        relative_path=_rel(path, seed_root),
        suffix=suffix,
        size_bytes=path.stat().st_size,
        sampled_record_count=len(records),
        matched_fields=matched,
        missing_required_fields=missing,
        field_score=len(matched),
        has_required_fields=len(missing) == 0,
        read_warning=warning,
    )


def build_market_regime_source_discovery(
    seed_bundle: str | Path | None = None,
    *,
    sample_limit: int = 5000,
    max_json_bytes: int = 50_000_000,
) -> MarketRegimeSourceDiscovery:
    seed_root = resolve_seed_bundle_root(seed_bundle)

    if seed_root is None:
        return MarketRegimeSourceDiscovery(
            seed_bundle_root=None,
            is_ready=False,
            candidate_file_count=0,
            viable_market_candidate_count=0,
            viable_regime_candidate_count=0,
            best_market_candidate=None,
            best_regime_candidate=None,
            candidates=tuple(),
            missing_search_roots=tuple(
                root for roots in SEARCH_ROOTS_BY_LAYER.values() for root in roots
            ),
            blocker_count=1,
            blockers=("seed_bundle_missing",),
        )

    candidates: list[LayerSourceCandidate] = []
    missing_roots: list[str] = []

    for layer, search_roots in SEARCH_ROOTS_BY_LAYER.items():
        for relative_root in search_roots:
            root = seed_root / relative_root

            if not root.exists():
                missing_roots.append(relative_root)
                continue

            for path in _candidate_files(root):
                candidates.append(
                    analyze_candidate_file(
                        layer=layer,
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
                candidate.has_required_fields,
                candidate.field_score,
                candidate.sampled_record_count,
                candidate.size_bytes,
            ),
            reverse=True,
        )
    )

    viable_market = tuple(
        candidate
        for candidate in candidates_sorted
        if candidate.layer == "market" and candidate.has_required_fields
    )
    viable_regime = tuple(
        candidate
        for candidate in candidates_sorted
        if candidate.layer == "regime" and candidate.has_required_fields
    )

    blockers: list[str] = []

    if not viable_market:
        blockers.append("no_viable_market_source_found")

    if not viable_regime:
        blockers.append("no_viable_regime_source_found")

    return MarketRegimeSourceDiscovery(
        seed_bundle_root=str(seed_root),
        is_ready=not blockers,
        candidate_file_count=len(candidates_sorted),
        viable_market_candidate_count=len(viable_market),
        viable_regime_candidate_count=len(viable_regime),
        best_market_candidate=viable_market[0] if viable_market else None,
        best_regime_candidate=viable_regime[0] if viable_regime else None,
        candidates=candidates_sorted,
        missing_search_roots=tuple(sorted(set(missing_roots))),
        blocker_count=len(blockers),
        blockers=tuple(blockers),
    )


def discovery_to_dict(discovery: MarketRegimeSourceDiscovery) -> dict[str, Any]:
    return asdict(discovery)


def write_discovery(discovery: MarketRegimeSourceDiscovery, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(discovery_to_dict(discovery), indent=2, sort_keys=True), encoding="utf-8")
    return path


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Discover market/regime source files in the V3.2.2 seed bundle.")
    parser.add_argument("--seed-bundle", default=None)
    parser.add_argument("--sample-limit", type=int, default=5000)
    parser.add_argument("--output", default="artifacts/market_regime_source_discovery.json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    discovery = build_market_regime_source_discovery(
        seed_bundle=args.seed_bundle,
        sample_limit=args.sample_limit,
    )
    write_discovery(discovery, args.output)

    if args.json:
        print(json.dumps(discovery_to_dict(discovery), indent=2, sort_keys=True))
    else:
        print(f"seed_bundle_root: {discovery.seed_bundle_root}")
        print(f"is_ready: {discovery.is_ready}")
        print(f"candidate_file_count: {discovery.candidate_file_count}")
        print(f"viable_market_candidate_count: {discovery.viable_market_candidate_count}")
        print(f"viable_regime_candidate_count: {discovery.viable_regime_candidate_count}")
        print(f"blocker_count: {discovery.blocker_count}")
        if discovery.best_market_candidate:
            print(f"best_market_candidate: {discovery.best_market_candidate.relative_path}")
        if discovery.best_regime_candidate:
            print(f"best_regime_candidate: {discovery.best_regime_candidate.relative_path}")

    return 0 if discovery.is_ready else 2


if __name__ == "__main__":
    raise SystemExit(main())


