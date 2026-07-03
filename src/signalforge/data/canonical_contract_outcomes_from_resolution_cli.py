from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8-sig", errors="ignore") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True, default=str) + "\n")


def iter_leaf_values(obj: Any, path: str = ""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            next_path = f"{path}.{k}" if path else str(k)
            yield from iter_leaf_values(v, next_path)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            next_path = f"{path}[{i}]"
            yield from iter_leaf_values(v, next_path)
    else:
        yield path, obj


def leaf_map(row: dict[str, Any]) -> dict[str, list[Any]]:
    out: dict[str, list[Any]] = defaultdict(list)
    for path, value in iter_leaf_values(row):
        name = path.split(".")[-1].split("[")[0].lower()
        out[name].append(value)
    return out


def pick(row: dict[str, Any], names: list[str]) -> Any:
    for name in names:
        if row.get(name) not in (None, ""):
            return row.get(name)

    leaves = leaf_map(row)
    for name in names:
        for value in leaves.get(name.lower(), []):
            if value not in (None, ""):
                return value

    return None


def norm_right(x: Any) -> str:
    s = str(x or "").strip().lower()
    if s in ("c", "call", "optionright.call"):
        return "call"
    if s in ("p", "put", "optionright.put"):
        return "put"
    return s


def norm_date(x: Any) -> str:
    return str(x or "")[:10]


def norm_strike(x: Any) -> str:
    try:
        d = Decimal(str(x))
        d = d.normalize()
        if d == d.to_integral():
            return str(d.to_integral())
        return format(d, "f").rstrip("0").rstrip(".")
    except (InvalidOperation, ValueError):
        return str(x or "").strip()


def to_float(x: Any) -> float | None:
    if x in (None, ""):
        return None
    try:
        return float(x)
    except Exception:
        return None


def quote_quality(row: dict[str, Any] | None) -> str:
    if not row:
        return "missing"

    bid = row.get("bid")
    ask = row.get("ask")
    mid = row.get("mid")

    if bid is not None and ask is not None and mid is not None:
        return "present"

    if mid is not None or bid is not None or ask is not None:
        return "weak"

    return "missing"


def extract_symbol(row: dict[str, Any]) -> str:
    return str(pick(row, ["symbol", "underlying_symbol", "underlying", "ticker", "root_symbol", "required_symbol"]) or "").upper()


def extract_quote_date(row: dict[str, Any]) -> str:
    return norm_date(pick(row, [
        "quote_date",
        "required_quote_date",
        "candidate_quote_date",
        "target_quote_date",
        "lookup_quote_date",
        "exit_quote_date",
        "entry_quote_date",
        "date",
    ]))


def extract_expiration(row: dict[str, Any]) -> str:
    return norm_date(pick(row, ["expiration", "expiry", "expiration_date", "expiry_date", "required_expiration", "selected_expiration"]))


def extract_strike(row: dict[str, Any]) -> str:
    return norm_strike(pick(row, ["strike", "required_strike", "selected_strike", "option_strike"]))


def extract_right(row: dict[str, Any]) -> str:
    return norm_right(pick(row, ["option_right", "right", "put_call", "call_put", "option_type", "required_option_right", "selected_option_right"]))


def extract_quote_outcome_id(row: dict[str, Any]) -> str:
    return str(pick(row, ["selected_quote_outcome_id", "quote_outcome_id", "contract_outcome_id"]) or "")


def extract_leg_id(row: dict[str, Any]) -> str:
    return str(pick(row, ["leg_selection_id", "leg_id", "selected_leg_index", "leg_index"]) or "")


def extract_leg_role(row: dict[str, Any]) -> str:
    return str(pick(row, ["required_role", "role", "quote_role", "leg_role"]) or "")


def extract_timing(row: dict[str, Any]) -> str:
    raw = str(pick(row, [
        "required_quote_timing",
        "quote_timing",
        "quote_phase",
        "quote_kind",
        "quote_type",
        "quote_requirement_type",
        "entry_or_exit",
        "required_side",
        "requirement_side",
        "timing",
    ]) or "").lower()

    if "entry" in raw:
        return "entry"
    if "exit" in raw:
        return "exit"

    role = str(pick(row, ["required_quote_type", "required_quote_role", "quote_role", "role"]) or "").lower()
    if "entry" in role:
        return "entry"
    if "exit" in role:
        return "exit"

    # Last-resort inference: if a row has target_exit_date and quote_date differs
    # from decision/entry date, treat it as an exit candidate.
    qd = extract_quote_date(row)
    decision = norm_date(pick(row, ["decision_date", "entry_date", "asof_date"]))
    target_exit = norm_date(pick(row, ["target_exit_date", "exit_date", "outcome_date"]))

    if target_exit and qd and qd != decision:
        return "exit"

    return "entry"


def quote_key_from_parts(symbol: str, quote_date: str, expiration: str, strike: str, right: str) -> str:
    return "|".join([symbol.upper(), quote_date[:10], expiration[:10], norm_strike(strike), norm_right(right)])


def quote_key(row: dict[str, Any]) -> str:
    return quote_key_from_parts(
        extract_symbol(row),
        extract_quote_date(row),
        extract_expiration(row),
        extract_strike(row),
        extract_right(row),
    )


def leg_group_key(row: dict[str, Any]) -> str:
    return "|".join([
        extract_quote_outcome_id(row),
        extract_leg_id(row),
        extract_timing(row),
        extract_leg_role(row),
        extract_symbol(row),
        extract_expiration(row),
        extract_strike(row),
        extract_right(row),
    ])


def action_sign(action: Any, timing: str) -> int:
    s = str(action or "").lower()

    if timing == "entry":
        if "buy" in s or "long" in s:
            return -1
        if "sell" in s or "short" in s:
            return 1

    if timing == "exit":
        if "buy" in s or "cover" in s:
            return -1
        if "sell" in s:
            return 1

    return 0


def infer_entry_action(role: str) -> str:
    r = role.lower()
    if r.startswith("long_") or "_long_" in r:
        return "buy_to_open"
    if r.startswith("short_") or "_short_" in r:
        return "sell_to_open"
    return "unknown"


def exit_action_for_entry_action(entry_action: str) -> str:
    if "buy" in entry_action or "long" in entry_action:
        return "sell_to_close"
    if "sell" in entry_action or "short" in entry_action:
        return "buy_to_close"
    return "unknown"


def price_for_action(row: dict[str, Any], action: str, fallback: str) -> float | None:
    bid = to_float(row.get("bid"))
    ask = to_float(row.get("ask"))
    mid = to_float(row.get("mid"))

    a = action.lower()

    if "buy" in a:
        return ask if ask is not None else mid

    if "sell" in a:
        return bid if bid is not None else mid

    if fallback == "mid":
        return mid

    return None


def mid_price(row: dict[str, Any]) -> float | None:
    return to_float(row.get("mid"))


def load_options(path: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}

    for row in read_jsonl(path):
        k = quote_key(row)
        old = out.get(k)

        if old is None:
            out[k] = row
            continue

        old_q = quote_quality(old)
        new_q = quote_quality(row)

        if old_q != "present" and new_q == "present":
            out[k] = row
        elif old_q == "missing" and new_q == "weak":
            out[k] = row

    return out


def choose_best_candidate(candidates: list[dict[str, Any]], options: dict[str, dict[str, Any]]) -> dict[str, Any]:
    enriched = []

    for req in candidates:
        k = quote_key(req)
        opt = options.get(k)
        q = quote_quality(opt)

        enriched.append({
            "required_row": req,
            "quote_key": k,
            "quote": opt,
            "quality": q,
            "quote_date": extract_quote_date(req),
        })

    present = [x for x in enriched if x["quality"] == "present"]
    if present:
        return sorted(present, key=lambda x: x["quote_date"])[0]

    weak = [x for x in enriched if x["quality"] == "weak"]
    if weak:
        return sorted(weak, key=lambda x: x["quote_date"])[0]

    return sorted(enriched, key=lambda x: x["quote_date"])[0] if enriched else {
        "required_row": {},
        "quote_key": "",
        "quote": None,
        "quality": "missing",
        "quote_date": "",
    }


def make_leg(best: dict[str, Any], timing: str, entry_action_by_leg_key: dict[str, str]) -> dict[str, Any]:
    req = best["required_row"]
    quote = best["quote"] or {}

    role = extract_leg_role(req)
    leg_id = extract_leg_id(req)

    if timing == "entry":
        action = str(pick(req, ["action", "entry_action"]) or infer_entry_action(role))
    else:
        entry_key = "|".join([
            extract_quote_outcome_id(req),
            leg_id,
            role,
            extract_symbol(req),
            extract_expiration(req),
            extract_strike(req),
            extract_right(req),
        ])
        entry_action = entry_action_by_leg_key.get(entry_key) or infer_entry_action(role)
        explicit_exit_action = pick(req, ["exit_action"])
        action = str(explicit_exit_action or exit_action_for_entry_action(entry_action))

    return {
        "timing": timing,
        "leg_selection_id": leg_id,
        "role": role,
        "symbol": extract_symbol(req),
        "quote_date": best["quote_date"],
        "expiration": extract_expiration(req),
        "strike": to_float(extract_strike(req)),
        "option_right": extract_right(req),
        "action": action,
        "quality": best["quality"],
        "quote_key": best["quote_key"],
        "bid": quote.get("bid"),
        "ask": quote.get("ask"),
        "mid": quote.get("mid"),
        "source_quote_resolution_state": quote.get("quote_resolution_state"),
    }



def synthesize_entry_required_row(row: dict[str, Any]) -> dict[str, Any] | None:
    # The required quote manifest may contain only exit search-window rows for an outcome.
    # In that case, synthesize the entry requirement from the same contract identity
    # using decision_date as the entry quote date.
    if extract_timing(row) != "exit":
        return None

    decision_date = norm_date(pick(row, ["decision_date", "entry_date", "asof_date"]))
    if not decision_date:
        return None

    symbol = extract_symbol(row)
    expiration = extract_expiration(row)
    strike = extract_strike(row)
    right = extract_right(row)

    if not symbol or not expiration or not strike or right not in ("call", "put"):
        return None

    out = dict(row)
    out["required_quote_role"] = "entry"
    out["required_quote_date"] = decision_date
    out["manifest_key"] = quote_key_from_parts(symbol, decision_date, expiration, strike, right)
    out["synthetic_entry_quote"] = True
    out["source"] = str(out.get("source") or "") + "|synthetic_entry_from_exit_required_row"
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--required-manifest", required=True)
    parser.add_argument("--canonical-options", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--commission-per-contract", type=float, default=0.65)
    args = parser.parse_args()

    required_path = Path(args.required_manifest)
    options_path = Path(args.canonical_options)
    output_dir = Path(args.output_dir)

    options = load_options(options_path)

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)

    source_required_row_count = 0
    synthetic_entry_row_count = 0

    for row in read_jsonl(required_path):
        source_required_row_count += 1
        groups[leg_group_key(row)].append(row)

        synthetic_entry = synthesize_entry_required_row(row)
        if synthetic_entry is not None:
            synthetic_entry_row_count += 1
            groups[leg_group_key(synthetic_entry)].append(synthetic_entry)

    by_outcome: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "entry_groups": {},
        "exit_groups": {},
    })

    for gkey, rows in groups.items():
        sample = rows[0]
        outcome_id = extract_quote_outcome_id(sample)
        timing = extract_timing(sample)

        if not outcome_id:
            continue

        if timing == "entry":
            by_outcome[outcome_id]["entry_groups"][gkey] = rows
        else:
            by_outcome[outcome_id]["exit_groups"][gkey] = rows

    outcome_rows = []
    quarantine_rows = []
    state_counts = Counter()
    strategy_counts = Counter()

    for outcome_id, bundle in sorted(by_outcome.items()):
        entry_groups = bundle["entry_groups"]
        exit_groups = bundle["exit_groups"]

        entry_action_by_leg_key: dict[str, str] = {}

        entry_legs = []
        for gkey, rows in entry_groups.items():
            best = choose_best_candidate(rows, options)
            leg = make_leg(best, "entry", entry_action_by_leg_key)
            entry_legs.append(leg)

            entry_action_key = "|".join([
                outcome_id,
                leg["leg_selection_id"],
                leg["role"],
                leg["symbol"],
                norm_date(leg["expiration"]),
                norm_strike(leg["strike"]),
                leg["option_right"],
            ])
            entry_action_by_leg_key[entry_action_key] = leg["action"]

        exit_legs = []
        for gkey, rows in exit_groups.items():
            best = choose_best_candidate(rows, options)
            leg = make_leg(best, "exit", entry_action_by_leg_key)
            exit_legs.append(leg)

        all_legs = entry_legs + exit_legs
        present_ready = all(leg["quality"] == "present" for leg in all_legs) and bool(entry_legs) and bool(exit_legs)
        weak_ready = all(leg["quality"] in ("present", "weak") for leg in all_legs) and bool(entry_legs) and bool(exit_legs)

        if present_ready:
            readiness = "official_bid_ask_ready"
        elif weak_ready:
            readiness = "diagnostic_weak_ready"
        else:
            readiness = "quarantined_missing_quote"

        entry_mid = 0.0
        exit_mid = 0.0
        entry_natural = 0.0
        exit_natural = 0.0
        pnl_mid = None
        pnl_natural = None
        pnl_natural_commission = None

        if weak_ready:
            for leg in entry_legs:
                p_mid = to_float(leg.get("mid"))
                p_nat = price_for_action(leg, leg["action"], "mid")
                sign = action_sign(leg["action"], "entry")

                if p_mid is not None:
                    entry_mid += sign * p_mid * 100.0
                if p_nat is not None:
                    entry_natural += sign * p_nat * 100.0

            for leg in exit_legs:
                p_mid = to_float(leg.get("mid"))
                p_nat = price_for_action(leg, leg["action"], "mid")
                sign = action_sign(leg["action"], "exit")

                if p_mid is not None:
                    exit_mid += sign * p_mid * 100.0
                if p_nat is not None:
                    exit_natural += sign * p_nat * 100.0

            pnl_mid = entry_mid + exit_mid
            pnl_natural = entry_natural + exit_natural
            pnl_natural_commission = pnl_natural - (len(all_legs) * args.commission_per_contract)

        row = {
            "quote_outcome_id": outcome_id,
            "selected_quote_outcome_id": outcome_id,
            "entry_leg_count": len(entry_legs),
            "exit_leg_count": len(exit_legs),
            "total_leg_quote_count": len(all_legs),
            "raw_leg_readiness_state": readiness,
            "entry_legs": entry_legs,
            "exit_legs": exit_legs,
            "entry_net_mid_cashflow": entry_mid if weak_ready else None,
            "exit_net_mid_cashflow": exit_mid if weak_ready else None,
            "raw_mid_unit_pnl": pnl_mid,
            "entry_natural_cashflow": entry_natural if weak_ready else None,
            "exit_natural_cashflow": exit_natural if weak_ready else None,
            "raw_natural_bid_ask_unit_pnl": pnl_natural,
            "raw_natural_bid_ask_commission_unit_pnl": pnl_natural_commission,
            "commission_per_contract": args.commission_per_contract,
            "source": "canonical_options_resolution_rebuild",
        }

        state_counts[readiness] += 1

        if readiness == "quarantined_missing_quote":
            quarantine_rows.append(row)
        else:
            outcome_rows.append(row)

    summary = {
        "adapter_type": "canonical_contract_outcomes_from_option_resolution_builder",
        "artifact_type": "signalforge_canonical_contract_outcomes",
        "is_ready": True,
        "readiness_state": "contract_outcomes_built",
        "required_manifest": str(required_path),
        "canonical_options": str(options_path),
        "outcome_count": len(outcome_rows),
        "quarantine_count": len(quarantine_rows),
        "state_counts": dict(state_counts),
        "source_required_row_count": source_required_row_count,
        "synthetic_entry_row_count": synthetic_entry_row_count,
        "required_group_count_after_synthetic_entries": len(groups),
        "commission_per_contract": args.commission_per_contract,
        "paths": {
            "outcomes": str(output_dir / "signalforge_canonical_contract_outcomes_20210601_20260531.jsonl"),
            "quarantine": str(output_dir / "signalforge_canonical_contract_outcomes_quarantine_20210601_20260531.jsonl"),
            "summary": str(output_dir / "signalforge_canonical_contract_outcomes_summary_20210601_20260531.json"),
        },
        "blockers": [],
    }

    write_jsonl(output_dir / "signalforge_canonical_contract_outcomes_20210601_20260531.jsonl", outcome_rows)
    write_jsonl(output_dir / "signalforge_canonical_contract_outcomes_quarantine_20210601_20260531.jsonl", quarantine_rows)
    write_json(output_dir / "signalforge_canonical_contract_outcomes_summary_20210601_20260531.json", summary)

    print(json.dumps(summary, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
