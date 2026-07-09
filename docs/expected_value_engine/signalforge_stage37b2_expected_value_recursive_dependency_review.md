# Stage 37B2 Expected-Value Recursive Dependency Review

- is_ready: True
- blocker_count: 0
- closure_group_count: 2
- reviewed_symbol_count: 25
- opportunity_score_closure_count: 24
- risk_reward_closure_count: 1
- strategy_selection_root_count: 2
- walk_forward_owner: `src/signalforge/backtesting/walk_forward_expectancy_builder.py`
- paper_order_created: False
- live_order_created: False
- live_trade_supported: False

## Closure Groups

| source | roots | closure count | closure |
|---|---|---:|---|
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py` | score_vega, rank_opportunities, passes_minimum_thresholds, filter_opportunities | 24 | normalize, inverse_normalize, score_vega, OpportunityMetrics, ComponentScores, ScoringWeights, OpportunityScoreResult, score_delta, score_expected_return, score_gamma, score_implied_volatility, score_liquidity, score_probability_of_profit, score_reward_risk, score_risk, score_theta, component_scores, validate_weights, total_weight, weighted_score, score_opportunity, rank_opportunities, passes_minimum_thresholds, filter_opportunities |
| `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/risk_reward.py` | profit_factor | 1 | profit_factor |

## Symbol Dependency Review

| symbol | kind | root | target | internal funcs | internal classes | imports | module bindings | unresolved |
|---|---|---:|---|---|---|---|---|---|
| `normalize` | function | False | `src/signalforge/engines/expected_value/opportunity_score.py` |  |  |  |  |  |
| `inverse_normalize` | function | False | `src/signalforge/engines/expected_value/opportunity_score.py` | normalize |  |  |  |  |
| `score_vega` | function | True | `src/signalforge/engines/expected_value/opportunity_score.py` | inverse_normalize |  |  |  |  |
| `OpportunityMetrics` | class | False | `src/signalforge/engines/expected_value/opportunity_score.py` |  |  | dataclass |  |  |
| `ComponentScores` | class | False | `src/signalforge/engines/expected_value/opportunity_score.py` |  |  | dataclass |  |  |
| `ScoringWeights` | class | False | `src/signalforge/engines/expected_value/opportunity_score.py` |  |  | dataclass |  |  |
| `OpportunityScoreResult` | class | False | `src/signalforge/engines/expected_value/opportunity_score.py` |  | ComponentScores, OpportunityMetrics, ScoringWeights | dataclass |  |  |
| `score_delta` | function | False | `src/signalforge/engines/expected_value/opportunity_score.py` | inverse_normalize |  |  |  |  |
| `score_expected_return` | function | False | `src/signalforge/engines/expected_value/opportunity_score.py` | normalize |  |  |  |  |
| `score_gamma` | function | False | `src/signalforge/engines/expected_value/opportunity_score.py` | inverse_normalize |  |  |  |  |
| `score_implied_volatility` | function | False | `src/signalforge/engines/expected_value/opportunity_score.py` | inverse_normalize |  |  |  |  |
| `score_liquidity` | function | False | `src/signalforge/engines/expected_value/opportunity_score.py` | normalize |  |  |  |  |
| `score_probability_of_profit` | function | False | `src/signalforge/engines/expected_value/opportunity_score.py` | normalize |  |  |  |  |
| `score_reward_risk` | function | False | `src/signalforge/engines/expected_value/opportunity_score.py` | normalize |  |  |  |  |
| `score_risk` | function | False | `src/signalforge/engines/expected_value/opportunity_score.py` | inverse_normalize |  |  |  |  |
| `score_theta` | function | False | `src/signalforge/engines/expected_value/opportunity_score.py` | normalize |  |  |  |  |
| `component_scores` | function | False | `src/signalforge/engines/expected_value/opportunity_score.py` | score_delta, score_expected_return, score_gamma, score_implied_volatility, score_liquidity, score_probability_of_profit, score_reward_risk, score_risk, score_theta, score_vega | ComponentScores, OpportunityMetrics |  |  |  |
| `validate_weights` | function | False | `src/signalforge/engines/expected_value/opportunity_score.py` |  | ScoringWeights |  |  |  |
| `total_weight` | function | False | `src/signalforge/engines/expected_value/opportunity_score.py` | validate_weights | ScoringWeights |  |  |  |
| `weighted_score` | function | False | `src/signalforge/engines/expected_value/opportunity_score.py` | total_weight | ComponentScores, ScoringWeights |  |  |  |
| `score_opportunity` | function | False | `src/signalforge/engines/expected_value/opportunity_score.py` | component_scores, weighted_score | OpportunityMetrics, OpportunityScoreResult, ScoringWeights |  |  |  |
| `rank_opportunities` | function | True | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` | score_opportunity | OpportunityMetrics, OpportunityScoreResult, ScoringWeights |  |  |  |
| `passes_minimum_thresholds` | function | True | `src/signalforge/engines/strategy_selection/expected_value_scoring.py` |  | OpportunityMetrics |  |  |  |
| `filter_opportunities` | function | True | `src/signalforge/engines/expected_value/opportunity_score.py` | passes_minimum_thresholds | OpportunityMetrics |  |  |  |
| `profit_factor` | function | True | `src/signalforge/engines/expected_value/risk_reward.py` |  |  |  |  |  |

