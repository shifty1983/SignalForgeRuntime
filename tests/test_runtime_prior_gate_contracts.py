from __future__ import annotations

from signalforge.contracts.runtime_inputs import RUNTIME_INPUT_CONTRACTS_BY_NAME
from signalforge.contracts.runtime_source_map import RUNTIME_SOURCE_MAPPINGS_BY_INPUT


def test_v3_2_2_prior_gate_evaluation_outcomes_contract_exists():
    contract = RUNTIME_INPUT_CONTRACTS_BY_NAME["v3_2_2_prior_gate_evaluation_outcomes"]

    assert contract.path == "data/runtime/rule_state/v3_2_2_prior_gate_evaluation_outcomes.jsonl"
    assert contract.relative_path == contract.path
    assert contract.required is True
    assert contract.max_age_days is None


def test_v3_2_2_prior_state_source_map_exists():
    mapping = RUNTIME_SOURCE_MAPPINGS_BY_INPUT["v3_2_2_prior_symbol_regime_state"]

    assert mapping.seed_source_path == "artifacts/v3_2_2_symbol_regime_walkforward_prune_stress_v1_20230101_20260531"
    assert mapping.seed_source_relative_path == mapping.seed_source_path
    assert mapping.builder_module == "signalforge.bootstrap.prior_symbol_regime_state_builder"


def test_runtime_contracts_have_source_mappings():
    contract_names = set(RUNTIME_INPUT_CONTRACTS_BY_NAME)
    mapping_names = set(RUNTIME_SOURCE_MAPPINGS_BY_INPUT)

    assert contract_names == mapping_names




