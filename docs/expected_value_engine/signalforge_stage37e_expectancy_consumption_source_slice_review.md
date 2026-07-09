# Stage 37E Expectancy Consumption Source Slice Review

- is_ready: True
- blocker_count: 0
- closure_group_count: 2
- reviewed_symbol_count: 23
- engine_expectancy_consumption_symbol_count: 21
- backtesting_expectancy_generation_symbol_count: 2
- paper_expectancy_consumption_entrypoint: `signalforge.engines.strategy_selection.expected_value_scoring.build_signalforge_expected_value_scoring`
- walk_forward_generation_owner: `src/signalforge/backtesting/walk_forward_expectancy_builder.py`
- paper_order_created: False
- live_order_created: False
- live_trade_supported: False

## Closure Groups

| source | roots | closure count | closure |
|---|---|---:|---|
| `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | _state_for_stats | 2 | RunningStats, _state_for_stats |
| `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | build_signalforge_expected_value_scoring, _build_ev_item, _candidate_families, _score_family_candidate, _candidate_ev_state, _item_ev_state, _candidate_handoff_status, _summary, _blocked_result | 21 | _blocked_result, _clean_text, _as_string_list, _ordered, _candidate_families, _candidate_handoff_status, _clean_symbol, _first_value, _item_ev_state, _candidate_ev_state, _clamp_score, _constraint_penalty, _premium_alignment_adjustment, _risk_penalty, _score_family_candidate, _build_ev_item, _looks_like_items, _extract_items, _source_artifact_type, _summary, build_signalforge_expected_value_scoring |

## Symbol Review

| symbol | source | ownership | action | target | internal funcs | imports | module bindings | unresolved |
|---|---|---|---|---|---|---|---|---|
| `RunningStats` | `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | backtesting_generation_policy_candidate | review_for_contract_alignment_do_not_extract_now | `none` |  | List, Optional, dataclass, date, field, median |  |  |
| `_state_for_stats` | `src/signalforge/backtesting/walk_forward_expectancy_builder.py` | backtesting_generation_policy_candidate | review_for_contract_alignment_do_not_extract_now | `none` |  | Optional |  |  |
| `_blocked_result` | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | engine_expectancy_consumption_helper | keep_in_engine_verify_snapshot_contract | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` |  | Any, EXPLICIT_EXCLUSIONS, Mapping, Sequence | COVERED_CAPABILITIES, DEPENDS_ON_CAPABILITIES, EXPECTED_VALUE_SCORING_SCHEMA_VERSION |  |
| `_clean_text` | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | engine_expectancy_consumption_helper | keep_in_engine_verify_snapshot_contract | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` |  | Any |  |  |
| `_as_string_list` | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | engine_expectancy_consumption_helper | keep_in_engine_verify_snapshot_contract | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | _clean_text | Any, Sequence |  |  |
| `_ordered` | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | engine_expectancy_consumption_helper | keep_in_engine_verify_snapshot_contract | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` |  |  | FAMILY_ORDER |  |
| `_candidate_families` | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | engine_expectancy_consumption_helper | keep_in_engine_verify_snapshot_contract | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | _ordered |  | NON_EV_FAMILIES |  |
| `_candidate_handoff_status` | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | engine_expectancy_consumption_helper | keep_in_engine_verify_snapshot_contract | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` |  |  |  |  |
| `_clean_symbol` | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | engine_expectancy_consumption_helper | keep_in_engine_verify_snapshot_contract | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | _clean_text | Any |  |  |
| `_first_value` | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | engine_expectancy_consumption_helper | keep_in_engine_verify_snapshot_contract | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` |  | Any, Mapping, Sequence |  |  |
| `_item_ev_state` | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | engine_expectancy_consumption_helper | keep_in_engine_verify_snapshot_contract | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` |  | Any, Mapping |  |  |
| `_candidate_ev_state` | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | engine_expectancy_consumption_helper | keep_in_engine_verify_snapshot_contract | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` |  |  |  |  |
| `_clamp_score` | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | engine_expectancy_consumption_helper | keep_in_engine_verify_snapshot_contract | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` |  |  |  |  |
| `_constraint_penalty` | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | engine_expectancy_consumption_helper | keep_in_engine_verify_snapshot_contract | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` |  | Sequence | CONSTRAINT_PENALTY_MAP |  |
| `_premium_alignment_adjustment` | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | engine_expectancy_consumption_helper | keep_in_engine_verify_snapshot_contract | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` |  |  | LONG_PREMIUM_FAMILIES, PREMIUM_ALIGNMENT_BONUS, PREMIUM_MISMATCH_PENALTY, SHORT_PREMIUM_FAMILIES |  |
| `_risk_penalty` | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | engine_expectancy_consumption_helper | keep_in_engine_verify_snapshot_contract | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` |  | Sequence | RISK_PENALTY_MAP |  |
| `_score_family_candidate` | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | engine_expectancy_consumption_helper | keep_in_engine_verify_snapshot_contract | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | _candidate_ev_state, _clamp_score, _constraint_penalty, _premium_alignment_adjustment, _risk_penalty | Any, Sequence | BASE_SCORE_ALLOWED, BASE_SCORE_FAVORED, CONSTRAINED_REVIEW_PENALTY, EV_CONSTRAINED_HANDOFF |  |
| `_build_ev_item` | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | engine_expectancy_consumption_helper | keep_in_engine_verify_snapshot_contract | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | _as_string_list, _candidate_families, _candidate_handoff_status, _clean_symbol, _clean_text, _first_value, _item_ev_state, _ordered, _score_family_candidate | Any, EXPLICIT_EXCLUSIONS, Mapping | BLOCKED_HANDOFF, DATA_REVIEW_HANDOFF, EV_CONSTRAINED_HANDOFF, FAMILY_ORDER |  |
| `_looks_like_items` | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | engine_expectancy_consumption_helper | keep_in_engine_verify_snapshot_contract | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` |  | Any, Sequence |  |  |
| `_extract_items` | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | engine_expectancy_consumption_helper | keep_in_engine_verify_snapshot_contract | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | _looks_like_items | Any, Mapping, Sequence |  |  |
| `_source_artifact_type` | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | engine_expectancy_consumption_helper | keep_in_engine_verify_snapshot_contract | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | _clean_text | Any, Mapping, Sequence |  |  |
| `_summary` | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | engine_expectancy_consumption_helper | keep_in_engine_verify_snapshot_contract | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` |  | Any, Counter, Mapping, Sequence | COVERED_CAPABILITIES, DEPENDS_ON_CAPABILITIES |  |
| `build_signalforge_expected_value_scoring` | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | engine_expectancy_consumption_entrypoint | keep_in_engine_as_paper_consumption_candidate | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | _blocked_result, _build_ev_item, _extract_items, _source_artifact_type, _summary | Any, EXPLICIT_EXCLUSIONS, Mapping, Sequence | COVERED_CAPABILITIES, DEPENDS_ON_CAPABILITIES, ELIGIBILITY_ITEM_KEYS, EXPECTED_VALUE_SCORING_SCHEMA_VERSION |  |

