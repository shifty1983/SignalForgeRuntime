from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from typing import Any

from signalforge.engines.strategy_selection.research_adapter import StrategySelectionInputContractError


OPTION_BEHAVIOR_HANDOFF_ARTIFACT_TYPE = "option_behavior_strategy_handoff"

OPTION_BEHAVIOR_BLOCKING_CONSTRAINTS = {
    "block_options_candidate_generation",
}


def attach_option_behavior_to_strategy_handoff(
    handoff_result: Any,
    option_behavior_handoffs: Any | None,
    *,
    require_option_behavior: bool = False,
) -> Any:
    """
    Attach option behavior context to the accepted research/backtest handoff before
    strategy selection adapts it into candidate rows.

    This is a pure integration adapter. It does not classify options, generate
    strategies, score expected value, select trades, write logs, create operation
    records, route orders, submit orders, model fills, model slippage, or perform
    live execution.
    """

    if option_behavior_handoffs is None:
        if require_option_behavior:
            raise StrategySelectionInputContractError(
                "option behavior handoff is required"
            )

        return handoff_result

    payload = _to_plain_mapping(handoff_result)

    option_handoff_by_symbol = _normalize_option_behavior_handoffs(
        option_behavior_handoffs
    )

    symbols = _accepted_symbols(payload)

    missing_symbols = [
        symbol
        for symbol in symbols
        if str(symbol) not in option_handoff_by_symbol
    ]

    if require_option_behavior and missing_symbols:
        raise StrategySelectionInputContractError(
            "missing option behavior handoff for symbols: "
            + ", ".join(sorted(str(symbol) for symbol in missing_symbols))
        )

    enriched = dict(payload)

    diagnostics_source = _get_any(
        payload,
        "diagnostics",
        "research_diagnostics",
        default={},
    )

    enriched_diagnostics: dict[str, dict[str, Any]] = {}

    for symbol in symbols:
        symbol_key = str(symbol)
        base_diagnostics = _mapping_for_symbol(diagnostics_source, symbol)
        option_handoff = option_handoff_by_symbol.get(symbol_key)

        if option_handoff is not None:
            base_diagnostics.update(
                _option_behavior_diagnostic_fields(option_handoff)
            )

        enriched_diagnostics[symbol_key] = base_diagnostics

    enriched["diagnostics"] = enriched_diagnostics
    enriched["research_diagnostics"] = enriched_diagnostics

    metadata = _metadata_from_payload(payload)
    metadata.update(
        {
            "option_behavior_attached": True,
            "option_behavior_symbols": sorted(option_handoff_by_symbol),
            "option_behavior_contract_version": (
                "option_behavior_to_strategy_selection_v1"
            ),
        }
    )

    if "handoff_metadata" in enriched:
        enriched["handoff_metadata"] = metadata
    else:
        enriched["metadata"] = metadata

    return enriched


def _normalize_option_behavior_handoffs(
    option_behavior_handoffs: Any,
) -> dict[str, Mapping[str, Any]]:
    if isinstance(option_behavior_handoffs, Mapping):
        if _is_option_behavior_handoff(option_behavior_handoffs):
            symbol = _symbol_from_option_handoff(option_behavior_handoffs)
            return {symbol: option_behavior_handoffs}

        normalized: dict[str, Mapping[str, Any]] = {}

        for symbol, handoff in option_behavior_handoffs.items():
            if not isinstance(handoff, Mapping):
                raise StrategySelectionInputContractError(
                    "option behavior handoff values must be mappings"
                )

            if not _is_option_behavior_handoff(handoff):
                raise StrategySelectionInputContractError(
                    "invalid option behavior strategy handoff"
                )

            handoff_symbol = _symbol_from_option_handoff(handoff)

            normalized[str(symbol)] = handoff

            if str(symbol) != handoff_symbol:
                normalized[handoff_symbol] = handoff

        return normalized

    if isinstance(option_behavior_handoffs, Sequence) and not isinstance(
        option_behavior_handoffs,
        (str, bytes),
    ):
        normalized = {}

        for handoff in option_behavior_handoffs:
            if not isinstance(handoff, Mapping):
                raise StrategySelectionInputContractError(
                    "option behavior handoff entries must be mappings"
                )

            if not _is_option_behavior_handoff(handoff):
                raise StrategySelectionInputContractError(
                    "invalid option behavior strategy handoff"
                )

            normalized[_symbol_from_option_handoff(handoff)] = handoff

        return normalized

    raise StrategySelectionInputContractError(
        "invalid option_behavior_handoffs shape"
    )


