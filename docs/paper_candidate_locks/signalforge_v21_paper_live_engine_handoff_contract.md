# SignalForge v21 Paper/Live Engine Handoff Contract

## Source

- paper_candidate_id: signalforge_v21_core_plus_credit_term_hpd5_exit10_allocator_v2_1_max_return_10_paper_candidate
- source_state: locked_paper_candidate
- active_baseline_scenario: max_return_10_allocated

## Engine Status

- paper_engine_enabled: True
- live_engine_enabled: False
- live_trade_supported: False

## Capital Policy

- minimum_operational_capital: 20000
- preferred_lower_paper_baseline: 25000
- validated_comparison_baseline: 100000

## Spread Policy

- preferred_clean_entry_spread_threshold: 0.1
- balanced_paper_entry_spread_cap: 0.2
- manual_review_spread_tier: >0.20 and <=0.35
- skip_default_spread_threshold_above: 0.35

## Allocator Policy

- bucket 5: 3 units
- bucket 4: 2 units
- bucket 3: 1 unit
- bucket 2: 0 units
- bucket 1: 0 units

## Layer Contract

The migrated expectancy, optimization, and portfolio construction layers consume this contract. They must not mutate the locked paper candidate.