## Source Slices

### `RunningStats`

- source: `src/signalforge/backtesting/walk_forward_expectancy_builder.py`
- ownership: backtesting_generation_policy_candidate
- action: review_for_contract_alignment_do_not_extract_now
- signature: `class RunningStats`
- reason: state mapping is part of tested walk-forward output semantics

```python
class RunningStats:
    count: int = 0
    win_count: int = 0
    total_return: float = 0.0
    returns: List[float] = field(default_factory=list)
    first_availability_date: Optional[date] = None
    last_availability_date: Optional[date] = None

    def add(self, value: float, availability_date: date) -> None:
        self.count += 1
        if value > 0:
            self.win_count += 1
        self.total_return += value
        self.returns.append(value)

        if self.first_availability_date is None or availability_date < self.first_availability_date:
            self.first_availability_date = availability_date

        if self.last_availability_date is None or availability_date > self.last_availability_date:
            self.last_availability_date = availability_date

    @property
    def average_return(self) -> Optional[float]:
        if self.count == 0:
            return None
        return self.total_return / self.count

    @property
    def median_return(self) -> Optional[float]:
        if self.count == 0:
            return None
        return float(median(self.returns))

    @property
    def win_rate(self) -> Optional[float]:
        if self.count == 0:
            return None
        return self.win_count / self.count
```

### `_state_for_stats`

- source: `src/signalforge/backtesting/walk_forward_expectancy_builder.py`
- ownership: backtesting_generation_policy_candidate
- action: review_for_contract_alignment_do_not_extract_now
- signature: `def _state_for_stats(stats: Optional[RunningStats], minimum_sample_count: int):`
- reason: state mapping is part of tested walk-forward output semantics