def _option_behavior_diagnostic_fields(
    option_handoff: Mapping[str, Any],
) -> dict[str, Any]:
    option_context = option_handoff.get("option_behavior_context")

    if not isinstance(option_context, Mapping):
        option_context = {}

    constraints = _string_list(
        option_handoff.get("strategy_generation_constraints")
    )
    warnings = _string_list(option_handoff.get("warnings"))
    blocked_reasons = _string_list(option_handoff.get("blocked_reasons"))

    status = _string_or_none(option_handoff.get("status"))
    strategy_generation_mode = _string_or_none(
        option_handoff.get("strategy_generation_mode")
    )

    fields: dict[str, Any] = {
        "option_behavior_status": status,
        "option_behavior_state": _string_or_none(
            option_context.get("option_behavior_state")
        ),
        "option_behavior_score": option_context.get("option_behavior_score"),
        "option_strategy_generation_mode": strategy_generation_mode,
        "option_strategy_generation_constraints": constraints,
        "option_behavior_warnings": warnings,
        "option_behavior_blocked_reasons": blocked_reasons,
        "option_iv_behavior": _string_or_none(
            option_context.get("iv_behavior")
        ),
        "option_vol_premium_behavior": _string_or_none(
            option_context.get("vol_premium_behavior")
        ),
        "option_liquidity_behavior": _string_or_none(
            option_context.get("liquidity_behavior")
        ),
        "option_skew_behavior": _string_or_none(
            option_context.get("skew_behavior")
        ),
        "option_term_structure_behavior": _string_or_none(
            option_context.get("term_structure_behavior")
        ),
        "option_greek_behavior": _string_or_none(
            option_context.get("greek_behavior")
        ),
    }

    if _is_blocking_option_handoff(
        status=status,
        constraints=constraints,
        blocked_reasons=blocked_reasons,
    ):
        fields["diagnostic_status"] = "failed"
        fields["option_behavior_blocked"] = True
    elif status == "needs_review":
        fields["option_behavior_needs_review"] = True

    return fields


def _is_blocking_option_handoff(
    *,
    status: str | None,
    constraints: list[str],
    blocked_reasons: list[str],
) -> bool:
    if status == "blocked" or blocked_reasons:
        return True

    return any(
        constraint in OPTION_BEHAVIOR_BLOCKING_CONSTRAINTS
        for constraint in constraints
    )


def _is_option_behavior_handoff(source: Mapping[str, Any]) -> bool:
    return source.get("artifact_type") == OPTION_BEHAVIOR_HANDOFF_ARTIFACT_TYPE


def _symbol_from_option_handoff(option_handoff: Mapping[str, Any]) -> str:
    symbol = _string_or_none(option_handoff.get("symbol"))

    if symbol is None:
        raise StrategySelectionInputContractError(
            "option behavior handoff is missing symbol"
        )

    return symbol


def _accepted_symbols(payload: Mapping[str, Any]) -> list[Any]:
    symbols = _get_any(
        payload,
        "accepted_symbols",
        "symbols",
        "asset_symbols",
        default=None,
    )

    if symbols is None:
        target_weights = _get_any(
            payload,
            "target_weights",
            "accepted_target_weights",
            "weights",
            default=None,
        )

        if isinstance(target_weights, Mapping):
            symbols = sorted(target_weights)

    if symbols is None:
        return []

    if isinstance(symbols, str):
        return [symbols]

    if isinstance(symbols, Sequence):
        return list(symbols)

    return []


def _metadata_from_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    for field_name in ("handoff_metadata", "metadata"):
        value = payload.get(field_name)

        if isinstance(value, Mapping):
            return dict(value)

    return {}


def _mapping_for_symbol(source: Any, symbol: Any) -> dict[str, Any]:
    if not isinstance(source, Mapping):
        return {}

    if symbol in source and isinstance(source[symbol], Mapping):
        return dict(source[symbol])

    string_symbol = str(symbol)

    if string_symbol in source and isinstance(source[string_symbol], Mapping):
        return dict(source[string_symbol])

    return dict(source)


def _get_any(
    source: Mapping[str, Any],
    *names: str,
    default: Any = None,
) -> Any:
    for name in names:
        if name in source:
            return source[name]

    return default


def _to_plain_mapping(source: Any) -> Mapping[str, Any]:
    if is_dataclass(source):
        source = asdict(source)

    if not isinstance(source, Mapping):
        raise StrategySelectionInputContractError(
            "handoff_result must be a mapping when attaching option behavior"
        )

    return source


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    strings: list[str] = []

    for item in value:
        string_value = _string_or_none(item)

        if string_value is not None:
            strings.append(string_value)

    return strings


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None

    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None

    return None
