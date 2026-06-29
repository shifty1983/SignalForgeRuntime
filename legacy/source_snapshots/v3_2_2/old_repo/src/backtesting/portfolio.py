from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from src.backtesting.transaction_costs import TransactionCostModel


@dataclass
class Position:
    symbol: str
    quantity: float = 0.0
    last_price: float = 0.0

    @property
    def market_value(self) -> float:
        return self.quantity * self.last_price


@dataclass
class TradeRecord:
    symbol: str
    quantity: float
    price: float
    gross_value: float
    transaction_cost: float
    cash_after_trade: float
    trade_date: datetime | None = None


@dataclass
class Portfolio:
    cash: float
    positions: dict[str, Position] = field(default_factory=dict)
    transaction_cost_model: TransactionCostModel = field(
        default_factory=TransactionCostModel
    )
    trade_history: list[TradeRecord] = field(default_factory=list)

    def update_price(self, symbol: str, price: float) -> None:
        symbol = symbol.upper()

        if price < 0:
            raise ValueError("Price cannot be negative.")

        if symbol not in self.positions:
            self.positions[symbol] = Position(symbol=symbol)

        self.positions[symbol].last_price = price

    def set_position(self, symbol: str, quantity: float, price: float) -> None:
        symbol = symbol.upper()

        if price < 0:
            raise ValueError("Price cannot be negative.")

        self.positions[symbol] = Position(
            symbol=symbol,
            quantity=quantity,
            last_price=price,
        )

    @property
    def invested_value(self) -> float:
        return sum(position.market_value for position in self.positions.values())

    @property
    def nav(self) -> float:
        return self.cash + self.invested_value

    @property
    def total_transaction_costs(self) -> float:
        return sum(trade.transaction_cost for trade in self.trade_history)

    def weight(self, symbol: str) -> float:
        symbol = symbol.upper()

        if self.nav == 0:
            return 0.0

        position = self.positions.get(symbol)

        if position is None:
            return 0.0

        return position.market_value / self.nav

    def weights(self) -> dict[str, float]:
        if self.nav == 0:
            return {symbol: 0.0 for symbol in self.positions}

        return {
            symbol: position.market_value / self.nav
            for symbol, position in self.positions.items()
        }

    def trade(
        self,
        symbol: str,
        quantity: float,
        price: float,
        trade_date: datetime | None = None,
    ) -> TradeRecord:
        symbol = symbol.upper()

        if price < 0:
            raise ValueError("Price cannot be negative.")

        if quantity == 0:
            raise ValueError("Quantity cannot be zero.")

        gross_value = quantity * price
        transaction_cost = self.transaction_cost_model.estimate(
            quantity=quantity,
            price=price,
        )

        if symbol not in self.positions:
            self.positions[symbol] = Position(symbol=symbol)

        self.positions[symbol].quantity += quantity
        self.positions[symbol].last_price = price

        self.cash -= gross_value
        self.cash -= transaction_cost

        trade_record = TradeRecord(
            symbol=symbol,
            quantity=quantity,
            price=price,
            gross_value=gross_value,
            transaction_cost=transaction_cost,
            cash_after_trade=self.cash,
            trade_date=trade_date,
        )

        self.trade_history.append(trade_record)

        if self.positions[symbol].quantity == 0:
            del self.positions[symbol]

        return trade_record

    def target_quantity(self, symbol: str, target_weight: float, price: float) -> float:
        if price <= 0:
            raise ValueError("Price must be greater than zero.")

        target_value = self.nav * target_weight
        return target_value / price

    def rebalance_to_weights(
        self,
        target_weights: dict[str, float],
        prices: dict[str, float],
        trade_date: datetime | None = None,
    ) -> list[TradeRecord]:
        normalized_targets = {
            symbol.upper(): weight for symbol, weight in target_weights.items()
        }

        normalized_prices = {
            symbol.upper(): price for symbol, price in prices.items()
        }

        trades = []

        for symbol, price in normalized_prices.items():
            self.update_price(symbol, price)

        for symbol, target_weight in normalized_targets.items():
            if symbol not in normalized_prices:
                raise ValueError(f"Missing price for symbol: {symbol}")

            price = normalized_prices[symbol]
            current_quantity = self.positions.get(symbol, Position(symbol)).quantity
            desired_quantity = self.target_quantity(symbol, target_weight, price)
            trade_quantity = desired_quantity - current_quantity

            if round(trade_quantity, 12) == 0:
                continue

            trade_record = self.trade(
                symbol=symbol,
                quantity=trade_quantity,
                price=price,
                trade_date=trade_date,
            )

            trades.append(trade_record)

        return trades

    def clear_trade_history(self) -> None:
        self.trade_history.clear()
