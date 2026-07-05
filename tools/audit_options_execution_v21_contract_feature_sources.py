from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


ALIASES = {
    "underlying_symbol": [
        "underlying_symbol",
        "requested_underlying_symbol",
        "option_underlying",
        "underlying",
        "root_symbol",
        "market_symbol",
        "asset_symbol",
        "ticker",
    ],
    "quote_date": [
        "quote_date",
        "date",
        "as_of_date",
        "decision_date",
        "trade_date",
    ],
    "contract_identifier": [
        "option_symbol",
        "option_contract_symbol",
        "contract_symbol",
        "canonical_option_symbol",
        "contract_id",
        "option_contract",
        "contract",
    ],
    "right": [
        "right",
        "option_right",
        "put_call",
        "call_put",
        "contract_right",
    ],
    "strike": [
        "strike",
        "strike_price",
        "contract_strike",
    ],
    "expiration": [
        "expiration",
        "expiry",
        "expiration_date",
        "contract_expiration",
    ],
    "dte": [
        "dte",
        "days_to_expiration",
        "min_dte",
        "max_dte",
        "expiration_count",
    ],
    "bid": [
        "bid",
        "bid_price",
        "close_bid",
        "quote_bid",
        "bid_count",
        "bid_ask_complete_rate",
    ],
    "ask": [
        "ask",
        "ask_price",
        "close_ask",
        "quote_ask",
        "ask_count",
        "bid_ask_complete_rate",
    ],
    "mid": [
        "mid",
        "mid_price",
        "quote_mid",
        "mid_count",
        "mid_available_rate",
    ],
    "spread": [
        "spread",
        "bid_ask_spread",
        "avg_spread",
        "median_spread",
        "max_spread",
        "spread_count",
    ],
    "relative_spread": [
        "relative_spread",
        "spread_pct",
        "avg_relative_spread",
        "median_relative_spread",
        "max_relative_spread",
        "spread_pct_available_rate",
        "spread_pct_p50_bucket_upper",
        "spread_pct_p75_bucket_upper",
        "spread_pct_p90_bucket_upper",
        "relative_spread_count",
    ],
    "delta": [
        "delta",
        "abs_delta",
        "min_delta",
        "max_delta",
        "delta_count",
        "delta_seen_rate",
    ],
    "gamma": [
        "gamma",
        "gamma_count",
        "gamma_seen_rate",
    ],
    "theta": [
        "theta",
        "theta_count",
        "theta_seen_rate",
    ],
    "vega": [
        "vega",
        "vega_count",
        "vega_seen_rate",
    ],
    "rho": [
        "rho",
        "rho_count",
        "rho_seen_rate",
    ],
    "implied_volatility": [
        "iv",
        "implied_volatility",
        "impliedvolatility",
        "implied_vol",
        "iv_count",
        "iv_seen_rate",
        "implied_volatility_seen_rate",
    ],
    "greeks": [
        "greeks",
        "greeks_seen_rate",
        "greeks_available",
    ],
    "open_interest": [
        "open_interest",
        "oi",
        "avg_open_interest",
        "median_open_interest",
        "max_open_interest",
        "open_interest_count",
        "open_interest_seen_rate",
    ],
    "volume": [
        "volume",
        "contract_volume",
        "avg_volume",
        "median_volume",
        "max_volume",
        "volume_count",
        "volume_seen_rate",
    ],
    "underlying_price": [
        "underlying_price",
        "underlying_close",
        "spot_price",
        "spot",
        "underlying_last",
    ],
    "liquidity": [
        "liquidity_tier",
        "rolling_liquidity_tier",
    ],
    "row_count": [
        "row_count",
    ],
}


PATTERNS = [
    "underlying",
    "symbol",
    "contract",
    "quote",
    "date",
    "right",
    "strike",
    "expiration",
    "expiry",
    "dte",
    "bid",
    "ask",
    "mid",
    "spread",
    "delta",
    "gamma",
    "theta",
    "vega",
    "rho",
    "greek",
    "iv",
    "volatility",
    "open",
    "interest",
    "volume",
    "liquidity",
    "row_count",
]


def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def is_present(value: Any) -> bool:
    return value not in (None, "", [], {})


def has_any(row: dict[str, Any], fields: list[str]) -> bool:
    for field in fields:
        if is_present(row.get(field)):
            return True
    return False