```python
def _state_for_stats(stats: Optional[RunningStats], minimum_sample_count: int) -> str:
    if stats is None or stats.count == 0:
        return "no_prior_sample"

    if stats.count < minimum_sample_count:
        return "sample_limited"

    average_return = stats.average_return or 0.0
    win_rate = stats.win_rate or 0.0

    if average_return > 0 and win_rate >= 0.50:
        return "positive_expectancy_candidate"

    if average_return < 0 and win_rate < 0.50:
        return "negative_expectancy_candidate"

    return "mixed_expectancy"
```

### `_blocked_result`

- source: `src/signalforge/engines/strategy_selection/expected_value_scoring.py`
- ownership: engine_expectancy_consumption_helper
- action: keep_in_engine_verify_snapshot_contract
- signature: `def _blocked_result(blocked_reasons: Sequence[str], *, source_artifacts: Mapping[str, Any]):`
- reason: existing engine-owned scoring helper, should be validated against locked expectancy snapshot contract

```python
def _blocked_result(blocked_reasons: Sequence[str], *, source_artifacts: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "artifact_type": "signalforge_expected_value_scoring",
        "schema_version": EXPECTED_VALUE_SCORING_SCHEMA_VERSION,
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "contract": "expected_value_scoring",
        "adapter_type": "expected_value_scoring_builder",
        "review_scope": "risk_adjusted_expected_value_scoring_not_trade_selection_or_execution",
        "source_artifacts": dict(source_artifacts),
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "blocked_reasons": list(blocked_reasons),
        "expected_value_items": [],
        "ev_items": [],
        "expected_value_summary": {
            "covered_capabilities": list(COVERED_CAPABILITIES),
            "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
            "symbol_count": 0,
            "ready_symbol_count": 0,
            "constrained_symbol_count": 0,
            "ev_scoreable_symbol_count": 0,
            "risk_adjusted_ev_symbol_count": 0,
            "data_review_symbol_count": 0,
            "blocked_symbol_count": 0,
            "needs_review_symbol_count": 0,
            "manual_review_symbol_count": 0,
            "positive_or_marginal_symbol_count": 0,
            "scored_candidate_count": 0,
            "coverage_status_counts": {},
            "expected_value_state_counts": {},
            "best_strategy_family_counts": {},
            "candidate_expected_value_state_counts": {},
            "candidate_strategy_family_counts": {},
            "handoff_counts": {},
            "risk_flag_counts": {},
            "constraint_flag_counts": {},
            "data_review_reason_counts": {},
        },
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }
```

### `_clean_text`

- source: `src/signalforge/engines/strategy_selection/expected_value_scoring.py`
- ownership: engine_expectancy_consumption_helper
- action: keep_in_engine_verify_snapshot_contract
- signature: `def _clean_text(value: Any):`
- reason: existing engine-owned scoring helper, should be validated against locked expectancy snapshot contract

```python
def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
```

### `_as_string_list`

- source: `src/signalforge/engines/strategy_selection/expected_value_scoring.py`
- ownership: engine_expectancy_consumption_helper
- action: keep_in_engine_verify_snapshot_contract
- signature: `def _as_string_list(value: Any):`
- reason: existing engine-owned scoring helper, should be validated against locked expectancy snapshot contract

```python
def _as_string_list(value: Any) -> list[str]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [clean for entry in value if (clean := _clean_text(entry))]
    clean = _clean_text(value)
    return [clean] if clean else []
```

### `_ordered`

- source: `src/signalforge/engines/strategy_selection/expected_value_scoring.py`
- ownership: engine_expectancy_consumption_helper
- action: keep_in_engine_verify_snapshot_contract
- signature: `def _ordered(values: set[str]):`
- reason: existing engine-owned scoring helper, should be validated against locked expectancy snapshot contract

```python
def _ordered(values: set[str]) -> list[str]:
    order = {name: index for index, name in enumerate(FAMILY_ORDER)}
    return sorted(values, key=lambda value: (order.get(value, 999), value))
```

### `_candidate_families`

- source: `src/signalforge/engines/strategy_selection/expected_value_scoring.py`
- ownership: engine_expectancy_consumption_helper
- action: keep_in_engine_verify_snapshot_contract
- signature: `def _candidate_families(*, favored: set[str], allowed: set[str], blocked: set[str]):`
- reason: existing engine-owned scoring helper, should be validated against locked expectancy snapshot contract

```python
def _candidate_families(*, favored: set[str], allowed: set[str], blocked: set[str]) -> list[str]:
    candidates = (favored | allowed) - blocked - NON_EV_FAMILIES
    return _ordered(candidates)
```

### `_candidate_handoff_status`