## Source Slices

### `normalize`

- source: `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py`
- kind: function
- target: `src/signalforge/engines/expected_value/opportunity_score.py`
- signature: `def normalize(value: float, min_value: float, max_value: float):`
- reason: shared opportunity scoring dependency

```python
def normalize(
    value: float,
    min_value: float,
    max_value: float,
) -> float:
    """
    Normalize value to 0-1 range.
    """
    if max_value <= min_value:
        return 0.0

    return max(0.0, min(1.0, (value - min_value) / (max_value - min_value)))
```

### `inverse_normalize`

- source: `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py`
- kind: function
- target: `src/signalforge/engines/expected_value/opportunity_score.py`
- signature: `def inverse_normalize(value: float, min_value: float, max_value: float):`
- reason: shared opportunity scoring dependency

```python
def inverse_normalize(
    value: float,
    min_value: float,
    max_value: float,
) -> float:
    """
    Normalize value where lower is better.
    """
    return 1.0 - normalize(
        value=value,
        min_value=min_value,
        max_value=max_value,
    )
```

### `score_vega`

- source: `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py`
- kind: function
- target: `src/signalforge/engines/expected_value/opportunity_score.py`
- signature: `def score_vega(vega: float | None, max_abs_vega: float=1.0):`
- reason: shared opportunity scoring dependency

```python
def score_vega(
    vega: float | None,
    max_abs_vega: float = 1.0,
) -> float:
    """
    Score vega exposure.

    Lower absolute vega receives a higher score by default because high
    volatility sensitivity can make EV less stable.
    """
    if vega is None:
        return 0.50

    return inverse_normalize(
        value=abs(vega),
        min_value=0.0,
        max_value=max_abs_vega,
    )
```

### `OpportunityMetrics`

- source: `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py`
- kind: class
- target: `src/signalforge/engines/expected_value/opportunity_score.py`
- signature: `class OpportunityMetrics`
- reason: shared opportunity scoring dependency

```python
class OpportunityMetrics:
    expected_return: float
    probability_of_profit: float
    reward_risk: float
    implied_volatility: float
    liquidity_score: float
    annualized_return: float | None = None
    risk_score: float | None = None
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    name: str | None = None
```

### `ComponentScores`

- source: `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py`
- kind: class
- target: `src/signalforge/engines/expected_value/opportunity_score.py`
- signature: `class ComponentScores`
- reason: shared opportunity scoring dependency

```python
class ComponentScores:
    expected_return_score: float
    probability_score: float
    reward_risk_score: float
    liquidity_score: float
    implied_volatility_score: float
    annualized_return_score: float
    risk_score: float
    delta_score: float
    gamma_score: float
    theta_score: float
    vega_score: float
```

### `ScoringWeights`