def compact_row(row: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for key, value in row.items():
        low = key.lower()
        if any(pattern in low for pattern in PATTERNS):
            out[key] = value
    return out


def audit_jsonl(path: Path, sample_limit: int = 5) -> dict[str, Any]:
    row_count = 0

    field_presence = Counter()
    field_non_null = Counter()
    field_examples: dict[str, Any] = {}

    matched_field_presence = Counter()
    matched_field_non_null = Counter()
    matched_field_examples: dict[str, Any] = {}

    canonical_presence = Counter()
    canonical_by_component = {}

    sample_rows = []
    component_counts = Counter()

    for row in read_jsonl(path):
        row_count += 1

        component = str(row.get("merge_component") or row.get("source") or row.get("adapter_type") or "unknown")
        component_counts[component] += 1

        if len(sample_rows) < sample_limit:
            sample_rows.append(compact_row(row))

        for field, value in row.items():
            field_presence[field] += 1
            if is_present(value):
                field_non_null[field] += 1
                field_examples.setdefault(field, value)

            low = field.lower()
            if any(pattern in low for pattern in PATTERNS):
                matched_field_presence[field] += 1
                if is_present(value):
                    matched_field_non_null[field] += 1
                    matched_field_examples.setdefault(field, value)

        for canonical_name, fields in ALIASES.items():
            if has_any(row, fields):
                canonical_presence[canonical_name] += 1

    canonical_coverage = {
        name: {
            "present_row_count": canonical_presence.get(name, 0),
            "coverage_rate": (
                canonical_presence.get(name, 0) / row_count if row_count else 0.0
            ),
            "aliases": fields,
        }
        for name, fields in ALIASES.items()
    }

    matched_fields = {
        field: {
            "presence": matched_field_presence[field],
            "non_null": matched_field_non_null[field],
            "example": matched_field_examples.get(field),
        }
        for field in sorted(matched_field_presence)
    }

    has_contract_identity = (
        canonical_coverage["contract_identifier"]["coverage_rate"] >= 0.95
        or (
            canonical_coverage["right"]["coverage_rate"] >= 0.95
            and canonical_coverage["strike"]["coverage_rate"] >= 0.95
            and canonical_coverage["expiration"]["coverage_rate"] >= 0.95
        )
    )

    has_quote_surface = (
        canonical_coverage["underlying_symbol"]["coverage_rate"] >= 0.95
        and canonical_coverage["quote_date"]["coverage_rate"] >= 0.95
        and has_contract_identity
        and canonical_coverage["bid"]["coverage_rate"] >= 0.80
        and canonical_coverage["ask"]["coverage_rate"] >= 0.80
        and canonical_coverage["relative_spread"]["coverage_rate"] >= 0.80
    )

    has_greek_surface = (
        canonical_coverage["delta"]["coverage_rate"] >= 0.80
        and canonical_coverage["implied_volatility"]["coverage_rate"] >= 0.80
    )

    has_liquidity_depth_surface = (
        canonical_coverage["open_interest"]["coverage_rate"] >= 0.50
        or canonical_coverage["volume"]["coverage_rate"] >= 0.50
    )

    return {
        "path": str(path),
        "row_count": row_count,
        "component_counts": dict(sorted(component_counts.items())),
        "canonical_coverage": canonical_coverage,
        "matched_fields": matched_fields,
        "sample_rows": sample_rows,
        "v21_local_readiness": {
            "has_contract_identity": has_contract_identity,
            "has_quote_surface": has_quote_surface,
            "has_greek_surface": has_greek_surface,
            "has_liquidity_depth_surface": has_liquidity_depth_surface,
            "can_build_v21_quote_spread_contract_features_locally": has_quote_surface,
            "can_build_v21_full_greeks_oi_volume_locally": (
                has_quote_surface
                and has_greek_surface
                and has_liquidity_depth_surface
            ),
            "requires_quantconnect_repull_for_full_v21": not (
                has_quote_surface
                and has_greek_surface
                and has_liquidity_depth_surface
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-jsonl", required=True)
    parser.add_argument("--metrics-jsonl", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    source_path = Path(args.source_jsonl)
    metrics_path = Path(args.metrics_jsonl)
    output_dir = Path(args.output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    summary_path = output_dir / "signalforge_options_execution_v21_contract_feature_source_audit.json"

    source_audit = audit_jsonl(source_path)
    metrics_audit = audit_jsonl(metrics_path)

    blockers = []

    if not source_audit["v21_local_readiness"]["has_contract_identity"]:
        blockers.append("source_lacks_contract_identity")

    if not source_audit["v21_local_readiness"]["has_quote_surface"]:
        blockers.append("source_lacks_quote_spread_contract_surface")

    if not source_audit["v21_local_readiness"]["has_greek_surface"]:
        blockers.append("source_lacks_delta_iv_surface")

    if not source_audit["v21_local_readiness"]["has_liquidity_depth_surface"]:
        blockers.append("source_lacks_open_interest_or_volume_surface")

    summary = {
        "adapter_type": "options_execution_v21_contract_feature_source_auditor",
        "artifact_type": "signalforge_options_execution_v21_contract_feature_source_audit",
        "contract": "options_execution_v21_contract_feature_source_audit",
        "is_ready": True,
        "v21_full_local_build_ready": len(blockers) == 0,
        "v21_full_local_build_blocker_count": len(blockers),
        "v21_full_local_build_blockers": blockers,
        "source_audit": source_audit,
        "metrics_audit": metrics_audit,
        "paths": {
            "summary_path": str(summary_path),
        },
    }

    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
