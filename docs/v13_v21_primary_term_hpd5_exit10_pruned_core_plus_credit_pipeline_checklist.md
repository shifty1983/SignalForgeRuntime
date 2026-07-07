# SignalForge v1.3/v2.1 Pipeline Checklist

Dataset:

`v13_v21_primary_term_hpd5_exit10_pruned_core_plus_credit_20210601_20260531`

Purpose:

This document records the approved artifact chain and script/CLI path from source data through final portfolio outcomes. `artifacts\` remains disposable. `canonical\` becomes the locked local source of truth after promotion.

---

## Operating Rules

- `artifacts\` = scratch outputs, experiments, reruns.
- `canonical\` = promoted locked pipeline state.
- `config\canonical_data_registry\` = committed registry pointing to canonical.
- Future research runs should not depend on searching random artifact folders.
- Every canonical dataset must have a stage checklist, script/CLI path per stage, input paths, output paths, readiness state, checksums, and promotion manifest.

---

## Pipeline Stage Checklist

<!-- BEGIN VERIFIED_PREDECISION_QC_GATE_CHAIN_V1 -->

### 00. QuantConnect Source Root

Status: `verified`

Source root:

```text
artifacts\qc_replay_5y_behavior_inputs

Purpose:

Defines the upstream local source boundary consumed by the QC 5-year inventory chain.

Consumes / produces:

Produced by external QuantConnect pull/export workflow.
Consumed by src\signalforge\backtesting\qc_5y_data_inventory_cli.py

Verified:

 qc_5y_data_inventory_cli consumes --source-root.
 Source root contains QuantConnect pulled data/artifacts.
 Inventory builder scans the source root recursively.
 Supported file extensions are .json, .jsonl, and .csv.
 Approved and replayed source root: artifacts\qc_replay_5y_behavior_inputs.

Canonical target:

canonical\...\00_qc_source_root\
01. QC 5Y Data Inventory

Status: verified as replay stage

Script / CLI:

src\signalforge\backtesting\qc_5y_data_inventory_cli.py

Builder:

src\signalforge\backtesting\qc_5y_data_inventory.py

Verified command:

python -m signalforge.backtesting.qc_5y_data_inventory_cli `
  --source-root artifacts\qc_replay_5y_behavior_inputs `
  --output-dir artifacts\canonical_replay_validation\v13_v21_predecision_gate\01_qc_5y_data_inventory `
  --replay-start 2021-06-01 `
  --replay-end 2026-05-31

Replay output:

artifacts\canonical_replay_validation\v13_v21_predecision_gate\01_qc_5y_data_inventory\
  signalforge_qc_5y_data_inventory.json
  signalforge_qc_5y_data_inventory_summary.json

Approved artifact:

artifacts\qc_5y_data_inventory_local_rebuild_20210601_20260531\

Checklist:

 CLI replay runs.
 Inventory JSON exists.
 Inventory summary JSON exists.
 blocker_count = 0.

Note:

This stage can show is_ready = false while blocker_count = 0. The final pass/fail readiness artifact is stage 04.

02. QC 5Y Data Inventory Split

Status: verified as replay stage

Script / CLI:

src\signalforge\backtesting\qc_5y_data_inventory_split_cli.py

Builder:

src\signalforge\backtesting\qc_5y_data_inventory_split.py

Consumes:

artifacts\canonical_replay_validation\v13_v21_predecision_gate\01_qc_5y_data_inventory\signalforge_qc_5y_data_inventory.json

Verified command:

python -m signalforge.backtesting.qc_5y_data_inventory_split_cli `
  --inventory-path artifacts\canonical_replay_validation\v13_v21_predecision_gate\01_qc_5y_data_inventory\signalforge_qc_5y_data_inventory.json `
  --output-dir artifacts\canonical_replay_validation\v13_v21_predecision_gate\02_qc_5y_data_inventory_split

Replay output:

artifacts\canonical_replay_validation\v13_v21_predecision_gate\02_qc_5y_data_inventory_split\
  signalforge_qc_5y_data_inventory_split.json
  signalforge_qc_5y_data_inventory_split_summary.json

Approved artifact:

artifacts\qc_5y_data_inventory_split_local_rebuild_20210601_20260531\

Checklist:

 CLI replay runs.
 Split JSON exists.
 Split summary JSON exists.
 blocker_count = 0.
03. QC 5Y Symbol Policy From Split

