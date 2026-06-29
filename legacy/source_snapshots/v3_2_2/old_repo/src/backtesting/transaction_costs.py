from __future__ import annotations

from dataclasses import dataclass


def commission_cost(
    quantity: float,
    commission_per_share: float = 0.0,
) -> float:
    if commission_per_share < 0:
        raise ValueError("Commission per share cannot be negative.")

    return abs(quantity) * commission_per_share


def slippage_cost(
    quantity: float,
    price: float,
    slippage_bps: float = 0.0,
) -> float:
    if price < 0:
        raise ValueError("Price cannot be negative.")

    if slippage_bps < 0:
        raise ValueError("Slippage bps cannot be negative.")

    notional = abs(quantity) * price

    return notional * (slippage_bps / 10_000)


def total_transaction_cost(
    quantity: float,
    price: float,
    commission_per_share: float = 0.0,
    slippage_bps: float = 0.0,
) -> float:
    return (
        commission_cost(
            quantity=quantity,
            commission_per_share=commission_per_share,
        )
        + slippage_cost(
            quantity=quantity,
            price=price,
            slippage_bps=slippage_bps,
        )
    )


def execution_price(
    price: float,
    side: str,
    slippage_bps: float = 0.0,
) -> float:
    if price < 0:
        raise ValueError("Price cannot be negative.")

    if slippage_bps < 0:
        raise ValueError("Slippage bps cannot be negative.")

    side = side.lower()

    if side not in {"buy", "sell"}:
        raise ValueError("Side must be 'buy' or 'sell'.")

    slippage_multiplier = slippage_bps / 10_000

    if side == "buy":
        return price * (1 + slippage_multiplier)

    return price * (1 - slippage_multiplier)


def infer_trade_side(quantity: float) -> str:
    if quantity > 0:
        return "buy"

    if quantity < 0:
        return "sell"

    raise ValueError("Quantity cannot be zero when inferring trade side.")


@dataclass(frozen=True)
class TransactionCostModel:
    commission_per_share: float = 0.0
    slippage_bps: float = 0.0

    def __post_init__(self) -> None:
        if self.commission_per_share < 0:
            raise ValueError("Commission per share cannot be negative.")

        if self.slippage_bps < 0:
            raise ValueError("Slippage bps cannot be negative.")

    def estimate(
        self,
        quantity: float,
        price: float,
    ) -> float:
        return total_transaction_cost(
            quantity=quantity,
            price=price,
            commission_per_share=self.commission_per_share,
            slippage_bps=self.slippage_bps,
        )

    def adjusted_execution_price(
        self,
        price: float,
        quantity: float,
    ) -> float:
        side = infer_trade_side(quantity)

        return execution_price(
            price=price,
            side=side,
            slippage_bps=self.slippage_bps,
        )
