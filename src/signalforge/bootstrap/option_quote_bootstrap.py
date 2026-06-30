from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from signalforge.data.seed_bundle import resolve_seed_bundle_root


QUOTE_AUDIT_SOURCE_RELATIVE_PATH = (
    "artifacts/v3_2_1_native_quote_join_v1_20230101_20260531/"
    "signalforge_v3_2_1_native_quote_join_row_audit.jsonl"
)

DEFAULT_OUTPUT = "data/runtime/option_quotes/option_quote_snapshot.jsonl"


@dataclass(frozen=True)
class OptionQuoteBootstrapSummary:
    seed_bundle_root: str | None
    source_path: str | None
    output_path: str
    is_ready: bool
    source_audit_row_count: int
    matched_entry_quote_count: int
    matched_exit_quote_count: int
    emitted_quote_count: int
    written_quote_count: int
    duplicate_quote_count: int
    contract_symbol_count: int
    quote_date_count: int
    missing_quote_count: int
    blocker_count: int
    blockers: tuple[str, ...]


def _read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue

            value = json.loads(line)

            if isinstance(value, dict):
                yield value


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _quote_identity(row: dict[str, Any]) -> dict[str, Any]:
    identity = row.get("identity") or {}

    if not isinstance(identity, dict):
        identity = {}

    return {
        "contract_symbol": identity.get("contract_symbol"),
        "expiration": identity.get("expiration"),
        "right": identity.get("right"),
        "strike": identity.get("strike"),
        "underlying": identity.get("underlying"),
    }


def _build_quote_record(
    *,
    audit_row: dict[str, Any],
    quote_role: str,
    quote_date: str | None,
    matched: bool,
    target_key: Any,
    quote: Any,
) -> dict[str, Any] | None:
    if not matched or not isinstance(quote, dict):
        return None

    identity = _quote_identity(audit_row)
    contract_symbol = identity.get("contract_symbol")

    bid = _safe_float(quote.get("bid"))
    ask = _safe_float(quote.get("ask"))
    mid = _safe_float(quote.get("mid"))
    spread = _safe_float(quote.get("spread"))
    spread_pct = _safe_float(quote.get("spread_pct"))

    if not contract_symbol or not quote_date or bid is None or ask is None or mid is None:
        return None

    return {
        "contract": "option_quote_snapshot_row",
        "quote_role": quote_role,
        "capital_label": audit_row.get("capital_label"),
        "row_index": audit_row.get("row_index"),
        "leg_index": audit_row.get("leg_index"),
        "quote_date": quote_date,
        "contract_symbol": contract_symbol,
        "option_symbol": contract_symbol,
        "expiration": identity.get("expiration"),
        "right": identity.get("right"),
        "strike": identity.get("strike"),
        "underlying": identity.get("underlying"),
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "spread": spread,
        "spread_pct": spread_pct,
        "sanity": quote.get("sanity"),
        "target_key": target_key,
        "key_used": quote.get("key_used"),
        "quote_source_path": quote.get("source_path"),
        "quote_source_row_index": quote.get("source_row_index"),
        "source_audit_path": QUOTE_AUDIT_SOURCE_RELATIVE_PATH,
    }


def _dedupe_key(record: dict[str, Any]) -> tuple[Any, ...]:
    return (
        record.get("contract_symbol"),
        record.get("quote_date"),
        record.get("bid"),
        record.get("ask"),
        record.get("mid"),
        record.get("quote_source_row_index"),
    )


def _build_quote_rows(source_path: Path) -> tuple[list[dict[str, Any]], dict[str, int]]:
    deduped: dict[tuple[Any, ...], dict[str, Any]] = {}

    source_audit_row_count = 0
    matched_entry_quote_count = 0
    matched_exit_quote_count = 0
    emitted_quote_count = 0
    missing_quote_count = 0
    duplicate_quote_count = 0

    for audit_row in _read_jsonl(source_path):
        source_audit_row_count += 1

        candidates = (
            (
                "entry",
                audit_row.get("entry_date"),
                bool(audit_row.get("entry_matched")),
                audit_row.get("entry_target_key"),
                audit_row.get("entry_quote"),
            ),
            (
                "exit",
                audit_row.get("exit_date"),
                bool(audit_row.get("exit_matched")),
                audit_row.get("exit_target_key"),
                audit_row.get("exit_quote"),
            ),
        )

        for quote_role, quote_date, matched, target_key, quote in candidates:
            record = _build_quote_record(
                audit_row=audit_row,
                quote_role=quote_role,
                quote_date=quote_date,
                matched=matched,
                target_key=target_key,
                quote=quote,
            )

            if record is None:
                missing_quote_count += 1
                continue

            emitted_quote_count += 1

            if quote_role == "entry":
                matched_entry_quote_count += 1
            elif quote_role == "exit":
                matched_exit_quote_count += 1

            key = _dedupe_key(record)

            if key in deduped:
                duplicate_quote_count += 1
                existing = deduped[key]
                roles = set(existing.get("observed_quote_roles") or [])
                roles.add(str(record.get("quote_role")))
                existing["observed_quote_roles"] = sorted(roles)
                existing["source_audit_ref_count"] = int(existing.get("source_audit_ref_count") or 1) + 1
                continue

            record["observed_quote_roles"] = [str(record.get("quote_role"))]
            record["source_audit_ref_count"] = 1
            deduped[key] = record

    rows = sorted(
        deduped.values(),
        key=lambda row: (
            str(row.get("quote_date") or ""),
            str(row.get("contract_symbol") or ""),
            str(row.get("quote_source_row_index") or ""),
        ),
    )

    counts = {
        "source_audit_row_count": source_audit_row_count,
        "matched_entry_quote_count": matched_entry_quote_count,
        "matched_exit_quote_count": matched_exit_quote_count,
        "emitted_quote_count": emitted_quote_count,
        "missing_quote_count": missing_quote_count,
        "duplicate_quote_count": duplicate_quote_count,
    }

    return rows, counts