Status: verified as replay stage

Script / CLI:

src\signalforge\backtesting\qc_5y_data_inventory_symbol_policy_from_split_cli.py

Builder:

src\signalforge\backtesting\qc_5y_data_inventory_symbol_policy_from_split.py

Consumes:

artifacts\canonical_replay_validation\v13_v21_predecision_gate\02_qc_5y_data_inventory_split\signalforge_qc_5y_data_inventory_split.json

Verified command:

python -m signalforge.backtesting.qc_5y_data_inventory_symbol_policy_from_split_cli `
  --split-inventory-path artifacts\canonical_replay_validation\v13_v21_predecision_gate\02_qc_5y_data_inventory_split\signalforge_qc_5y_data_inventory_split.json `
  --output-path artifacts\canonical_replay_validation\v13_v21_predecision_gate\03_qc_5y_symbol_policy\qc_5y_data_inventory_symbol_policy.json

Replay output:

artifacts\canonical_replay_validation\v13_v21_predecision_gate\03_qc_5y_symbol_policy\
  qc_5y_data_inventory_symbol_policy.json

Approved artifact:

artifacts\qc_5y_data_inventory_symbol_policy_local_rebuild_20210601_20260531\

Checklist:

 CLI replay runs.
 Symbol policy JSON exists.
04. QC 5Y Data Inventory Gate

Status: verified

Script / CLI:

src\signalforge\backtesting\qc_5y_data_inventory_gate_cli.py

Builder:

src\signalforge\backtesting\qc_5y_data_inventory_gate.py

Consumes:

artifacts\canonical_replay_validation\v13_v21_predecision_gate\02_qc_5y_data_inventory_split\signalforge_qc_5y_data_inventory_split.json
artifacts\canonical_replay_validation\v13_v21_predecision_gate\03_qc_5y_symbol_policy\qc_5y_data_inventory_symbol_policy.json

Verified command:

