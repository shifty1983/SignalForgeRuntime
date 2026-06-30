from signalforge.rulebooks.prior_symbol_regime_state import (
    PriorSymbolRegimeStats,
    passes_prior_symbol_regime_gate,
)


def test_prior_gate_passes_when_no_stats():
    assert passes_prior_symbol_regime_gate(None)


def test_prior_gate_passes_when_sample_is_too_small():
    stats = PriorSymbolRegimeStats(
        prior_count=7,
        prior_net_pnl=-1000,
        prior_profit_factor=0.50,
    )
    assert passes_prior_symbol_regime_gate(stats)


def test_prior_gate_blocks_weak_symbol_regime_prior():
    stats = PriorSymbolRegimeStats(
        prior_count=8,
        prior_net_pnl=-1,
        prior_profit_factor=0.90,
    )
    assert not passes_prior_symbol_regime_gate(stats)


def test_prior_gate_passes_profitable_prior():
    stats = PriorSymbolRegimeStats(
        prior_count=8,
        prior_net_pnl=1,
        prior_profit_factor=0.50,
    )
    assert passes_prior_symbol_regime_gate(stats)