def build_option_quote_bootstrap(
    *,
    seed_bundle: str | Path | None = None,
    output_path: str | Path = DEFAULT_OUTPUT,
) -> OptionQuoteBootstrapSummary:
    seed_root = resolve_seed_bundle_root(seed_bundle)
    output = Path(output_path)

    if seed_root is None:
        return OptionQuoteBootstrapSummary(
            seed_bundle_root=None,
            source_path=None,
            output_path=str(output),
            is_ready=False,
            source_audit_row_count=0,
            matched_entry_quote_count=0,
            matched_exit_quote_count=0,
            emitted_quote_count=0,
            written_quote_count=0,
            duplicate_quote_count=0,
            contract_symbol_count=0,
            quote_date_count=0,
            missing_quote_count=0,
            blocker_count=1,
            blockers=("seed_bundle_missing",),
        )

    source = seed_root / QUOTE_AUDIT_SOURCE_RELATIVE_PATH

    if not source.is_file():
        return OptionQuoteBootstrapSummary(
            seed_bundle_root=str(seed_root),
            source_path=str(source),
            output_path=str(output),
            is_ready=False,
            source_audit_row_count=0,
            matched_entry_quote_count=0,
            matched_exit_quote_count=0,
            emitted_quote_count=0,
            written_quote_count=0,
            duplicate_quote_count=0,
            contract_symbol_count=0,
            quote_date_count=0,
            missing_quote_count=0,
            blocker_count=1,
            blockers=("quote_audit_source_missing",),
        )

    rows, counts = _build_quote_rows(source)
    blockers: list[str] = []

    if not rows:
        blockers.append("no_quote_rows_written")

    output.parent.mkdir(parents=True, exist_ok=True)

    with output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    return OptionQuoteBootstrapSummary(
        seed_bundle_root=str(seed_root),
        source_path=str(source),
        output_path=str(output),
        is_ready=not blockers,
        source_audit_row_count=counts["source_audit_row_count"],
        matched_entry_quote_count=counts["matched_entry_quote_count"],
        matched_exit_quote_count=counts["matched_exit_quote_count"],
        emitted_quote_count=counts["emitted_quote_count"],
        written_quote_count=len(rows),
        duplicate_quote_count=counts["duplicate_quote_count"],
        contract_symbol_count=len({str(row.get("contract_symbol")) for row in rows if row.get("contract_symbol")}),
        quote_date_count=len({str(row.get("quote_date")) for row in rows if row.get("quote_date")}),
        missing_quote_count=counts["missing_quote_count"],
        blocker_count=len(blockers),
        blockers=tuple(blockers),
    )


def summary_to_dict(summary: OptionQuoteBootstrapSummary) -> dict[str, Any]:
    return asdict(summary)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap runtime option quote snapshot.")
    parser.add_argument("--seed-bundle", default=None)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--summary-output", default="artifacts/option_quote_bootstrap_summary.json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    summary = build_option_quote_bootstrap(seed_bundle=args.seed_bundle, output_path=args.output)

    summary_path = Path(args.summary_output)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary_to_dict(summary), indent=2, sort_keys=True), encoding="utf-8")

    if args.json:
        print(json.dumps(summary_to_dict(summary), indent=2, sort_keys=True))
    else:
        print(f"is_ready: {summary.is_ready}")
        print(f"source_audit_row_count: {summary.source_audit_row_count}")
        print(f"matched_entry_quote_count: {summary.matched_entry_quote_count}")
        print(f"matched_exit_quote_count: {summary.matched_exit_quote_count}")
        print(f"emitted_quote_count: {summary.emitted_quote_count}")
        print(f"written_quote_count: {summary.written_quote_count}")
        print(f"duplicate_quote_count: {summary.duplicate_quote_count}")
        print(f"contract_symbol_count: {summary.contract_symbol_count}")
        print(f"quote_date_count: {summary.quote_date_count}")
        print(f"blocker_count: {summary.blocker_count}")

    return 0 if summary.is_ready else 2


if __name__ == "__main__":
    raise SystemExit(main())