- source: `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py`
- kind: class
- target: `src/signalforge/engines/expected_value/opportunity_score.py`
- signature: `class ScoringWeights`
- reason: shared opportunity scoring dependency

```python
class ScoringWeights:
    expected_return_weight: float = 0.30
    probability_weight: float = 0.20
    reward_risk_weight: float = 0.15
    liquidity_weight: float = 0.10
    iv_weight: float = 0.10
    annualized_return_weight: float = 0.00
    risk_score_weight: float = 0.00
    delta_weight: float = 0.05
    gamma_weight: float = 0.03
    theta_weight: float = 0.04
    vega_weight: float = 0.03
```

### `OpportunityScoreResult`

- source: `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py`
- kind: class
- target: `src/signalforge/engines/expected_value/opportunity_score.py`
- signature: `class OpportunityScoreResult`
- reason: shared opportunity scoring dependency

```python
class OpportunityScoreResult:
    score: float
    metrics: OpportunityMetrics
    components: ComponentScores
    weights: ScoringWeights
```

### `score_delta`

- source: `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py`
- kind: function
- target: `src/signalforge/engines/expected_value/opportunity_score.py`
- signature: `def score_delta(delta: float | None, target_abs_delta: float=0.5, max_distance: float=0.5):`
- reason: shared opportunity scoring dependency

```python
def score_delta(
    delta: float | None,
    target_abs_delta: float = 0.50,
    max_distance: float = 0.50,
) -> float:
    """
    Score delta exposure.

    Higher score means the absolute delta is closer to the target.
    Default target is 0.50, useful for balanced directional option exposure.
    """
    if delta is None:
        return 0.50

    distance = abs(abs(delta) - target_abs_delta)

    return inverse_normalize(
        value=distance,
        min_value=0.0,
        max_value=max_distance,
    )
```

### `score_expected_return`

- source: `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py`
- kind: function
- target: `src/signalforge/engines/expected_value/opportunity_score.py`
- signature: `def score_expected_return(expected_return: float, min_return: float=-0.5, max_return: float=0.5):`
- reason: shared opportunity scoring dependency

```python
def score_expected_return(
    expected_return: float,
    min_return: float = -0.50,
    max_return: float = 0.50,
) -> float:
    return normalize(
        value=expected_return,
        min_value=min_return,
        max_value=max_return,
    )
```

### `score_gamma`

- source: `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py`
- kind: function
- target: `src/signalforge/engines/expected_value/opportunity_score.py`
- signature: `def score_gamma(gamma: float | None, max_abs_gamma: float=0.1):`
- reason: shared opportunity scoring dependency

```python
def score_gamma(
    gamma: float | None,
    max_abs_gamma: float = 0.10,
) -> float:
    """
    Score gamma exposure.

    Lower absolute gamma receives a higher score because extreme gamma
    can create unstable PnL and sizing behavior.
    """
    if gamma is None:
        return 0.50

    return inverse_normalize(
        value=abs(gamma),
        min_value=0.0,
        max_value=max_abs_gamma,
    )
```

### `score_implied_volatility`

- source: `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py`
- kind: function
- target: `src/signalforge/engines/expected_value/opportunity_score.py`
- signature: `def score_implied_volatility(implied_volatility: float, min_iv: float=0.0, max_iv: float=1.0):`
- reason: shared opportunity scoring dependency

```python
def score_implied_volatility(
    implied_volatility: float,
    min_iv: float = 0.0,
    max_iv: float = 1.0,
) -> float:
    """
    Lower implied volatility receives a higher score.
    """
    return inverse_normalize(
        value=implied_volatility,
        min_value=min_iv,
        max_value=max_iv,
    )
```

### `score_liquidity`

- source: `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py`
- kind: function
- target: `src/signalforge/engines/expected_value/opportunity_score.py`
- signature: `def score_liquidity(liquidity_score: float):`
- reason: shared opportunity scoring dependency

```python
def score_liquidity(
    liquidity_score: float,
) -> float:
    return normalize(
        value=liquidity_score,
        min_value=0.0,
        max_value=1.0,
    )
```

### `score_probability_of_profit`

