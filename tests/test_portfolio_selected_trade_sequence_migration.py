from __future__ import annotations

import importlib


def test_portfolio_selected_trade_sequence_imports():
    module = importlib.import_module(
        "signalforge.backtesting.portfolio_selected_trade_sequence"
    )

    assert module is not None


def test_portfolio_selected_trade_sequence_cli_imports():
    module = importlib.import_module(
        "signalforge.backtesting.portfolio_selected_trade_sequence_cli"
    )

    assert module is not None


