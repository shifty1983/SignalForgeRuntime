import csv
import gzip
import json
import os
import re
from pathlib import Path
from collections import defaultdict, Counter
from typing import Any, Dict, Iterable, List, Optional, Tuple

OUT_DIR = Path(os.environ.get(
    "SIGNALFORGE_NATIVE_QUOTE_JOIN_OUT_DIR",
    "artifacts/v3_2_1_native_quote_join_v1_20230101_20260531",
))


def env_path(name: str, default: str) -> Path:
    return Path(os.environ.get(name, default))


def env_path_list(name: str, defaults: list[str]) -> list[Path]:
    raw = os.environ.get(name, "")
    if raw.strip():
        return [Path(part) for part in raw.split(os.pathsep) if part.strip()]
    return [Path(part) for part in defaults]


LEGACY_SOURCE_PATH_ROOT = os.environ.get(
    "SIGNALFORGE_NATIVE_QUOTE_JOIN_LEGACY_SOURCE_PATH_ROOT",
    "",
).strip()


def legacy_source_path(path_value: str) -> str:
    if not LEGACY_SOURCE_PATH_ROOT:
        return path_value

    try:
        path_obj = Path(path_value)
        root_obj = Path(LEGACY_SOURCE_PATH_ROOT)

        rel = path_obj.resolve().relative_to(root_obj.resolve())
        return str(rel)
    except Exception:
        return path_value


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    SUMMARY_PATH = OUT_DIR / "signalforge_v3_2_1_native_quote_join_summary.json"
    INVENTORY_PATH = OUT_DIR / "signalforge_v3_2_1_native_quote_source_inventory.json"
    ROW_AUDIT_PATH = OUT_DIR / "signalforge_v3_2_1_native_quote_join_row_audit.jsonl"

    SCENARIOS = {
        "30k": {
            "starting_capital": 30000.0,
            "input_ledger": env_path(
                "SIGNALFORGE_NATIVE_QUOTE_JOIN_30K_LEDGER",
                "artifacts/v3_2_1_spread_guardrail_metrics_stress_20230101_20260531/v3_2_1_30k/ledger.jsonl",
            ),
            "output_ledger": OUT_DIR / "v3_2_1_native_quote_join_30k" / "ledger.jsonl",
        },
        "40k": {
            "starting_capital": 40000.0,
            "input_ledger": env_path(
                "SIGNALFORGE_NATIVE_QUOTE_JOIN_40K_LEDGER",
                "artifacts/v3_2_1_spread_guardrail_metrics_stress_20230101_20260531/v3_2_1_40k/ledger.jsonl",
            ),
            "output_ledger": OUT_DIR / "v3_2_1_native_quote_join_40k" / "ledger.jsonl",
        },
    }

    SEARCH_ROOTS = env_path_list(
        "SIGNALFORGE_NATIVE_QUOTE_JOIN_SEARCH_ROOTS",
        ["artifacts", "data"],
    )

    EXCLUDED_SEARCH_PATHS = env_path_list(
        "SIGNALFORGE_NATIVE_QUOTE_JOIN_EXCLUDED_SEARCH_PATHS",
        [],
    )
    EXCLUDED_SEARCH_PATHS_RESOLVED = [path.resolve() for path in EXCLUDED_SEARCH_PATHS]

    # Prefer likely quote artifacts first. Discovery still scans recursively.
    PREFERRED_QUOTE_PATH_PATTERNS = [
        "portfolio_exit_contract_daily_quote_merge",
        "portfolio_exit_daily_quote_path",
        "quote_merge",
        "quote_path",
        "option_quote",
        "option_chain",
        "quantconnect_option",
    ]

    BID_FIELDS = [
        "bid", "Bid", "BID",
        "option_bid", "quote_bid", "bid_price", "entry_bid", "exit_bid",
        "contract_bid", "close_bid", "open_bid",
    ]

    ASK_FIELDS = [
        "ask", "Ask", "ASK",
        "option_ask", "quote_ask", "ask_price", "entry_ask", "exit_ask",
        "contract_ask", "close_ask", "open_ask",
    ]

    MID_FIELDS = [
        "mid", "Mid", "MID",
        "mark", "mark_price", "mid_price", "quote_mid", "option_mid",
    ]

    DATE_FIELDS = [
        "date", "quote_date", "time", "timestamp", "datetime", "end_time",
        "entry_date", "exit_date", "decision_date", "asof_date",
    ]

    CONTRACT_SYMBOL_FIELDS = [
        "contract_symbol", "option_symbol", "option_contract_symbol", "contract",
        "contract_id", "qc_symbol", "mapped_contract_symbol", "occ_symbol",
        "canonical_option_symbol",
    ]

    UNDERLYING_FIELDS = [
        "underlying", "underlying_symbol", "symbol", "ticker", "root_symbol",
    ]

    EXPIRATION_FIELDS = [
        "expiration", "expiry", "expiration_date", "expiry_date",
        "contract_expiration", "option_expiration",
    ]

    STRIKE_FIELDS = [
        "strike", "strike_price", "contract_strike", "option_strike",
    ]

    RIGHT_FIELDS = [
        "right", "option_right", "put_call", "call_put", "option_type",
        "contract_right", "type",
    ]

    QUANTITY_FIELDS = [
        "quantity", "adjusted_quantity", "contract_count", "allocated_contract_count", "contracts",
    ]

    PNL_FIELDS = [
        "allocated_pnl", "adjusted_allocated_pnl", "realized_pnl_dollars", "pnl_dollars", "realized_pnl",
    ]

    ENTRY_DATE_FIELDS = [
        "entry_date", "trade_date", "decision_date", "date",
    ]

    EXIT_DATE_FIELDS = [
        "realization_date", "portfolio_realization_date", "exit_date", "close_date", "outcome_date", "decision_date",
    ]

    LEG_CONTAINER_FIELDS = [
        "legs", "strategy_legs", "option_legs", "selected_legs",
        "selected_contracts", "position_legs", "contract_legs",
    ]

    LEG_SIDE_FIELDS = [
        "side", "action", "direction", "position_side", "leg_side", "open_action",
    ]

    LEG_RATIO_FIELDS = [
        "ratio", "leg_ratio", "quantity", "qty", "contracts", "contract_count",
    ]

    def read_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
        opener = gzip.open if path.suffix.lower() == ".gz" else open
        with opener(path, "rt", encoding="utf-8-sig", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        yield json.loads(line)
                    except Exception:
                        continue

    def read_csv_rows(path: Path) -> Iterable[Dict[str, Any]]:
        opener = gzip.open if path.suffix.lower() == ".gz" else open
        with opener(path, "rt", encoding="utf-8-sig", errors="ignore", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                yield dict(row)

    def read_json_rows(path: Path) -> Iterable[Dict[str, Any]]:
        try:
            text = path.read_text(encoding="utf-8-sig", errors="ignore")
            obj = json.loads(text)
        except Exception:
            return

        if isinstance(obj, list):
            for row in obj:
                if isinstance(row, dict):
                    yield row
        elif isinstance(obj, dict):
            # Common wrapper formats.
            for key in [
                "rows", "data", "quotes", "records", "items",
                "contract_quotes", "option_quotes", "snapshots",
            ]:
                val = obj.get(key)
                if isinstance(val, list):
                    for row in val:
                        if isinstance(row, dict):
                            yield row
                    return

            # Single row dict fallback.
            yield obj

    def iter_rows(path: Path) -> Iterable[Dict[str, Any]]:
        name = path.name.lower()
        suffixes = "".join(path.suffixes).lower()

        if suffixes.endswith(".jsonl") or suffixes.endswith(".jsonl.gz"):
            yield from read_jsonl(path)
        elif suffixes.endswith(".csv") or suffixes.endswith(".csv.gz"):
            yield from read_csv_rows(path)
        elif suffixes.endswith(".json"):
            yield from read_json_rows(path)

    def write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, sort_keys=True, separators=(",", ":"), default=str) + "\n")

    def pick(row: Dict[str, Any], fields: List[str], default=None) -> Tuple[Any, Optional[str]]:
        for field in fields:
            if field in row and row[field] is not None and str(row[field]).strip() != "":
                return row[field], field
        return default, None

    def fnum(x, default=None):
        try:
            if x is None:
                return default
            s = str(x).strip()
            if s == "":
                return default
            return float(s)
        except Exception:
            return default

    def quantity(row: Dict[str, Any]) -> float:
        v, _ = pick(row, QUANTITY_FIELDS, 0.0)
        return fnum(v, 0.0) or 0.0

    def pnl(row: Dict[str, Any]) -> float:
        v, _ = pick(row, PNL_FIELDS, 0.0)
        return fnum(v, 0.0) or 0.0

    def row_state(row: Dict[str, Any]) -> str:
        v, _ = pick(row, ["row_state", "sizing_state", "adjusted_row_state"], "accepted")
        return str(v).lower()

    def accepted(row: Dict[str, Any]) -> bool:
        if quantity(row) <= 0:
            return False
        s = row_state(row)
        return not ("skip" in s or "reject" in s)

    def date10(x) -> Optional[str]:
        if x is None:
            return None
        s = str(x).strip()
        if not s:
            return None

        # ISO-like date at beginning.
        m = re.search(r"(\d{4}-\d{2}-\d{2})", s)
        if m:
            return m.group(1)

        # Basic YYYYMMDD.
        m = re.search(r"(\d{8})", s)
        if m:
            raw = m.group(1)
            return f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"

        return s[:10]

    def norm_text(x) -> Optional[str]:
        if x is None:
            return None
        s = str(x).strip()
        if not s:
            return None
        return s.upper().replace(" ", "")

    def norm_underlying(x) -> Optional[str]:
        s = norm_text(x)
        if not s:
            return None
        # Keep simple symbol if QC-style value appears.
        if " " in s:
            s = s.split(" ")[0]
        return s

    def norm_contract(x) -> Optional[str]:
        s = norm_text(x)
        if not s:
            return None
        return s

    def norm_right(x) -> Optional[str]:
        s = norm_text(x)
        if not s:
            return None
        if s in ("C", "CALL", "0"):
            return "C"
        if s in ("P", "PUT", "1"):
            return "P"
        if "CALL" in s:
            return "C"
        if "PUT" in s:
            return "P"
        return s[:1]

    def norm_strike(x) -> Optional[str]:
        v = fnum(x, None)
        if v is None:
            return None
        return f"{v:.4f}".rstrip("0").rstrip(".")

    def norm_expiration(x) -> Optional[str]:
        return date10(x)

    def get_date(row: Dict[str, Any], fields: List[str]) -> Optional[str]:
        v, _ = pick(row, fields, None)
        return date10(v)

    def get_contract_symbol(row: Dict[str, Any]) -> Optional[str]:
        v, _ = pick(row, CONTRACT_SYMBOL_FIELDS, None)
        return norm_contract(v)

    def get_underlying(row: Dict[str, Any]) -> Optional[str]:
        v, _ = pick(row, UNDERLYING_FIELDS, None)
        return norm_underlying(v)

    def get_expiration(row: Dict[str, Any]) -> Optional[str]:
        v, _ = pick(row, EXPIRATION_FIELDS, None)
        return norm_expiration(v)

    def get_strike(row: Dict[str, Any]) -> Optional[str]:
        v, _ = pick(row, STRIKE_FIELDS, None)
        return norm_strike(v)

    def get_right(row: Dict[str, Any]) -> Optional[str]:
        v, _ = pick(row, RIGHT_FIELDS, None)
        return norm_right(v)

    def quote_keys_from_record(row: Dict[str, Any]) -> List[Tuple[str, ...]]:
        d = get_date(row, DATE_FIELDS)
        if not d:
            return []

        keys = []

        cs = get_contract_symbol(row)
        if cs:
            keys.append(("contract", cs, d))

        u = get_underlying(row)
        exp = get_expiration(row)
        strike = get_strike(row)
        right = get_right(row)

        if u and exp and strike and right:
            keys.append(("tuple", u, exp, strike, right, d))

        return keys

    def leg_keys(leg: Dict[str, Any], target_date: str) -> List[Tuple[str, ...]]:
        keys = []

        cs = get_contract_symbol(leg)
        if cs:
            keys.append(("contract", cs, target_date))

        u = get_underlying(leg)
        exp = get_expiration(leg)
        strike = get_strike(leg)
        right = get_right(leg)

        if u and exp and strike and right:
            keys.append(("tuple", u, exp, strike, right, target_date))

        return keys

    def quote_values(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        bid, bid_field = pick(row, BID_FIELDS, None)
        ask, ask_field = pick(row, ASK_FIELDS, None)
        mid, mid_field = pick(row, MID_FIELDS, None)

        bid_f = fnum(bid, None)
        ask_f = fnum(ask, None)
        mid_f = fnum(mid, None)

        if bid_f is None or ask_f is None:
            return None

        if ask_f <= 0:
            return None

        if bid_f < 0:
            return None

        if bid_f > ask_f:
            sanity = "crossed_market"
        else:
            sanity = "ok"

        if mid_f is None:
            mid_f = (bid_f + ask_f) / 2.0

        spread = ask_f - bid_f
        spread_pct = spread / mid_f if mid_f and mid_f > 0 else None

        return {
            "bid": bid_f,
            "ask": ask_f,
            "mid": mid_f,
            "spread": spread,
            "spread_pct": spread_pct,
            "bid_field": bid_field,
            "ask_field": ask_field,
            "mid_field": mid_field,
            "sanity": sanity,
        }

    def sample_file(path: Path, max_rows: int = 200) -> List[Dict[str, Any]]:
        rows = []
        try:
            for row in iter_rows(path):
                if isinstance(row, dict):
                    rows.append(row)
                    if len(rows) >= max_rows:
                        break
        except Exception:
            return []
        return rows

    def is_quote_candidate(path: Path, sample_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        field_counts = Counter()
        bid_count = 0
        ask_count = 0
        date_count = 0
        identity_count = 0

        for row in sample_rows:
            fields = set(row.keys())
            field_counts.update(fields)

            if any(f in fields for f in BID_FIELDS):
                bid_count += 1
            if any(f in fields for f in ASK_FIELDS):
                ask_count += 1
            if any(f in fields for f in DATE_FIELDS):
                date_count += 1

            has_contract = any(f in fields for f in CONTRACT_SYMBOL_FIELDS)
            has_tuple = (
                any(f in fields for f in UNDERLYING_FIELDS)
                and any(f in fields for f in EXPIRATION_FIELDS)
                and any(f in fields for f in STRIKE_FIELDS)
                and any(f in fields for f in RIGHT_FIELDS)
            )

            if has_contract or has_tuple:
                identity_count += 1

        score = 0
        if bid_count:
            score += 1
        if ask_count:
            score += 1
        if date_count:
            score += 1
        if identity_count:
            score += 1

        path_lower = str(path).lower()
        name_bonus = any(p in path_lower for p in PREFERRED_QUOTE_PATH_PATTERNS)

        is_candidate = score >= 4

        return {
            "path": str(path),
            "sample_row_count": len(sample_rows),
            "is_quote_candidate": is_candidate,
            "score": score + (1 if name_bonus else 0),
            "has_bid": bid_count > 0,
            "has_ask": ask_count > 0,
            "has_date": date_count > 0,
            "has_identity": identity_count > 0,
            "name_bonus": name_bonus,
            "top_fields": field_counts.most_common(60),
        }

    def discover_quote_sources() -> List[Dict[str, Any]]:
        candidates = []
        allowed_suffixes = (
            ".jsonl", ".json", ".csv",
            ".jsonl.gz", ".csv.gz",
        )

        paths = []
        for root in SEARCH_ROOTS:
            if not root.exists():
                continue

            for p in root.rglob("*"):
                if not p.is_file():
                    continue

                suffixes = "".join(p.suffixes).lower()
                if not any(suffixes.endswith(s) for s in allowed_suffixes):
                    continue

                low = str(p).lower()
                if not any(token in low for token in ["quote", "option", "chain", "contract"]):
                    continue

                # Avoid reading our own current output folder.
                if str(OUT_DIR).lower() in low:
                    continue

                paths.append(p)

        # Prefer likely quote paths first.
        paths = sorted(
            paths,
            key=lambda p: (
                0 if any(pattern in str(p).lower() for pattern in PREFERRED_QUOTE_PATH_PATTERNS) else 1,
                str(p).lower(),
            )
        )

        for path in paths:
            sample_rows = sample_file(path, 200)
            if not sample_rows:
                continue
            inv = is_quote_candidate(path, sample_rows)
            candidates.append(inv)

        return candidates

    def extract_nested_legs(row: Dict[str, Any]) -> List[Dict[str, Any]]:
        for field in LEG_CONTAINER_FIELDS:
            val = row.get(field)
            if isinstance(val, list):
                legs = [x for x in val if isinstance(x, dict)]
                if legs:
                    return legs
        return []

    def extract_prefixed_legs(row: Dict[str, Any]) -> List[Dict[str, Any]]:
        legs = []

        # Handles leg_1_contract_symbol, leg1_strike, leg2_right, etc.
        groups = defaultdict(dict)

        for key, value in row.items():
            m = re.match(r"^(leg[_-]?)(\d+)[_-](.+)$", key, flags=re.IGNORECASE)
            if not m:
                continue
            idx = m.group(2)
            field = m.group(3)
            groups[idx][field] = value

        for idx in sorted(groups.keys(), key=lambda x: int(x)):
            leg = groups[idx]
            if leg:
                legs.append(leg)

        return legs

    def extract_row_as_single_leg(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        has_contract = any(f in row for f in CONTRACT_SYMBOL_FIELDS)
        has_tuple = (
            any(f in row for f in UNDERLYING_FIELDS)
            and any(f in row for f in EXPIRATION_FIELDS)
            and any(f in row for f in STRIKE_FIELDS)
            and any(f in row for f in RIGHT_FIELDS)
        )

        if has_contract or has_tuple:
            return dict(row)

        return None

    def extract_legs(row: Dict[str, Any]) -> List[Dict[str, Any]]:
        legs = extract_nested_legs(row)
        if legs:
            return legs

        legs = extract_prefixed_legs(row)
        if legs:
            return legs

        single = extract_row_as_single_leg(row)
        if single is not None:
            return [single]

        return []

    def leg_identity_summary(leg: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "contract_symbol": get_contract_symbol(leg),
            "underlying": get_underlying(leg),
            "expiration": get_expiration(leg),
            "strike": get_strike(leg),
            "right": get_right(leg),
        }

    def summarize_quote_match(q: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if q is None:
            return None
        return {
            "source_path": q["source_path"],
            "source_row_index": q["source_row_index"],
            "bid": q["bid"],
            "ask": q["ask"],
            "mid": q["mid"],
            "spread": q["spread"],
            "spread_pct": q["spread_pct"],
            "sanity": q["sanity"],
            "key_used": q["key_used"],
        }

    def build_required_keys() -> Tuple[Dict[str, List[Dict[str, Any]]], set, List[Dict[str, Any]], List[str]]:
        scenario_rows = {}
        required_keys = set()
        target_leg_audit = []
        blockers = []

        for capital_label, cfg in SCENARIOS.items():
            if not cfg["input_ledger"].exists():
                blockers.append(f"missing_v3_2_1_ledger_{capital_label}: {cfg['input_ledger']}")
                continue

            rows = list(read_jsonl(cfg["input_ledger"]))
            scenario_rows[capital_label] = rows

            for row_idx, row in enumerate(rows):
                if not accepted(row):
                    continue

                entry_date = get_date(row, ENTRY_DATE_FIELDS)
                exit_date = get_date(row, EXIT_DATE_FIELDS)
                legs = extract_legs(row)

                leg_identity_missing = False

                for leg_idx, leg in enumerate(legs):
                    identity = leg_identity_summary(leg)

                    for d, role in [(entry_date, "entry"), (exit_date, "exit")]:
                        if d:
                            keys = leg_keys(leg, d)
                            for key in keys:
                                required_keys.add(key)

                    if not leg_keys(leg, entry_date or "1900-01-01"):
                        leg_identity_missing = True

                    target_leg_audit.append({
                        "capital_label": capital_label,
                        "row_index": row_idx,
                        "leg_index": leg_idx,
                        "entry_date": entry_date,
                        "exit_date": exit_date,
                        "identity": identity,
                        "has_join_key": bool(
                            (entry_date and leg_keys(leg, entry_date))
                            or (exit_date and leg_keys(leg, exit_date))
                        ),
                    })

                if not legs:
                    target_leg_audit.append({
                        "capital_label": capital_label,
                        "row_index": row_idx,
                        "leg_index": None,
                        "entry_date": entry_date,
                        "exit_date": exit_date,
                        "identity": {},
                        "has_join_key": False,
                        "problem": "no_leg_identity_found_on_ledger_row",
                    })

        return scenario_rows, required_keys, target_leg_audit, blockers

    def index_quote_sources(source_inventory: List[Dict[str, Any]], required_keys: set) -> Tuple[Dict[Tuple[str, ...], Dict[str, Any]], List[Dict[str, Any]]]:
        quote_index = {}
        source_stats = []

        sources = [s for s in source_inventory if s.get("is_quote_candidate")]
        sources = sorted(sources, key=lambda s: -s.get("score", 0))

        for source in sources:
            path = Path(source["path"])

            scanned = 0
            usable_quote_rows = 0
            matched_required_key_rows = 0
            crossed_market_rows = 0

            try:
                for row_idx, row in enumerate(iter_rows(path)):
                    scanned += 1

                    qv = quote_values(row)
                    if qv is None:
                        continue

                    usable_quote_rows += 1

                    if qv["sanity"] == "crossed_market":
                        crossed_market_rows += 1

                    keys = quote_keys_from_record(row)
                    matched_any = False

                    for key in keys:
                        if key not in required_keys:
                            continue

                        matched_any = True

                        # Keep first good market. If current existing is crossed and new is ok, replace it.
                        existing = quote_index.get(key)
                        should_replace = False

                        if existing is None:
                            should_replace = True
                        elif existing.get("sanity") == "crossed_market" and qv["sanity"] == "ok":
                            should_replace = True

                        if should_replace:
                            quote_index[key] = {
                                **qv,
                                "source_path": legacy_source_path(str(path)),
                                "source_row_index": row_idx,
                                "key_used": key,
                            }

                    if matched_any:
                        matched_required_key_rows += 1

            except Exception as e:
                source_stats.append({
                    "path": str(path),
                    "error": repr(e),
                    "scanned_rows": scanned,
                    "usable_quote_rows": usable_quote_rows,
                    "matched_required_key_rows": matched_required_key_rows,
                    "crossed_market_rows": crossed_market_rows,
                })
                continue

            source_stats.append({
                "path": str(path),
                "scanned_rows": scanned,
                "usable_quote_rows": usable_quote_rows,
                "matched_required_key_rows": matched_required_key_rows,
                "crossed_market_rows": crossed_market_rows,
            })

        return quote_index, source_stats

    def find_quote_for_leg(leg: Dict[str, Any], d: Optional[str], quote_index: Dict[Tuple[str, ...], Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], Optional[Tuple[str, ...]]]:
        if not d:
            return None, None

        keys = leg_keys(leg, d)

        for key in keys:
            q = quote_index.get(key)
            if q is not None:
                return q, key

        return None, keys[0] if keys else None

    def enrich_scenario(capital_label: str, rows: List[Dict[str, Any]], quote_index: Dict[Tuple[str, ...], Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
        enriched_rows = []
        audit_rows = []

        active_count = 0
        rows_with_leg_identity = 0
        complete_entry_rows = 0
        complete_exit_rows = 0
        complete_entry_exit_rows = 0
        total_legs = 0
        entry_leg_matches = 0
        exit_leg_matches = 0
        crossed_market_match_count = 0

        entry_spread_cost_per_strategy_unit_values = []
        exit_spread_cost_per_strategy_unit_values = []
        round_trip_half_spread_cost_per_strategy_unit_values = []

        for row_idx, row in enumerate(rows):
            new = dict(row)

            if not accepted(row):
                enriched_rows.append(new)
                continue

            active_count += 1

            entry_date = get_date(row, ENTRY_DATE_FIELDS)
            exit_date = get_date(row, EXIT_DATE_FIELDS)
            legs = extract_legs(row)

            join = {
                "join_version": "v3_2_1_native_quote_join_v1",
                "entry_date": entry_date,
                "exit_date": exit_date,
                "leg_count": len(legs),
                "entry_legs": [],
                "exit_legs": [],
                "has_leg_identity": bool(legs),
                "entry_quote_complete": False,
                "exit_quote_complete": False,
                "entry_exit_quote_complete": False,
                "entry_half_spread_cost_per_strategy_unit": None,
                "exit_half_spread_cost_per_strategy_unit": None,
                "round_trip_half_spread_cost_per_strategy_unit": None,
                "round_trip_half_spread_cost_estimate_for_row": None,
            }

            if legs:
                rows_with_leg_identity += 1

            entry_complete = bool(legs)
            exit_complete = bool(legs)

            entry_half_cost = 0.0
            exit_half_cost = 0.0

            for leg_idx, leg in enumerate(legs):
                total_legs += 1
                identity = leg_identity_summary(leg)

                entry_q, entry_key = find_quote_for_leg(leg, entry_date, quote_index)
                exit_q, exit_key = find_quote_for_leg(leg, exit_date, quote_index)

                if entry_q is None:
                    entry_complete = False
                else:
                    entry_leg_matches += 1
                    if entry_q.get("sanity") == "crossed_market":
                        crossed_market_match_count += 1
                    entry_half_cost += max(entry_q["spread"], 0.0) / 2.0 * 100.0

                if exit_q is None:
                    exit_complete = False
                else:
                    exit_leg_matches += 1
                    if exit_q.get("sanity") == "crossed_market":
                        crossed_market_match_count += 1
                    exit_half_cost += max(exit_q["spread"], 0.0) / 2.0 * 100.0

                join["entry_legs"].append({
                    "leg_index": leg_idx,
                    "identity": identity,
                    "target_key": entry_key,
                    "quote": summarize_quote_match(entry_q),
                    "matched": entry_q is not None,
                })

                join["exit_legs"].append({
                    "leg_index": leg_idx,
                    "identity": identity,
                    "target_key": exit_key,
                    "quote": summarize_quote_match(exit_q),
                    "matched": exit_q is not None,
                })

                audit_rows.append({
                    "capital_label": capital_label,
                    "row_index": row_idx,
                    "leg_index": leg_idx,
                    "entry_date": entry_date,
                    "exit_date": exit_date,
                    "identity": identity,
                    "entry_matched": entry_q is not None,
                    "exit_matched": exit_q is not None,
                    "entry_target_key": entry_key,
                    "exit_target_key": exit_key,
                    "entry_quote": summarize_quote_match(entry_q),
                    "exit_quote": summarize_quote_match(exit_q),
                })

            if entry_complete:
                complete_entry_rows += 1

            if exit_complete:
                complete_exit_rows += 1

            if entry_complete and exit_complete:
                complete_entry_exit_rows += 1

            if legs:
                join["entry_quote_complete"] = entry_complete
                join["exit_quote_complete"] = exit_complete
                join["entry_exit_quote_complete"] = entry_complete and exit_complete

                join["entry_half_spread_cost_per_strategy_unit"] = entry_half_cost if entry_complete else None
                join["exit_half_spread_cost_per_strategy_unit"] = exit_half_cost if exit_complete else None

                if entry_complete and exit_complete:
                    rt = entry_half_cost + exit_half_cost
                    join["round_trip_half_spread_cost_per_strategy_unit"] = rt
                    join["round_trip_half_spread_cost_estimate_for_row"] = rt * quantity(row)

                    entry_spread_cost_per_strategy_unit_values.append(entry_half_cost)
                    exit_spread_cost_per_strategy_unit_values.append(exit_half_cost)
                    round_trip_half_spread_cost_per_strategy_unit_values.append(rt)

            new["native_quote_join"] = join
            enriched_rows.append(new)

        def pct(n, d):
            return n / d if d else 0.0

        def percentile(values, q):
            if not values:
                return None
            vals = sorted(values)
            idx = (len(vals) - 1) * q
            lo = int(idx)
            hi = min(lo + 1, len(vals) - 1)
            frac = idx - lo
            return vals[lo] * (1 - frac) + vals[hi] * frac

        summary = {
            "capital_label": capital_label,
            "active_trade_count": active_count,
            "rows_with_leg_identity": rows_with_leg_identity,
            "leg_identity_coverage": pct(rows_with_leg_identity, active_count),
            "total_leg_count": total_legs,
            "entry_leg_quote_match_count": entry_leg_matches,
            "exit_leg_quote_match_count": exit_leg_matches,
            "entry_leg_quote_coverage": pct(entry_leg_matches, total_legs),
            "exit_leg_quote_coverage": pct(exit_leg_matches, total_legs),
            "complete_entry_quote_rows": complete_entry_rows,
            "complete_exit_quote_rows": complete_exit_rows,
            "complete_entry_exit_quote_rows": complete_entry_exit_rows,
            "complete_entry_quote_row_coverage": pct(complete_entry_rows, active_count),
            "complete_exit_quote_row_coverage": pct(complete_exit_rows, active_count),
            "complete_entry_exit_quote_row_coverage": pct(complete_entry_exit_rows, active_count),
            "crossed_market_match_count": crossed_market_match_count,
            "entry_half_spread_cost_per_strategy_unit_p50": percentile(entry_spread_cost_per_strategy_unit_values, 0.50),
            "entry_half_spread_cost_per_strategy_unit_p90": percentile(entry_spread_cost_per_strategy_unit_values, 0.90),
            "entry_half_spread_cost_per_strategy_unit_p95": percentile(entry_spread_cost_per_strategy_unit_values, 0.95),
            "exit_half_spread_cost_per_strategy_unit_p50": percentile(exit_spread_cost_per_strategy_unit_values, 0.50),
            "exit_half_spread_cost_per_strategy_unit_p90": percentile(exit_spread_cost_per_strategy_unit_values, 0.90),
            "exit_half_spread_cost_per_strategy_unit_p95": percentile(exit_spread_cost_per_strategy_unit_values, 0.95),
            "round_trip_half_spread_cost_per_strategy_unit_p50": percentile(round_trip_half_spread_cost_per_strategy_unit_values, 0.50),
            "round_trip_half_spread_cost_per_strategy_unit_p90": percentile(round_trip_half_spread_cost_per_strategy_unit_values, 0.90),
            "round_trip_half_spread_cost_per_strategy_unit_p95": percentile(round_trip_half_spread_cost_per_strategy_unit_values, 0.95),
        }

        return enriched_rows, audit_rows, summary

    # ============================================================
    # Main
    # ============================================================

    blockers = []
    warnings = []

    scenario_rows, required_keys, target_leg_audit, input_blockers = build_required_keys()
    blockers.extend(input_blockers)

    source_inventory = discover_quote_sources()
    quote_candidates = [s for s in source_inventory if s.get("is_quote_candidate")]

    if not scenario_rows:
        blockers.append("no_v3_2_1_input_ledgers_loaded")

    if not required_keys:
        blockers.append("no_required_quote_join_keys_extracted_from_v3_2_1_ledgers")
        warnings.append("The V3.2.1 ledger rows may not carry option contract identity/leg fields.")

    if not quote_candidates:
        blockers.append("no_quote_source_files_with_bid_ask_identity_discovered")
        warnings.append("No quote files with bid/ask/date/contract identity were discovered under artifacts/ or data/.")

    quote_index = {}
    quote_source_stats = []

    if not blockers:
        quote_index, quote_source_stats = index_quote_sources(source_inventory, required_keys)

        if not quote_index:
            blockers.append("quote_sources_found_but_no_required_keys_matched")
            warnings.append("Quote files exist, but none matched V3.2.1 ledger contract/date keys.")

    scenario_summaries = []
    all_audit_rows = []

    if not blockers:
        for capital_label, rows in scenario_rows.items():
            enriched_rows, audit_rows, scenario_summary = enrich_scenario(capital_label, rows, quote_index)
            all_audit_rows.extend(audit_rows)
            scenario_summaries.append(scenario_summary)

            out_path = SCENARIOS[capital_label]["output_ledger"]
            write_jsonl(out_path, enriched_rows)

    write_jsonl(ROW_AUDIT_PATH, all_audit_rows)

    inventory_payload = {
        "adapter_type": "v3_2_1_native_quote_source_inventory_builder",
        "artifact_type": "signalforge_v3_2_1_native_quote_source_inventory",
        "quote_source_count": len(source_inventory),
        "quote_candidate_count": len(quote_candidates),
        "required_quote_key_count": len(required_keys),
        "matched_quote_key_count": len(quote_index),
        "target_leg_audit_sample": target_leg_audit[:100],
        "source_inventory": source_inventory,
        "quote_source_stats": quote_source_stats,
    }

    INVENTORY_PATH.write_text(json.dumps(inventory_payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")

    if blockers:
        decision = "quote_native_join_blocked"
    else:
        min_complete = min(
            (s["complete_entry_exit_quote_row_coverage"] for s in scenario_summaries),
            default=0.0,
        )

        if min_complete >= 0.99:
            decision = "quote_native_join_passed_preferred_coverage"
        elif min_complete >= 0.95:
            decision = "quote_native_join_passed_minimum_coverage"
        elif min_complete > 0:
            decision = "quote_native_join_partial_coverage"
            warnings.append("Native quote join coverage is below 95%; true quote-native validation remains incomplete.")
        else:
            decision = "quote_native_join_failed_no_complete_rows"

    summary = {
        "adapter_type": "v3_2_1_native_quote_join_builder",
        "artifact_type": "signalforge_v3_2_1_native_quote_join",
        "contract": "v3_2_1_native_quote_join",
        "candidate_id": "signalforge_v3_2_1_spread_guardrail_12_5pct_20230101_20260531",
        "parent_candidate": "signalforge_v3_2_reconciled_canonical_from_v2_locked_actions",
        "is_ready": len(blockers) == 0,
        "readiness_state": "ready" if len(blockers) == 0 else "blocked",
        "decision": decision,
        "blockers": blockers,
        "warnings": warnings,
        "required_quote_key_count": len(required_keys),
        "quote_source_count": len(source_inventory),
        "quote_candidate_count": len(quote_candidates),
        "matched_quote_key_count": len(quote_index),
        "scenario_summaries": scenario_summaries,
        "coverage_thresholds": {
            "minimum_acceptable_complete_entry_exit_quote_row_coverage": 0.95,
            "preferred_complete_entry_exit_quote_row_coverage": 0.99,
        },
        "paths": {
            "summary": str(SUMMARY_PATH),
            "inventory": str(INVENTORY_PATH),
            "row_audit": str(ROW_AUDIT_PATH),
            "v3_2_1_native_quote_join_30k_ledger": str(SCENARIOS["30k"]["output_ledger"]),
            "v3_2_1_native_quote_join_40k_ledger": str(SCENARIOS["40k"]["output_ledger"]),
        },
        "next_step_if_passed": "Run native quote fill/PnL reconstruction and quote-native stress using enriched ledgers.",
        "next_step_if_blocked": "Inspect source inventory and target leg audit to identify missing contract identity or missing quote source files.",
    }

    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")

    print(json.dumps(summary, indent=2, sort_keys=True, default=str))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())