- source: `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py`
- kind: function
- target: `src/signalforge/engines/expected_value/opportunity_score.py`
- signature: `def score_probability_of_profit(probability_of_profit: float):`
- reason: shared opportunity scoring dependency

```python
def score_probability_of_profit(
    probability_of_profit: float,
) -> float:
    return normalize(
        value=probability_of_profit,
        min_value=0.0,
        max_value=1.0,
    )
```

### `score_reward_risk`

- source: `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py`
- kind: function
- target: `src/signalforge/engines/expected_value/opportunity_score.py`
- signature: `def score_reward_risk(reward_risk: float, max_reward_risk: float=10.0):`
- reason: shared opportunity scoring dependency

```python
def score_reward_risk(
    reward_risk: float,
    max_reward_risk: float = 10.0,
) -> float:
    return normalize(
        value=reward_risk,
        min_value=0.0,
        max_value=max_reward_risk,
    )
```

### `score_risk`

- source: `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py`
- kind: function
- target: `src/signalforge/engines/expected_value/opportunity_score.py`
- signature: `def score_risk(risk_score: float | None):`
- reason: shared opportunity scoring dependency

```python
def score_risk(
    risk_score: float | None,
) -> float:
    """
    Lower risk receives a higher score.

    Missing risk_score is treated neutrally.
    """
    if risk_score is None:
        return 0.50

    return inverse_normalize(
        value=risk_score,
        min_value=0.0,
        max_value=1.0,
    )
```

### `score_theta`

- source: `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py`
- kind: function
- target: `src/signalforge/engines/expected_value/opportunity_score.py`
- signature: `def score_theta(theta: float | None, min_theta: float=-1.0, max_theta: float=1.0):`
- reason: shared opportunity scoring dependency

```python
def score_theta(
    theta: float | None,
    min_theta: float = -1.0,
    max_theta: float = 1.0,
) -> float:
    """
    Score theta exposure.

    Higher theta is better. Positive theta strategies benefit from time decay.
    """
    if theta is None:
        return 0.50

    return normalize(
        value=theta,
        min_value=min_theta,
        max_value=max_theta,
    )
```

### `component_scores`

- source: `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py`
- kind: function
- target: `src/signalforge/engines/expected_value/opportunity_score.py`
- signature: `def component_scores(metrics: OpportunityMetrics):`
- reason: shared opportunity scoring dependency

```python
def component_scores(
    metrics: OpportunityMetrics,
) -> ComponentScores:
    """
    Calculate normalized component scores.
    """
    annualized_value = (
        metrics.annualized_return
        if metrics.annualized_return is not None
        else metrics.expected_return
    )

    return ComponentScores(
        expected_return_score=score_expected_return(metrics.expected_return),
        probability_score=score_probability_of_profit(metrics.probability_of_profit),
        reward_risk_score=score_reward_risk(metrics.reward_risk),
        liquidity_score=score_liquidity(metrics.liquidity_score),
        implied_volatility_score=score_implied_volatility(metrics.implied_volatility),
        annualized_return_score=score_expected_return(annualized_value),
        risk_score=score_risk(metrics.risk_score),
        delta_score=score_delta(metrics.delta),
        gamma_score=score_gamma(metrics.gamma),
        theta_score=score_theta(metrics.theta),
        vega_score=score_vega(metrics.vega),
    )
```

### `validate_weights`

- source: `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py`
- kind: function
- target: `src/signalforge/engines/expected_value/opportunity_score.py`
- signature: `def validate_weights(weights: ScoringWeights):`
- reason: shared opportunity scoring dependency

```python
def validate_weights(weights: ScoringWeights) -> None:
    """
    Validate all weights are non-negative.
    """
    values = [
        weights.expected_return_weight,
        weights.probability_weight,
        weights.reward_risk_weight,
        weights.liquidity_weight,
        weights.iv_weight,
        weights.annualized_return_weight,
        weights.risk_score_weight,
        weights.delta_weight,
        weights.gamma_weight,
        weights.theta_weight,
        weights.vega_weight,
    ]

    if any(value < 0 for value in values):
        raise ValueError("Scoring weights cannot be negative.")
```

