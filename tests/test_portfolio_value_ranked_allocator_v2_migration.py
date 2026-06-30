from __future__ import annotations

import importlib


def test_portfolio_value_ranked_allocator_v2_imports():
    module = importlib.import_module(
        "signalforge.backtesting.portfolio_value_ranked_allocator_v2"
    )

    assert module is not None