- source: `src/signalforge/engines/strategy_selection/expected_value_scoring.py`
- ownership: engine_expectancy_consumption_helper
- action: keep_in_engine_verify_snapshot_contract
- signature: `def _candidate_handoff_status(*, coverage_status: str, expected_value_state: str):`
- reason: existing engine-owned scoring helper, should be validated against locked expectancy snapshot contract

```python
def _candidate_handoff_status(*, coverage_status: str, expected_value_state: str) -> str:
    if coverage_status == "data_review_required":
        return "data_review_required"
    if coverage_status == "blocked":
        return "blocked_from_candidate_review"
    if expected_value_state in {"positive_expected_value_candidate", "marginal_expected_value_candidate"}:
        return "ready_for_candidate_review" if coverage_status == "ready" else "constrained_for_candidate_review"
    return "not_recommended_for_candidate_review"
```

### `_clean_symbol`

- source: `src/signalforge/engines/strategy_selection/expected_value_scoring.py`
- ownership: engine_expectancy_consumption_helper
- action: keep_in_engine_verify_snapshot_contract
- signature: `def _clean_symbol(value: Any):`
- reason: existing engine-owned scoring helper, should be validated against locked expectancy snapshot contract

```python
def _clean_symbol(value: Any) -> str | None:
    text = _clean_text(value)
    return text.upper() if text else None
```

### `_first_value`

- source: `src/signalforge/engines/strategy_selection/expected_value_scoring.py`
- ownership: engine_expectancy_consumption_helper
- action: keep_in_engine_verify_snapshot_contract
- signature: `def _first_value(item: Mapping[str, Any] | None, keys: Sequence[str]):`
- reason: existing engine-owned scoring helper, should be validated against locked expectancy snapshot contract

```python
def _first_value(item: Mapping[str, Any] | None, keys: Sequence[str]) -> Any:
    if item is None:
        return None
    for key in keys:
        if key in item:
            value = item.get(key)
            if value is not None:
                return value
    return None
```

### `_item_ev_state`

- source: `src/signalforge/engines/strategy_selection/expected_value_scoring.py`
- ownership: engine_expectancy_consumption_helper
- action: keep_in_engine_verify_snapshot_contract
- signature: `def _item_ev_state(*, coverage_status: str, best_candidate: Mapping[str, Any] | None):`
- reason: existing engine-owned scoring helper, should be validated against locked expectancy snapshot contract

```python
def _item_ev_state(*, coverage_status: str, best_candidate: Mapping[str, Any] | None) -> str:
    if coverage_status == "data_review_required":
        return "not_scored_data_review_required"
    if coverage_status == "blocked":
        return "not_scored_blocked"
    if not best_candidate:
        return "not_scored_no_candidate"
    return str(best_candidate.get("expected_value_state") or "unknown")
```

### `_candidate_ev_state`

- source: `src/signalforge/engines/strategy_selection/expected_value_scoring.py`
- ownership: engine_expectancy_consumption_helper
- action: keep_in_engine_verify_snapshot_contract
- signature: `def _candidate_ev_state(score: float):`
- reason: existing engine-owned scoring helper, should be validated against locked expectancy snapshot contract

```python
def _candidate_ev_state(score: float) -> str:
    if score >= 0.68:
        return "positive_expected_value_candidate"
    if score >= 0.52:
        return "marginal_expected_value_candidate"
    if score >= 0.38:
        return "weak_expected_value_candidate"
    return "negative_expected_value_candidate"
```

### `_clamp_score`

- source: `src/signalforge/engines/strategy_selection/expected_value_scoring.py`
- ownership: engine_expectancy_consumption_helper
- action: keep_in_engine_verify_snapshot_contract
- signature: `def _clamp_score(value: float):`
- reason: existing engine-owned scoring helper, should be validated against locked expectancy snapshot contract

```python
def _clamp_score(value: float) -> float:
    return max(0.0, min(1.0, value))
```

### `_constraint_penalty`

- source: `src/signalforge/engines/strategy_selection/expected_value_scoring.py`
- ownership: engine_expectancy_consumption_helper
- action: keep_in_engine_verify_snapshot_contract
- signature: `def _constraint_penalty(constraint_flags: Sequence[str]):`
- reason: existing engine-owned scoring helper, should be validated against locked expectancy snapshot contract

```python
def _constraint_penalty(constraint_flags: Sequence[str]) -> float:
    total = 0.0
    for flag in constraint_flags:
        total += CONSTRAINT_PENALTY_MAP.get(flag, 0.0)
    return min(total, 0.20)
```