### `total_weight`

- source: `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py`
- kind: function
- target: `src/signalforge/engines/expected_value/opportunity_score.py`
- signature: `def total_weight(weights: ScoringWeights):`
- reason: shared opportunity scoring dependency

```python
def total_weight(weights: ScoringWeights) -> float:
    """
    Sum active scoring weights.
    """
    validate_weights(weights)

    return (
        weights.expected_return_weight
        + weights.probability_weight
        + weights.reward_risk_weight
        + weights.liquidity_weight
        + weights.iv_weight
        + weights.annualized_return_weight
        + weights.risk_score_weight
        + weights.delta_weight
        + weights.gamma_weight
        + weights.theta_weight
        + weights.vega_weight
    )
```

### `weighted_score`

- source: `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py`
- kind: function
- target: `src/signalforge/engines/expected_value/opportunity_score.py`
- signature: `def weighted_score(components: ComponentScores, weights: ScoringWeights):`
- reason: shared opportunity scoring dependency

```python
def weighted_score(
    components: ComponentScores,
    weights: ScoringWeights,
) -> float:
    """
    Combine component scores into one weighted score.
    """
    weight_sum = total_weight(weights)

    if weight_sum <= 0:
        return 0.0

    raw_score = (
        components.expected_return_score * weights.expected_return_weight
        + components.probability_score * weights.probability_weight
        + components.reward_risk_score * weights.reward_risk_weight
        + components.liquidity_score * weights.liquidity_weight
        + components.implied_volatility_score * weights.iv_weight
        + components.annualized_return_score * weights.annualized_return_weight
        + components.risk_score * weights.risk_score_weight
        + components.delta_score * weights.delta_weight
        + components.gamma_score * weights.gamma_weight
        + components.theta_score * weights.theta_weight
        + components.vega_score * weights.vega_weight
    )

    return raw_score / weight_sum
```

### `score_opportunity`

- source: `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py`
- kind: function
- target: `src/signalforge/engines/expected_value/opportunity_score.py`
- signature: `def score_opportunity(metrics: OpportunityMetrics, weights: ScoringWeights | None=None):`
- reason: shared opportunity scoring dependency

```python
def score_opportunity(
    metrics: OpportunityMetrics,
    weights: ScoringWeights | None = None,
) -> OpportunityScoreResult:
    """
    Full opportunity score result with component breakdown.
    """
    active_weights = weights or ScoringWeights()
    components = component_scores(metrics)

    score = weighted_score(
        components=components,
        weights=active_weights,
    )

    return OpportunityScoreResult(
        score=round(score, 4),
        metrics=metrics,
        components=components,
        weights=active_weights,
    )
```

### `rank_opportunities`

- source: `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py`
- kind: function
- target: `src/signalforge/engines/strategy_selection/expected_value_scoring.py`
- signature: `def rank_opportunities(opportunities: list[OpportunityMetrics], weights: ScoringWeights | None=None, descending: bool=True):`
- reason: post-expectancy opportunity ranking/filter helper

```python
def rank_opportunities(
    opportunities: list[OpportunityMetrics],
    weights: ScoringWeights | None = None,
    descending: bool = True,
) -> list[OpportunityScoreResult]:
    """
    Rank opportunities by composite opportunity score.
    """
    results = [
        score_opportunity(
            metrics=metrics,
            weights=weights,
        )
        for metrics in opportunities
    ]

    return sorted(
        results,
        key=lambda result: result.score,
        reverse=descending,
    )
```

### `passes_minimum_thresholds`

- source: `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py`
- kind: function
- target: `src/signalforge/engines/strategy_selection/expected_value_scoring.py`
- signature: `def passes_minimum_thresholds(metrics: OpportunityMetrics, min_expected_return: float=0.0, min_probability_of_profit: float=0.5, min_reward_risk: float=1.0, min_liquidity_score: float=0.5, max_implied_volatility: float=1.0, max_abs_delta: float | None=None, max_abs_gamma: float | None=None, min_theta: float | None=None, max_abs_vega: float | None=None):`
- reason: post-expectancy opportunity ranking/filter helper

