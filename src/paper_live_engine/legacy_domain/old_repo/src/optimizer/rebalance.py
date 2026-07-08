"""
Optimizer rebalance logic.

This module compares the current portfolio against a newly optimized target
portfolio and produces actionable rebalance instructions.

It does not choose the target portfolio. That belongs in solver.py.
It does not score candidates. That belongs in objective.py.
It does not enforce portfolio rules. That belongs in constraints.py.

Its job:
- compare current weights to target weights
- identify buys, sells, increases, reductions, and holds
- calculate turnover
- return a clean rebalance plan
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from src.optimizer.portfolio import OptimizedPortfolio, OptimizedPosition


@dataclass(frozen=True)
class RebalanceConfig:
    """
    Configuration for portfolio rebalance decisions.
    """

    min_trade_weight: float = 0.01
    include_holds: bool = False

    current_portfolio_name: str = "current_portfolio"
    target_portfolio_name: str = "target_portfolio"

    key_fields: tuple[str, ...] = (
        "symbol",
        "strategy_type",
        "expiration",
        "expiry",
        "expiration_date",
        "strike",
        "option_type",
        "side",
    )


@dataclass(frozen=True)
class RebalanceInstruction:
    """
    A single rebalance action.
    """

    action: str
    key: str
    symbol: str
    current_weight: float
    target_weight: float
    trade_weight: float
    reason: str
    strategy_type: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def abs_trade_weight(self) -> float:
        return abs(self.trade_weight)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "key": self.key,
            "symbol": self.symbol,
            "strategy_type": self.strategy_type,
            "current_weight": round(self.current_weight, 6),
            "target_weight": round(self.target_weight, 6),
            "trade_weight": round(self.trade_weight, 6),
            "abs_trade_weight": round(self.abs_trade_weight, 6),
            "reason": self.reason,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class RebalancePlan:
    """
    Full rebalance output.
    """

    current_portfolio: OptimizedPortfolio
    target_portfolio: OptimizedPortfolio
    instructions: tuple[RebalanceInstruction, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def trade_instructions(self) -> tuple[RebalanceInstruction, ...]:
        return tuple(
            instruction
            for instruction in self.instructions
            if instruction.action != "HOLD"
        )

    @property
    def buy_weight(self) -> float:
        return sum(
            instruction.trade_weight
            for instruction in self.trade_instructions
            if instruction.trade_weight > 0
        )

    @property
    def sell_weight(self) -> float:
        return abs(
            sum(
                instruction.trade_weight
                for instruction in self.trade_instructions
                if instruction.trade_weight < 0
            )
        )

    @property
    def net_weight_change(self) -> float:
        return sum(
            instruction.trade_weight
            for instruction in self.trade_instructions
        )

    @property
    def total_turnover(self) -> float:
        return sum(
            abs(instruction.trade_weight)
            for instruction in self.trade_instructions
        )

    @property
    def instruction_count(self) -> int:
        return len(self.instructions)

    @property
    def trade_count(self) -> int:
        return len(self.trade_instructions)

    def actions(self, action: str) -> list[RebalanceInstruction]:
        action_upper = action.upper()
        return [
            instruction
            for instruction in self.instructions
            if instruction.action == action_upper
        ]

    def to_rows(self) -> list[dict[str, Any]]:
        return [instruction.to_dict() for instruction in self.instructions]

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": {
                "instruction_count": self.instruction_count,
                "trade_count": self.trade_count,
                "buy_weight": round(self.buy_weight, 6),
                "sell_weight": round(self.sell_weight, 6),
                "net_weight_change": round(self.net_weight_change, 6),
                "total_turnover": round(self.total_turnover, 6),
                "current_total_weight": round(self.current_portfolio.total_weight(), 6),
                "target_total_weight": round(self.target_portfolio.total_weight(), 6),
            },
            "current_portfolio": self.current_portfolio.to_dict(),
            "target_portfolio": self.target_portfolio.to_dict(),
            "instructions": self.to_rows(),
            "metadata": dict(self.metadata),
        }


class PortfolioRebalancer:
    """
    Creates rebalance plans from current and target portfolio positions.
    """

    def __init__(self, config: RebalanceConfig | None = None) -> None:
        self.config = config or RebalanceConfig()

        if self.config.min_trade_weight < 0:
            raise ValueError("min_trade_weight cannot be negative.")

    def create_plan(
        self,
        current_positions: OptimizedPortfolio | Iterable[Mapping[str, Any] | OptimizedPosition],
        target_positions: OptimizedPortfolio | Iterable[Mapping[str, Any] | OptimizedPosition],
        metadata: Mapping[str, Any] | None = None,
    ) -> RebalancePlan:
        current_rows = self._aggregate_by_key(
            self._normalize_positions(current_positions)
        )
        target_rows = self._aggregate_by_key(
            self._normalize_positions(target_positions)
        )

        instructions: list[RebalanceInstruction] = []

        all_keys = sorted(set(current_rows) | set(target_rows))

        for key in all_keys:
            current = current_rows.get(key)
            target = target_rows.get(key)

            current_weight = _position_weight(current) if current is not None else 0.0
            target_weight = _position_weight(target) if target is not None else 0.0
            trade_weight = target_weight - current_weight

            action, reason = self._determine_action(
                current_weight=current_weight,
                target_weight=target_weight,
                trade_weight=trade_weight,
            )

            if action == "HOLD" and not self.config.include_holds:
                continue

            source = target or current or {}
            symbol = _first_string(source, ("symbol", "ticker", "underlying"))

            if symbol is None:
                symbol = key

            instructions.append(
                RebalanceInstruction(
                    action=action,
                    key=key,
                    symbol=symbol,
                    strategy_type=_first_string(
                        source,
                        ("strategy_type", "strategy", "structure"),
                    ),
                    current_weight=current_weight,
                    target_weight=target_weight,
                    trade_weight=trade_weight,
                    reason=reason,
                    metadata={
                        "current": dict(current or {}),
                        "target": dict(target or {}),
                    },
                )
            )

        current_portfolio = OptimizedPortfolio.from_candidates(
            candidates=current_rows.values(),
            name=self.config.current_portfolio_name,
        )

        target_portfolio = OptimizedPortfolio.from_candidates(
            candidates=target_rows.values(),
            name=self.config.target_portfolio_name,
        )

        return RebalancePlan(
            current_portfolio=current_portfolio,
            target_portfolio=target_portfolio,
            instructions=tuple(instructions),
            metadata=dict(metadata or {}),
        )

    def _determine_action(
        self,
        current_weight: float,
        target_weight: float,
        trade_weight: float,
    ) -> tuple[str, str]:
        threshold = self.config.min_trade_weight

        if abs(trade_weight) < threshold:
            return "HOLD", "within_rebalance_threshold"

        if abs(current_weight) < threshold and abs(target_weight) >= threshold:
            if trade_weight > 0:
                return "BUY", "target_position_not_currently_held"
            return "SELL", "new_target_weight_is_negative"

        if abs(target_weight) < threshold and abs(current_weight) >= threshold:
            return "SELL", "position_not_in_target_portfolio"

        if trade_weight > 0:
            return "INCREASE", "target_weight_above_current_weight"

        return "REDUCE", "target_weight_below_current_weight"

    def _normalize_positions(
        self,
        positions: OptimizedPortfolio | Iterable[Mapping[str, Any] | OptimizedPosition],
    ) -> list[dict[str, Any]]:
        if isinstance(positions, OptimizedPortfolio):
            return positions.to_rows()

        rows: list[dict[str, Any]] = []

        for position in positions:
            if isinstance(position, OptimizedPosition):
                rows.append(position.to_dict())
            elif isinstance(position, Mapping):
                rows.append(dict(position))
            else:
                raise TypeError(
                    "Positions must be mappings, OptimizedPosition objects, "
                    "or an OptimizedPortfolio."
                )

        return rows

    def _aggregate_by_key(
        self,
        rows: Iterable[Mapping[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        aggregated: dict[str, dict[str, Any]] = {}

        for row in rows:
            key = self._position_key(row)
            weight = _position_weight(row)

            if key not in aggregated:
                aggregated[key] = dict(row)
                aggregated[key]["weight"] = weight
                continue

            existing = aggregated[key]
            existing["weight"] = _position_weight(existing) + weight

        return aggregated

    def _position_key(self, row: Mapping[str, Any]) -> str:
        direct_id = _first_string(
            row,
            ("position_id", "trade_id", "candidate_id"),
        )

        if direct_id is not None:
            return direct_id

        components: list[str] = []

        for field_name in self.config.key_fields:
            value = row.get(field_name)

            if value is None:
                continue

            text = str(value).strip()

            if text:
                components.append(text.upper())

        if not components:
            raise ValueError(
                "Unable to build rebalance key. Position requires at least a symbol, "
                "ticker, underlying, position_id, trade_id, or candidate_id."
            )

        return "|".join(components)


def create_rebalance_plan(
    current_positions: OptimizedPortfolio | Iterable[Mapping[str, Any] | OptimizedPosition],
    target_positions: OptimizedPortfolio | Iterable[Mapping[str, Any] | OptimizedPosition],
    config: RebalanceConfig | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> RebalancePlan:
    """
    Convenience function for creating a rebalance plan.
    """

    return PortfolioRebalancer(config=config).create_plan(
        current_positions=current_positions,
        target_positions=target_positions,
        metadata=metadata,
    )


def _position_weight(position: Mapping[str, Any] | None) -> float:
    if position is None:
        return 0.0

    value = _first_number(
        position,
        (
            "weight",
            "target_weight",
            "allocation",
            "allocation_pct",
            "position_weight",
        ),
        default=0.0,
    )

    return _percentage_to_decimal_if_needed(value)


def _first_number(
    values: Mapping[str, Any],
    names: tuple[str, ...],
    default: float,
) -> float:
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