### `_premium_alignment_adjustment`

- source: `src/signalforge/engines/strategy_selection/expected_value_scoring.py`
- ownership: engine_expectancy_consumption_helper
- action: keep_in_engine_verify_snapshot_contract
- signature: `def _premium_alignment_adjustment(*, family: str, premium_bias: str):`
- reason: existing engine-owned scoring helper, should be validated against locked expectancy snapshot contract

```python
def _premium_alignment_adjustment(*, family: str, premium_bias: str) -> float:
    if premium_bias == "short_premium_bias":
        if family in SHORT_PREMIUM_FAMILIES:
            return PREMIUM_ALIGNMENT_BONUS
        if family in LONG_PREMIUM_FAMILIES:
            return -PREMIUM_MISMATCH_PENALTY
    if premium_bias == "long_premium_bias":
        if family in LONG_PREMIUM_FAMILIES:
            return PREMIUM_ALIGNMENT_BONUS
        if family in SHORT_PREMIUM_FAMILIES:
            return -PREMIUM_MISMATCH_PENALTY
    return 0.0
```

### `_risk_penalty`

- source: `src/signalforge/engines/strategy_selection/expected_value_scoring.py`
- ownership: engine_expectancy_consumption_helper
- action: keep_in_engine_verify_snapshot_contract
- signature: `def _risk_penalty(risk_flags: Sequence[str]):`
- reason: existing engine-owned scoring helper, should be validated against locked expectancy snapshot contract

```python
def _risk_penalty(risk_flags: Sequence[str]) -> float:
    total = 0.0
    for flag in risk_flags:
        lowered = flag.lower()
        if "gamma" in lowered:
            total += RISK_PENALTY_MAP["gamma_risk_penalty"]
        elif "theta" in lowered:
            total += RISK_PENALTY_MAP["theta_decay_penalty"]
        elif "liquidity" in lowered or "spread" in lowered:
            total += RISK_PENALTY_MAP["liquidity_penalty"]
        elif "macro_regime" in lowered or "regime" in lowered or "weekly_planning" in lowered:
            total += RISK_PENALTY_MAP["regime_penalty"]
        elif "asset" in lowered or "drawdown" in lowered:
            total += RISK_PENALTY_MAP["asset_risk_penalty"]
    return min(total, 0.45)
```

### `_score_family_candidate`

- source: `src/signalforge/engines/strategy_selection/expected_value_scoring.py`
- ownership: engine_expectancy_consumption_helper
- action: keep_in_engine_verify_snapshot_contract
- signature: `def _score_family_candidate(*, family: str, favored: bool, premium_bias: str, handoff: str, risk_flags: Sequence[str], constraint_flags: Sequence[str], discouraged: bool):`
- reason: existing engine-owned scoring helper, should be validated against locked expectancy snapshot contract

```python
def _score_family_candidate(
    *,
    family: str,
    favored: bool,
    premium_bias: str,
    handoff: str,
    risk_flags: Sequence[str],
    constraint_flags: Sequence[str],
    discouraged: bool,
) -> dict[str, Any]:
    base_score = BASE_SCORE_FAVORED if favored else BASE_SCORE_ALLOWED
    premium_adjustment = _premium_alignment_adjustment(family=family, premium_bias=premium_bias)
    risk_penalty = _risk_penalty(risk_flags)
    constraint_penalty = _constraint_penalty(constraint_flags)
    handoff_penalty = CONSTRAINED_REVIEW_PENALTY if handoff == EV_CONSTRAINED_HANDOFF else 0.0
    discouraged_penalty = 0.08 if discouraged else 0.0
    final_score = _clamp_score(base_score + premium_adjustment - risk_penalty - constraint_penalty - handoff_penalty - discouraged_penalty)
    ev_state = _candidate_ev_state(final_score)

    return {
        "strategy_family": family,
        "base_expected_value_score": round(base_score, 4),
        "premium_alignment_adjustment": round(premium_adjustment, 4),
        "risk_penalty": round(risk_penalty, 4),
        "constraint_penalty": round(constraint_penalty, 4),
        "handoff_penalty": round(handoff_penalty, 4),
        "discouraged_penalty": round(discouraged_penalty, 4),
        "risk_adjusted_expected_value_score": round(final_score, 4),
        "expected_value_state": ev_state,
        "manual_review_required": True,
    }
```

### `_build_ev_item`

