from __future__ import annotations

import importlib


def test_v3_2_1_native_quote_pnl_stress_v1_imports():
    module = importlib.import_module(
        "signalforge.backtesting.v3_2_1_native_quote_pnl_stress_v1"
    )

    assert module is not None
