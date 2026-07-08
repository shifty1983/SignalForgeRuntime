"""
Optimizer portfolio constraints.

This module enforces hard portfolio rules. Unlike objective.py, which scores
preferences, this module answers whether a candidate or portfolio is allowed.

Primary constraint groups:
- position count
- position sizing
- ticker / sector / strategy concentration
- capital at risk
- liquidity
- portfolio-level Greeks
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class GreekLimits:
    """
    Hard portfolio-level Greek exposure limits.
    """

    max_abs_delta: float | None = 2.00
    max_abs_gamma: float | None = 1.00
    max_abs_theta: float | None = 5.00
    max_abs_vega: float | None = 5.00


@dataclass(frozen=True)
class LiquidityLimits:
    """
    Hard candidate-level liquidity requirements.
    """

    min_liquidity_score: float | None = 0.25
    max_bid_ask_spread_pct: float | None = 0.15
    min_volume: float | None = None
    min_open_interest: float | None = None


@dataclass(frozen=True)
class PortfolioConstraints:
    """
    Full hard-constraint configuration for optimizer selection.
    """

    max_positions: int | None = 10

    min_position_weight: float | None = 0.00
    max_position_weight: float | None = 0.25

    max_symbol_weight: float | None = 0.30
    max_sector_weight: float | None = 0.40
    max_strategy_weight: float | None = 0.50

    max_total_weight: float | None = 1.00
    min_total_weight: float | None = 0.00

    max_total_capital_at_risk: float | None = 1.00

    greek_limits: GreekLimits = field(default_factory=GreekLimits)
    liquidity_limits: LiquidityLimits = field(default_factory=LiquidityLimits)

    allowed_symbols: tuple[str, ...] | None = None
    blocked_symbols: tuple[str, ...] = field(default_factory=tuple)

    allowed_strategy_types: tuple[str, ...] | None = None
    blocked_strategy_types: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ConstraintViolation:
    """
    A single failed constraint.
    """

    constraint: str
    message: str
    value: float | int | str | None = None
    limit: float | int | str | None = None


@dataclass(frozen=True)
class ConstraintCheckResult:
    """
    Result of checking a candidate or portfolio against constraints.
    """

    passed: bool
    violations: tuple[ConstraintViolation, ...]

    def messages(self) -> list[str]:
        return [violation.message for violation in self.violations]


class PortfolioConstraintChecker:
    """
    Enforces hard optimizer constraints.
    """

    def __init__(self, constraints: PortfolioConstraints | None = None) -> None:
        self.constraints = constraints or PortfolioConstraints()

    def check_candidate(self, candidate: Mapping[str, Any]) -> ConstraintCheckResult:
        violations: list[ConstraintViolation] = []

        self._check_symbol(candidate, violations)
        self._check_strategy_type(candidate, violations)
        self._check_candidate_weight(candidate, violations)
        self._check_candidate_liquidity(candidate, violations)

        return ConstraintCheckResult(
            passed=not violations,
            violations=tuple(violations),
        )

    def check_portfolio(
        self,
        positions: Iterable[Mapping[str, Any]],
    ) -> ConstraintCheckResult:
        positions_list = list(positions)
        violations: list[ConstraintViolation] = []

        for position in positions_list:
            candidate_result = self.check_candidate(position)
            violations.extend(candidate_result.violations)

        self._check_position_count(positions_list, violations)
        self._check_total_weight(positions_list, violations)
        self._check_total_capital_at_risk(positions_list, violations)
        self._check_group_concentration(
            positions=positions_list,
            field_names=("symbol", "ticker", "underlying"),
            constraint_name="max_symbol_weight",
            limit=self.constraints.max_symbol_weight,
            violations=violations,
        )
        self._check_group_concentration(
            positions=positions_list,
            field_names=("sector", "sector_name"),
            constraint_name="max_sector_weight",
            limit=self.constraints.max_sector_weight,
            violations=violations,
        )
        self._check_group_concentration(
            positions=positions_list,
            field_names=("strategy_type", "strategy", "structure"),
            constraint_name="max_strategy_weight",
            limit=self.constraints.max_strategy_weight,
            violations=violations,
        )
        self._check_portfolio_greeks(positions_list, violations)

        return ConstraintCheckResult(
            passed=not violations,
            violations=tuple(violations),
        )

    def filter_candidates(
        self,
        candidates: Iterable[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Return only candidates that pass candidate-level constraints.
        """

        passed: list[dict[str, Any]] = []

        for candidate in candidates:
            result = self.check_candidate(candidate)
            if result.passed:
                passed.append(dict(candidate))

        return passed

    def passes_candidate(self, candidate: Mapping[str, Any]) -> bool:
        return self.check_candidate(candidate).passed

    def passes_portfolio(self, positions: Iterable[Mapping[str, Any]]) -> bool:
        return self.check_portfolio(positions).passed

    def _check_symbol(
        self,
        candidate: Mapping[str, Any],
        violations: list[ConstraintViolation],
    ) -> None:
        symbol = _first_string(candidate, ("symbol", "ticker", "underlying"))

        if symbol is None:
            return

        normalized_symbol = symbol.upper()

        if self.constraints.allowed_symbols is not None:
            allowed = {item.upper() for item in self.constraints.allowed_symbols}
            if normalized_symbol not in allowed:
                violations.append(
                    ConstraintViolation(
                        constraint="allowed_symbols",
                        message=f"{symbol} is not in the allowed symbol list.",
                        value=symbol,
                        limit="allowed_symbols",
                    )
                )

        blocked = {item.upper() for item in self.constraints.blocked_symbols}
        if normalized_symbol in blocked:
            violations.append(
                ConstraintViolation(
                    constraint="blocked_symbols",
                    message=f"{symbol} is blocked.",
                    value=symbol,
                    limit="blocked_symbols",
                )
            )

    def _check_strategy_type(
        self,
        candidate: Mapping[str, Any],
        violations: list[ConstraintViolation],
    ) -> None:
        strategy_type = _first_string(
            candidate,
            ("strategy_type", "strategy", "structure"),
        )

        if strategy_type is None:
            return

        normalized_strategy = strategy_type.lower()

        if self.constraints.allowed_strategy_types is not None:
            allowed = {
                item.lower()
                for item in self.constraints.allowed_strategy_types
            }
            if normalized_strategy not in allowed:
                violations.append(
                    ConstraintViolation(
                        constraint="allowed_strategy_types",
                        message=f"{strategy_type} is not an allowed strategy type.",
                        value=strategy_type,
                        limit="allowed_strategy_types",
                    )
                )

        blocked = {
            item.lower()
            for item in self.constraints.blocked_strategy_types
        }
        if normalized_strategy in blocked:
            violations.append(
                ConstraintViolation(
                    constraint="blocked_strategy_types",
                    message=f"{strategy_type} is blocked.",
                    value=strategy_type,
                    limit="blocked_strategy_types",
                )
            )

    def _check_candidate_weight(
        self,
        candidate: Mapping[str, Any],
        violations: list[ConstraintViolation],
    ) -> None:
        weight = _position_weight(candidate)

        if weight is None:
            return

        min_weight = self.constraints.min_position_weight
        max_weight = self.constraints.max_position_weight

        if min_weight is not None and weight < min_weight:
            violations.append(
                ConstraintViolation(
                    constraint="min_position_weight",
                    message="Position weight is below the minimum allowed weight.",
                    value=weight,
                    limit=min_weight,
                )
            )

        if max_weight is not None and weight > max_weight:
            violations.append(
                ConstraintViolation(
                    constraint="max_position_weight",
                    message="Position weight exceeds the maximum allowed weight.",
                    value=weight,
                    limit=max_weight,
                )
            )

    def _check_candidate_liquidity(
        self,
        candidate: Mapping[str, Any],
        violations: list[ConstraintViolation],
    ) -> None:
        limits = self.constraints.liquidity_limits

        liquidity_score = _first_number(
            candidate,
            (
                "liquidity_score",
                "option_liquidity_score",
                "market_liquidity_score",
            ),
            default=None,
        )

        if liquidity_score is not None:
            liquidity_score = _percentage_to_decimal_if_needed(liquidity_score)

            if (
                limits.min_liquidity_score is not None
                and liquidity_score < limits.min_liquidity_score
            ):
                violations.append(
                    ConstraintViolation(
                        constraint="min_liquidity_score",
                        message="Liquidity score is below the minimum requirement.",
                        value=liquidity_score,
                        limit=limits.min_liquidity_score,
                    )
                )

        bid_ask_spread = _first_number(
            candidate,
            (
                "bid_ask_spread_pct",
                "spread_pct",
                "relative_spread",
            ),
            default=None,
        )

        if bid_ask_spread is not None:
            bid_ask_spread = _percentage_to_decimal_if_needed(bid_ask_spread)

            if (
                limits.max_bid_ask_spread_pct is not None
                and bid_ask_spread > limits.max_bid_ask_spread_pct
            ):
                violations.append(
                    ConstraintViolation(
                        constraint="max_bid_ask_spread_pct",
                        message="Bid/ask spread exceeds the maximum allowed spread.",
                        value=bid_ask_spread,
                        limit=limits.max_bid_ask_spread_pct,
                    )
                )

        volume = _first_number(
            candidate,
            ("volume", "option_volume"),
            default=None,
        )

        if (
            volume is not None
            and limits.min_volume is not None
            and volume < limits.min_volume
        ):
            violations.append(
                ConstraintViolation(
                    constraint="min_volume",
                    message="Volume is below the minimum requirement.",
                    value=volume,
                    limit=limits.min_volume,
                )
            )

        open_interest = _first_number(
            candidate,
            ("open_interest", "oi"),
            default=None,
        )

        if (
            open_interest is not None
            and limits.min_open_interest is not None
            and open_interest < limits.min_open_interest
        ):
            violations.append(
                ConstraintViolation(
                    constraint="min_open_interest",
                    message="Open interest is below the minimum requirement.",
                    value=open_interest,
                    limit=limits.min_open_interest,
                )
            )

    def _check_position_count(
        self,
        positions: list[Mapping[str, Any]],
        violations: list[ConstraintViolation],
    ) -> None:
        max_positions = self.constraints.max_positions

        if max_positions is None:
            return

        if len(positions) > max_positions:
            violations.append(
                ConstraintViolation(
                    constraint="max_positions",
                    message="Portfolio has more positions than allowed.",
                    value=len(positions),
                    limit=max_positions,
                )
            )

    def _check_total_weight(
        self,
        positions: list[Mapping[str, Any]],
        violations: list[ConstraintViolation],
    ) -> None:
        weights = [_position_weight(position) for position in positions]
        known_weights = [weight for weight in weights if weight is not None]

        if not known_weights:
            return

        total_weight = sum(known_weights)

        max_total_weight = self.constraints.max_total_weight
        min_total_weight = self.constraints.min_total_weight

        if max_total_weight is not None and total_weight > max_total_weight:
            violations.append(
                ConstraintViolation(
                    constraint="max_total_weight",
                    message="Total portfolio weight exceeds the maximum allowed weight.",
                    value=total_weight,
                    limit=max_total_weight,
                )
            )

        if min_total_weight is not None and total_weight < min_total_weight:
            violations.append(
                ConstraintViolation(
                    constraint="min_total_weight",
                    message="Total portfolio weight is below the minimum required weight.",
                    value=total_weight,
                    limit=min_total_weight,
                )
            )

    def _check_total_capital_at_risk(
        self,
        positions: list[Mapping[str, Any]],
        violations: list[ConstraintViolation],
    ) -> None:
        max_total_capital_at_risk = self.constraints.max_total_capital_at_risk

        if max_total_capital_at_risk is None:
            return

        capital_values = [
            _first_number(
                position,
                (
                    "capital_at_risk",
                    "capital_required",
                    "margin_required",
                    "max_loss_pct",
                    "risk_weight",
                ),
                default=None,
            )
            for position in positions
        ]

        known_capital_values = [
            _percentage_to_decimal_if_needed(value)
            for value in capital_values
            if value is not None
        ]

        if not known_capital_values:
            return

        total_capital_at_risk = sum(known_capital_values)

        if total_capital_at_risk > max_total_capital_at_risk:
            violations.append(
                ConstraintViolation(
                    constraint="max_total_capital_at_risk",
                    message="Total capital at risk exceeds the maximum allowed amount.",
                    value=total_capital_at_risk,
                    limit=max_total_capital_at_risk,
                )
            )

    def _check_group_concentration(
        self,
        positions: list[Mapping[str, Any]],
        field_names: tuple[str, ...],
        constraint_name: str,
        limit: float | None,
        violations: list[ConstraintViolation],
    ) -> None:
        if limit is None:
            return

        exposures: dict[str, float] = {}

        for position in positions:
            group = _first_string(position, field_names)
            weight = _position_weight(position)

            if group is None or weight is None:
                continue

            exposures[group] = exposures.get(group, 0.0) + weight

        for group, exposure in exposures.items():
            if exposure > limit:
                violations.append(
                    ConstraintViolation(
                        constraint=constraint_name,
                        message=f"{group} exposure exceeds the maximum allowed concentration.",
                        value=exposure,
                        limit=limit,
                    )
                )

    def _check_portfolio_greeks(
        self,
        positions: list[Mapping[str, Any]],
        violations: list[ConstraintViolation],
    ) -> None:
        limits = self.constraints.greek_limits

        exposures = {
            "delta": self._portfolio_greek_exposure(
                positions,
                ("delta", "net_delta"),
            ),
            "gamma": self._portfolio_greek_exposure(
                positions,
                ("gamma", "net_gamma"),
            ),
            "theta": self._portfolio_greek_exposure(
                positions,
                ("theta", "net_theta"),
            ),
            "vega": self._portfolio_greek_exposure(
                positions,
                ("vega", "net_vega"),
            ),
        }

        greek_limit_map = {
            "delta": limits.max_abs_delta,
            "gamma": limits.max_abs_gamma,
            "theta": limits.max_abs_theta,
            "vega": limits.max_abs_vega,
        }

        for greek_name, exposure in exposures.items():
            limit = greek_limit_map[greek_name]

            if limit is None:
                continue

            if abs(exposure) > limit:
                violations.append(
                    ConstraintViolation(
                        constraint=f"max_abs_{greek_name}",
                        message=f"Portfolio {greek_name} exposure exceeds the hard limit.",
                        value=exposure,
                        limit=limit,
                    )
                )

    def _portfolio_greek_exposure(
        self,
        positions: list[Mapping[str, Any]],
        names: tuple[str, ...],
    ) -> float:
        total = 0.0

        for position in positions:
            greek_value = _first_number(position, names, default=None)

            if greek_value is None:
                continue

            weight = _position_weight(position)

            if weight is None:
                total += greek_value
            else:
                total += greek_value * weight

        return total