- source: `src/signalforge/engines/strategy_selection/expected_value_scoring.py`
- ownership: engine_expectancy_consumption_helper
- action: keep_in_engine_verify_snapshot_contract
- signature: `def _build_ev_item(eligibility_item: Mapping[str, Any]):`
- reason: existing engine-owned scoring helper, should be validated against locked expectancy snapshot contract

```python
def _build_ev_item(eligibility_item: Mapping[str, Any]) -> dict[str, Any]:
    symbol = _clean_symbol(_first_value(eligibility_item, ("symbol", "underlying_symbol", "ticker"))) or "UNKNOWN"
    handoff = _clean_text(
        _first_value(
            eligibility_item,
            (
                "expected_value_handoff_status",
                "strategy_family_eligibility_handoff",
                "handoff_status",
                "coverage_status",
            ),
        )
    ) or DATA_REVIEW_HANDOFF

    data_review_reasons = list(_as_string_list(eligibility_item.get("data_review_reasons")))
    hard_block_reasons = list(_as_string_list(eligibility_item.get("hard_block_reasons")))
    risk_flags = list(_as_string_list(eligibility_item.get("risk_flags")))
    constraint_flags = list(_as_string_list(eligibility_item.get("constraint_flags")))
    risk_review_reasons = list(_as_string_list(eligibility_item.get("risk_review_reasons")))

    favored = set(_as_string_list(eligibility_item.get("favored_strategy_families")))
    allowed = set(_as_string_list(eligibility_item.get("allowed_strategy_families")))
    blocked = set(_as_string_list(eligibility_item.get("blocked_strategy_families")))
    discouraged = set(_as_string_list(eligibility_item.get("discouraged_strategy_families")))
    premium_bias = _clean_text(eligibility_item.get("premium_bias")) or "not_provided"

    if eligibility_item.get("data_review_required") is True or handoff == DATA_REVIEW_HANDOFF:
        coverage_status = "data_review_required"
        candidates: list[dict[str, Any]] = []
        best_candidate: dict[str, Any] | None = None
    elif eligibility_item.get("hard_blocked") is True or handoff == BLOCKED_HANDOFF:
        coverage_status = "blocked"
        candidates = []
        best_candidate = None
    else:
        candidate_families = _candidate_families(favored=favored, allowed=allowed, blocked=blocked)
        candidates = [
            _score_family_candidate(
                family=family,
                favored=family in favored,
                premium_bias=premium_bias,
                handoff=handoff,
                risk_flags=risk_flags,
                constraint_flags=constraint_flags,
                discouraged=family in discouraged,
            )
            for family in candidate_families
        ]
        candidates = sorted(
            candidates,
            key=lambda candidate: (
                candidate["risk_adjusted_expected_value_score"],
                -FAMILY_ORDER.index(candidate["strategy_family"]) if candidate["strategy_family"] in FAMILY_ORDER else -999,
            ),
            reverse=True,
        )
        if not candidates:
            coverage_status = "blocked"
            hard_block_reasons.append("no_ev_scoreable_strategy_family")
            best_candidate = None
        else:
            coverage_status = "constrained" if handoff == EV_CONSTRAINED_HANDOFF or risk_flags or constraint_flags else "ready"
            best_candidate = candidates[0]

    expected_value_state = _item_ev_state(coverage_status=coverage_status, best_candidate=best_candidate)
    review_reasons = sorted(set(data_review_reasons + hard_block_reasons + risk_review_reasons + risk_flags + constraint_flags))

    return {
        "artifact_type": "expected_value_scoring_item",
        "symbol": symbol,
        "coverage_status": coverage_status,
        "expected_value_state": expected_value_state,
        "ev_scoreable": coverage_status in {"ready", "constrained"},
        "risk_adjustment_required": coverage_status == "constrained",
        "data_review_required": coverage_status == "data_review_required",
        "hard_blocked": coverage_status == "blocked",
        "expected_value_handoff_status": _candidate_handoff_status(coverage_status=coverage_status, expected_value_state=expected_value_state),
        "macro_regime": eligibility_item.get("macro_regime"),
        "weekly_planning_label": eligibility_item.get("weekly_planning_label"),
        "asset_behavior_state": eligibility_item.get("asset_behavior_state"),
        "options_behavior_state": eligibility_item.get("options_behavior_state"),
        "premium_bias": premium_bias,
        "strategy_environment_bias": eligibility_item.get("strategy_environment_bias"),
        "favored_strategy_families": _ordered(favored),
        "allowed_strategy_families": _ordered(allowed),
        "discouraged_strategy_families": _ordered(discouraged),
        "blocked_strategy_families": _ordered(blocked),
        "candidate_strategy_family_scores": candidates,
        "candidate_count": len(candidates),
        "best_strategy_family": best_candidate.get("strategy_family") if best_candidate else None,
        "best_expected_value_score": best_candidate.get("risk_adjusted_expected_value_score") if best_candidate else None,
        "best_expected_value_state": best_candidate.get("expected_value_state") if best_candidate else None,
        "risk_flags": sorted(set(risk_flags)),
        "constraint_flags": sorted(set(constraint_flags)),
        "data_review_reasons": sorted(set(data_review_reasons)),
        "hard_block_reasons": sorted(set(hard_block_reasons)),
        "needs_review_reasons": review_reasons,
        "manual_review_required": True,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }
```

