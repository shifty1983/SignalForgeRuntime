# SignalForge v21 Paper Candidate Lock Snapshot

## State

- paper_candidate_id: signalforge_v21_core_plus_credit_term_hpd5_exit10_allocator_v2_1_max_return_10_paper_candidate
- closure_state: closed_through_stage33_paper_candidate_lock
- paper_candidate_state: locked_for_paper_trading_review
- live_candidate_state: not_live_candidate
- active_baseline_scenario: max_return_10_allocated
- paper_trade_supported: True
- live_trade_supported: False
- strategy_count: 6

## Capital Policy

- minimum_operational_capital: 20000
- preferred_lower_paper_baseline: 25000
- validated_comparison_baseline: 100000

## Spread Policy

- preferred_clean_entry_spread_threshold: 0.1
- balanced_paper_entry_spread_cap: 0.2
- manual_review_spread_tier: >0.20 and <=0.35
- skip_default_spread_threshold_above: 0.35

## Execution Stress

- stress_state: passes_baseline_and_fee_proxy_but_fails_severe_fill_and_combined_stress
- deployment_scope: paper only
- live trading: not approved

## Canonical Hashes

- F2AA57C06BD2BA252EEA86365AA269722C575F39C0C04FFD02B159C5C32DDBC8  data\canonical\signalforge_pipeline\metadata\signalforge_pipeline_stage34_paper_candidate_closure_audit.json
- B9D128D4ADBA194069395B0D5873A5E32AFFF5CFD60FA892C44DB184BD4E4B16  data\canonical\signalforge_pipeline\33_paper_candidate_lock\signalforge_paper_candidate_lock.json
- 89E885A1C4D0727EF6DF295A7E49867E2EEFB2CB82084F72CE27C176939FC65E  data\canonical\signalforge_pipeline\29_strategy_management_rulebook_paper_lock\signalforge_strategy_management_rulebook_amended_paper_lock.json


Canonical artifacts remain ignored. This file is the tracked lock record.