def check_candidate_constraints(
    candidate: Mapping[str, Any],
    constraints: PortfolioConstraints | None = None,
) -> ConstraintCheckResult:
    return PortfolioConstraintChecker(constraints).check_candidate(candidate)


def check_portfolio_constraints(
    positions: Iterable[Mapping[str, Any]],
    constraints: PortfolioConstraints | None = None,
) -> ConstraintCheckResult:
    return PortfolioConstraintChecker(constraints).check_portfolio(positions)


def filter_candidates_by_constraints(
    candidates: Iterable[Mapping[str, Any]],
    constraints: PortfolioConstraints | None = None,
) -> list[dict[str, Any]]:
    return PortfolioConstraintChecker(constraints).filter_candidates(candidates)


def _position_weight(position: Mapping[str, Any]) -> float | None:
    value = _first_number(
        position,
        (
            "weight",
            "target_weight",
            "allocation",
            "allocation_pct",
            "position_weight",
        ),
        default=None,
    )

    if value is None:
        return None

    return _percentage_to_decimal_if_needed(value)


def _first_number(
    values: Mapping[str, Any],
    names: tuple[str, ...],
    default: float | None,
) -> float | None:
    for name in names:
        value = values.get(name)

        if value is None:
            continue

        if isinstance(value, bool):
            continue

        if isinstance(value, (int, float)):
            return float(value)

        try:
            return float(value)
        except (TypeError, ValueError):
            continue

    return default


def _first_string(
    values: Mapping[str, Any],
    names: tuple[str, ...],
) -> str | None:
    for name in names:
        value = values.get(name)

        if value is None:
            continue

        text = str(value).strip()

        if text:
            return text

    return None


def _percentage_to_decimal_if_needed(value: float) -> float:
    if abs(value) > 1.0:
        return value / 100.0

    return value