### `_looks_like_items`

- source: `src/signalforge/engines/strategy_selection/expected_value_scoring.py`
- ownership: engine_expectancy_consumption_helper
- action: keep_in_engine_verify_snapshot_contract
- signature: `def _looks_like_items(value: Any):`
- reason: existing engine-owned scoring helper, should be validated against locked expectancy snapshot contract

```python
def _looks_like_items(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))
```

### `_extract_items`

- source: `src/signalforge/engines/strategy_selection/expected_value_scoring.py`
- ownership: engine_expectancy_consumption_helper
- action: keep_in_engine_verify_snapshot_contract
- signature: `def _extract_items(source: Mapping[str, Any] | Sequence[Any] | None, keys: Sequence[str]):`
- reason: existing engine-owned scoring helper, should be validated against locked expectancy snapshot contract

```python
def _extract_items(source: Mapping[str, Any] | Sequence[Any] | None, keys: Sequence[str]) -> list[Any]:
    if source is None:
        return []
    if isinstance(source, Sequence) and not isinstance(source, (str, bytes, bytearray)):
        return list(source)
    if not isinstance(source, Mapping):
        return []
    for key in keys:
        value = source.get(key)
        if _looks_like_items(value):
            return list(value)
    for parent_key in ("result", "payload", "data", "import_result"):
        parent = source.get(parent_key)
        if isinstance(parent, Mapping):
            for key in keys:
                value = parent.get(key)
                if _looks_like_items(value):
                    return list(value)
    return []
```

### `_source_artifact_type`

- source: `src/signalforge/engines/strategy_selection/expected_value_scoring.py`
- ownership: engine_expectancy_consumption_helper
- action: keep_in_engine_verify_snapshot_contract
- signature: `def _source_artifact_type(source: Any):`
- reason: existing engine-owned scoring helper, should be validated against locked expectancy snapshot contract

```python
def _source_artifact_type(source: Any) -> str:
    if isinstance(source, Mapping):
        return _clean_text(source.get("artifact_type")) or "mapping"
    if isinstance(source, Sequence) and not isinstance(source, (str, bytes, bytearray)):
        return "sequence"
    if source is None:
        return "missing"
    return type(source).__name__
```

### `_summary`

- source: `src/signalforge/engines/strategy_selection/expected_value_scoring.py`
- ownership: engine_expectancy_consumption_helper
- action: keep_in_engine_verify_snapshot_contract
- signature: `def _summary(items: Sequence[Mapping[str, Any]]):`
- reason: existing engine-owned scoring helper, should be validated against locked expectancy snapshot contract

