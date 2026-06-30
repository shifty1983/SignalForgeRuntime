from __future__ import annotations

import importlib


def test_portfolio_position_sizing_replay_imports():
    module = importlib.import_module(
        "signalforge.backtesting.portfolio_position_sizing_replay"
    )

    assert module is not None


def test_portfolio_position_sizing_replay_cli_imports():
    module = importlib.import_module(
        "signalforge.backtesting.portfolio_position_sizing_replay_cli"
    )

    assert module is not None

