from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml


UNIVERSE_GROUP_ASSET_CLASSES = {
    "etf_core": "equities",
    "us_equity_size_style": "equities",
    "sectors": "equities",
    "industry_etfs": "equities",
    "factor_etfs": "equities",
    "dividend_income": "equities",
    "international_core": "equities",
    "international_regions": "equities",
    "international_countries": "equities",
    "bonds_rates": "bonds",
    "credit_income": "credit",
    "commodities_broad": "commodities",
    "commodities_metals": "commodities",
    "commodities_energy": "commodities",
    "commodities_agriculture": "commodities",
    "currencies": "currencies",
    "volatility": "volatility",
}

WATCHLIST_GROUP_ASSET_CLASSES = {
    "growth": "equities",
    "value": "equities",
    "quality": "equities",
    "low_volatility": "equities",
}

INFLATION_LINKED_BOND_SYMBOLS = {
    "TIP",
    "STIP",
    "SCHP",
    "VTIP",
}


def load_asset_class_map_from_universe_config(path: str | Path) -> dict[str, str]:
    config_path = Path(path)

    if not config_path.exists():
        raise FileNotFoundError(f"universe config does not exist: {config_path}")

    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

    if not isinstance(config, Mapping):
        raise ValueError("universe config must be a mapping")

    return build_asset_class_map_from_universe_config(config)


def build_asset_class_map_from_universe_config(
    config: Mapping[str, Any],
) -> dict[str, str]:
    mapping: dict[str, str] = {}

    universes = config.get("universes")
    if isinstance(universes, Mapping):
        for group_name, asset_class in UNIVERSE_GROUP_ASSET_CLASSES.items():
            _add_symbols_from_group(
                mapping=mapping,
                group=universes.get(group_name),
                asset_class=asset_class,
            )

        inflation_group = universes.get("inflation_real_assets")
        if isinstance(inflation_group, Mapping):
            for symbol in inflation_group.get("symbols") or []:
                cleaned = _clean_symbol(symbol)
                if cleaned in INFLATION_LINKED_BOND_SYMBOLS:
                    mapping.setdefault(cleaned, "bonds")

    watchlists = config.get("watchlists")
    if isinstance(watchlists, Mapping):
        for group_name, asset_class in WATCHLIST_GROUP_ASSET_CLASSES.items():
            _add_symbols_from_group(
                mapping=mapping,
                group=watchlists.get(group_name),
                asset_class=asset_class,
            )

    return dict(sorted(mapping.items()))


def _add_symbols_from_group(
    *,
    mapping: dict[str, str],
    group: Any,
    asset_class: str,
) -> None:
    if not isinstance(group, Mapping):
        return

    symbols = group.get("symbols")
    if not isinstance(symbols, list):
        return

    for symbol in symbols:
        cleaned = _clean_symbol(symbol)
        if cleaned:
            mapping.setdefault(cleaned, asset_class)


def _clean_symbol(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip().upper()
    return text or None