```python
def _summary(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    coverage_counts = Counter(str(item.get("coverage_status") or "unknown") for item in items)
    ev_state_counts = Counter(str(item.get("expected_value_state") or "unknown") for item in items)
    best_family_counts = Counter(str(item.get("best_strategy_family")) for item in items if item.get("best_strategy_family"))
    handoff_counts = Counter(str(item.get("expected_value_handoff_status") or "unknown") for item in items)
    risk_flag_counts = Counter(flag for item in items for flag in item.get("risk_flags", []))
    constraint_counts = Counter(flag for item in items for flag in item.get("constraint_flags", []))
    data_reason_counts = Counter(reason for item in items for reason in item.get("data_review_reasons", []))
    candidate_state_counts = Counter(
        candidate.get("expected_value_state")
        for item in items
        for candidate in item.get("candidate_strategy_family_scores", [])
    )
    candidate_family_counts = Counter(
        candidate.get("strategy_family")
        for item in items
        for candidate in item.get("candidate_strategy_family_scores", [])
    )
    scored_candidate_count = sum(int(item.get("candidate_count") or 0) for item in items)
    ev_scoreable_count = sum(1 for item in items if item.get("ev_scoreable") is True)
    risk_adjusted_count = sum(1 for item in items if item.get("risk_adjustment_required") is True)
    positive_or_marginal_symbol_count = sum(
        1
        for item in items
        if item.get("expected_value_state") in {"positive_expected_value_candidate", "marginal_expected_value_candidate"}
    )

    return {
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "symbol_count": len(items),
        "ready_symbol_count": coverage_counts.get("ready", 0),
        "constrained_symbol_count": coverage_counts.get("constrained", 0),
        "ev_scoreable_symbol_count": ev_scoreable_count,
        "risk_adjusted_ev_symbol_count": risk_adjusted_count,
        "data_review_symbol_count": coverage_counts.get("data_review_required", 0),
        "blocked_symbol_count": coverage_counts.get("blocked", 0),
        "needs_review_symbol_count": coverage_counts.get("data_review_required", 0) + coverage_counts.get("blocked", 0),
        "manual_review_symbol_count": sum(1 for item in items if item.get("manual_review_required") is True),
        "positive_or_marginal_symbol_count": positive_or_marginal_symbol_count,
        "scored_candidate_count": scored_candidate_count,
        "coverage_status_counts": dict(sorted(coverage_counts.items())),
        "expected_value_state_counts": dict(sorted(ev_state_counts.items())),
        "best_strategy_family_counts": dict(sorted(best_family_counts.items())),
        "candidate_expected_value_state_counts": dict(sorted(candidate_state_counts.items())),
        "candidate_strategy_family_counts": dict(sorted(candidate_family_counts.items())),
        "handoff_counts": dict(sorted(handoff_counts.items())),
        "risk_flag_counts": dict(sorted(risk_flag_counts.items())),
        "constraint_flag_counts": dict(sorted(constraint_counts.items())),
        "data_review_reason_counts": dict(sorted(data_reason_counts.items())),
    }
```

### `build_signalforge_expected_value_scoring`

- source: `src/signalforge/engines/strategy_selection/expected_value_scoring.py`
- ownership: engine_expectancy_consumption_entrypoint
- action: keep_in_engine_as_paper_consumption_candidate
- signature: `def build_signalforge_expected_value_scoring(eligibility_source: Mapping[str, Any] | Sequence[Any] | None):`
- reason: current engine entrypoint for consuming expectancy-like strategy selection inputs

```python
def build_signalforge_expected_value_scoring(
    eligibility_source: Mapping[str, Any] | Sequence[Any] | None,
) -> dict[str, Any]:
    """Score EV-eligible strategy families without selecting trades or orders.

    This artifact consumes the refined strategy-family eligibility handoff. It scores
    ready and constrained candidates, carries risk/constraint flags into penalties,
    and keeps data-review or blocked symbols out of the EV scoring pool. It does not
    pick contracts, submit orders, call brokers, model fills, model slippage, or make
    automatic strategy changes.
    """

    eligibility_items = _extract_items(eligibility_source, ELIGIBILITY_ITEM_KEYS)
    source_artifacts = {"eligibility_source": _source_artifact_type(eligibility_source)}

    blocked_reasons: list[str] = []
    if not eligibility_items:
        blocked_reasons.append("missing_strategy_family_eligibility_items")

    if blocked_reasons:
        return _blocked_result(blocked_reasons, source_artifacts=source_artifacts)

    items = [_build_ev_item(item) for item in eligibility_items if isinstance(item, Mapping)]
    summary = _summary(items)
    status = "ready" if summary["data_review_symbol_count"] == 0 and summary["blocked_symbol_count"] == 0 else "needs_review"

    return {
        "artifact_type": "signalforge_expected_value_scoring",
        "schema_version": EXPECTED_VALUE_SCORING_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "contract": "expected_value_scoring",
        "adapter_type": "expected_value_scoring_builder",
        "review_scope": "risk_adjusted_expected_value_scoring_not_trade_selection_or_execution",
        "source_artifacts": source_artifacts,
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "next_build_recommendations": [
            {
                "capability": "candidate_selection_review",
                "priority": "high",
                "recommendation": "Use risk-adjusted EV scores to rank candidate strategy families, then require final review before any contract selection or execution workflow.",
            }
        ],
        "expected_value_items": items,
        "ev_items": items,
        "expected_value_summary": summary,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }
```


## Warnings

- stage37e_is_read_only_no_logic_moved
- do_not_recompute_walk_forward_expectancy_inside_paper_engine
- next_stage_should_define_locked_expectancy_snapshot_contract_for_paper_consumption