python -m signalforge.backtesting.qc_5y_data_inventory_gate_cli `
  --split-inventory-path artifacts\canonical_replay_validation\v13_v21_predecision_gate\02_qc_5y_data_inventory_split\signalforge_qc_5y_data_inventory_split.json `
  --policy-path artifacts\canonical_replay_validation\v13_v21_predecision_gate\03_qc_5y_symbol_policy\qc_5y_data_inventory_symbol_policy.json `
  --output-dir artifacts\canonical_replay_validation\v13_v21_predecision_gate\04_qc_5y_data_inventory_gate

Replay output:

artifacts\canonical_replay_validation\v13_v21_predecision_gate\04_qc_5y_data_inventory_gate\
  signalforge_qc_5y_data_inventory_gate.json
  signalforge_qc_5y_data_inventory_gate_summary.json

Approved artifact:

artifacts\qc_5y_data_inventory_gate_local_rebuild_20210601_20260531\

Verified replay result:

approved_is_ready      : True
replay_is_ready        : True
approved_blocker_count : 0
replay_blocker_count   : 0
source_root            : artifacts\qc_replay_5y_behavior_inputs
status                 : ready

Verified policy state:

accepted_missing_contract_outcomes_count     : 14
accepted_missing_option_behavior_count       : 20
market_symbols_missing_option_behavior_count : 20
option_underlyings_missing_contract_outcomes : 14
tradable_option_symbol_count                 : 160
required coverage failures                   : 0
policy conflicts                             : 0

Checklist:

 CLI replay runs.
 Gate JSON exists.
 Gate summary JSON exists.
 Approved and replay is_ready = true.
 Approved and replay blocker_count = 0.
05. Pre-Decision Option / Quote Coverage Audit Index

Status: discovered; exact replay pending

Purpose:

Document source and quote-coverage audit tooling that supports later v2.1 execution-feature and quote-outcome stages.

Discovered scripts / tools:

tools\audit_options_execution_symbol_coverage.py
tools\audit_options_execution_v2_source_coverage.py
tools\audit_options_execution_v2_source_coverage_complete.py
tools\audit_options_execution_v21_contract_feature_sources.py
tools\audit_decision_vs_v21_options_source_coverage.py
src\signalforge\data\required_option_quote_coverage_cli.py
src\signalforge\data\required_option_quote_resolution_coverage_cli.py
src\signalforge\backtesting\quote_outcome_source_inventory_cli.py
src\signalforge\backtesting\portfolio_quote_source_inventory_cli.py
src\signalforge\backtesting\portfolio_quote_source_join_coverage_audit_cli.py

Known related artifacts:

artifacts\options_execution_v21_contract_feature_source_audit_20210601_20260531
artifacts\decision_vs_v21_options_source_coverage_audit_20210601_20260531
artifacts\required_option_quote_coverage_20210601_20260531
artifacts\required_option_quote_coverage_after_backfill_20210601_20260531
artifacts\required_option_quote_coverage_after_retry_20210601_20260531
artifacts\quote_outcome_source_inventory_20210601_20260531
artifacts\portfolio_quote_source_inventory_20210601_20260531

Checklist:

 Exact replay command for each required audit captured.
 Required audit artifacts identified.
 Readiness states captured.
<!-- END VERIFIED_PREDECISION_QC_GATE_CHAIN_V1 -->
06. Historical Decision Rows

Status: pending exact replay verification

Canonical target:

canonical\...\06_historical_decision_rows\
07. Strategy Family Eligibility

Status: pending exact replay verification

Canonical target:

canonical\...\07_strategy_family_eligibility\
08. Option Contract Execution Features v2.1

Status: pending exact replay verification

Canonical target:

canonical\...\08_option_contract_execution_features_v21\
09. Strategy Structure Availability v2.1

Status: pending exact replay verification

Canonical target:

canonical\...\09_strategy_structure_availability_v21\
10. Resolved Strategy Execution Rules v2.1

Status: pending exact replay verification

Canonical target:

canonical\...\10_resolved_execution_rules_v21\
11. Repaired Historical Strategy Candidates

Status: pending exact replay verification

Canonical target:

canonical\...\11_repaired_strategy_candidates\
12. Calendar / Diagonal Term-Structure Augmentation

Status: pending exact replay verification

Canonical target:

canonical\...\12_term_structure_augmented_candidates\
13. Candidate Coverage Policy Attribution

Status: pending exact replay verification

Canonical target:

canonical\...\13_candidate_coverage_policy_attribution\
14. Selector Candidate Input

Status: pending exact replay verification

Canonical target:

canonical\...\14_selector_candidate_input\
15. Term HPD5 Leg-Selection Candidate Input

Status: pending exact replay verification

Canonical target:

canonical\...\15_leg_selection_candidate_input_term_hpd5\
16. Historical Strategy Leg Selection

Status: pending exact replay verification

Canonical target:

canonical\...\16_leg_selection\
17. Historical Strategy Quote Outcomes

Status: pending exact replay verification

Canonical target:

canonical\...\17_quote_outcomes_term_hpd5_exit10\
18. Walk-Forward Expectancy

Status: pending exact replay verification

Canonical target:

canonical\...\18_walk_forward_expectancy\
19. Full 10-Strategy Selector Baseline

Status: pending exact replay verification

Canonical target:

canonical\...\19_strategy_selection_full_baseline\
20. Pruned Expectancy Rows

Status: pending exact replay verification

Canonical target:

canonical\...\20_pruned_expectancy_core_plus_credit\
21. Pruned Reselected Strategy Selection

Status: pending exact replay verification

Canonical target:

canonical\...\21_strategy_selection_pruned_core_plus_credit\
22. Selected Strategy Outcomes - Pruned

Status: pending exact replay verification

Canonical target:

canonical\...\22_selected_strategy_outcomes_pruned\
23. Selected Trade Sequence - Pruned

Status: pending exact replay verification

Canonical target:

canonical\...\23_selected_trade_sequence_pruned\
24. Position Sizing Sensitivity - Pruned

Status: pending exact replay verification

Canonical target:

canonical\...\24_position_sizing_return_bound_sensitivity\
25. Equity Reconstruction Sensitivity - Pruned

Status: pending exact replay verification

Canonical target:

canonical\...\25_equity_reconstruction_return_bound_sensitivity\
26. Portfolio Metrics Report Sensitivity - Pruned

Status: pending exact replay verification

Canonical target:

canonical\...\26_metrics_return_bound_sensitivity\
Script / CLI Index

To be filled as each stage is replay-verified.

Canonical Promotion Checklist
 all stage summaries exist
 all required rows files exist
 all is_ready fields are true where the stage is a pass/fail gate
 blocker counts are zero
 checksums generated
 canonical manifest generated
 registry generated under config\canonical_data_registry\
 artifacts remain ignored
 canonical remains ignored
 registry and scripts are committed