```python
def passes_minimum_thresholds(
    metrics: OpportunityMetrics,
    min_expected_return: float = 0.0,
    min_probability_of_profit: float = 0.50,
    min_reward_risk: float = 1.0,
    min_liquidity_score: float = 0.50,
    max_implied_volatility: float = 1.0,
    max_abs_delta: float | None = None,
    max_abs_gamma: float | None = None,
    min_theta: float | None = None,
    max_abs_vega: float | None = None,
) -> bool:
    """
    Basic gate before ranking an opportunity.

    Greek thresholds are optional. They are only applied when provided.
    """
    if metrics.expected_return < min_expected_return:
        return False

    if metrics.probability_of_profit < min_probability_of_profit:
        return False

    if metrics.reward_risk < min_reward_risk:
        return False

    if metrics.liquidity_score < min_liquidity_score:
        return False

    if metrics.implied_volatility > max_implied_volatility:
        return False

    if max_abs_delta is not None and metrics.delta is not None:
        if abs(metrics.delta) > max_abs_delta:
            return False

    if max_abs_gamma is not None and metrics.gamma is not None:
        if abs(metrics.gamma) > max_abs_gamma:
            return False

    if min_theta is not None and metrics.theta is not None:
        if metrics.theta < min_theta:
            return False

    if max_abs_vega is not None and metrics.vega is not None:
        if abs(metrics.vega) > max_abs_vega:
            return False

    return True
```

### `filter_opportunities`

- source: `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py`
- kind: function
- target: `src/signalforge/engines/expected_value/opportunity_score.py`
- signature: `def filter_opportunities(opportunities: list[OpportunityMetrics], min_expected_return: float=0.0, min_probability_of_profit: float=0.5, min_reward_risk: float=1.0, min_liquidity_score: float=0.5, max_implied_volatility: float=1.0, max_abs_delta: float | None=None, max_abs_gamma: float | None=None, min_theta: float | None=None, max_abs_vega: float | None=None):`
- reason: shared opportunity scoring dependency

```python
def filter_opportunities(
    opportunities: list[OpportunityMetrics],
    min_expected_return: float = 0.0,
    min_probability_of_profit: float = 0.50,
    min_reward_risk: float = 1.0,
    min_liquidity_score: float = 0.50,
    max_implied_volatility: float = 1.0,
    max_abs_delta: float | None = None,
    max_abs_gamma: float | None = None,
    min_theta: float | None = None,
    max_abs_vega: float | None = None,
) -> list[OpportunityMetrics]:
    """
    Filter opportunities using minimum quality thresholds.
    """
    return [
        metrics
        for metrics in opportunities
        if passes_minimum_thresholds(
            metrics=metrics,
            min_expected_return=min_expected_return,
            min_probability_of_profit=min_probability_of_profit,
            min_reward_risk=min_reward_risk,
            min_liquidity_score=min_liquidity_score,
            max_implied_volatility=max_implied_volatility,
            max_abs_delta=max_abs_delta,
            max_abs_gamma=max_abs_gamma,
            min_theta=min_theta,
            max_abs_vega=max_abs_vega,
        )
    ]
```

### `profit_factor`

- source: `src/paper_live_engine/legacy_domain/old_repo/src/expected_value/risk_reward.py`
- kind: function
- target: `src/signalforge/engines/expected_value/risk_reward.py`
- signature: `def profit_factor(gross_profit: float, gross_loss: float):`
- reason: risk/reward metric helper

```python
def profit_factor(
    gross_profit: float,
    gross_loss: float,
) -> float:
    """
    Gross profit divided by gross loss.
    """
    loss = abs(gross_loss)

    if loss == 0:
        return float("inf") if gross_profit > 0 else 0.0

    return gross_profit / loss
```


## Warnings

- stage37b2_is_read_only_no_logic_moved
- walk_forward_expectancy_builder_remains_backtesting_owned
- next_stage_should_extract_verified_dependency_clusters_with_parity_tests