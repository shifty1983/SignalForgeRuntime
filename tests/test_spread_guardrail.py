from signalforge.rulebooks.spread_guardrail import passes_spread_guardrail


def test_spread_guardrail_passes_at_threshold():
    assert passes_spread_guardrail(0.125)


def test_spread_guardrail_blocks_above_threshold():
    assert not passes_spread_guardrail(0.1251)


def test_spread_guardrail_blocks_missing():
    assert not passes_spread_guardrail(None)




