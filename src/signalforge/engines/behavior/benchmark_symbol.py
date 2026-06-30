from __future__ import annotations

from typing import Any


DEFAULT_BENCHMARK_SYMBOL = "SPY"

BOND_BENCHMARK_SYMBOL = "AGG"
DURATION_BENCHMARK_SYMBOL = "TLT"
CREDIT_BENCHMARK_SYMBOL = "LQD"
HIGH_YIELD_BENCHMARK_SYMBOL = "HYG"
COMMODITY_BENCHMARK_SYMBOL = "DBC"
CURRENCY_BENCHMARK_SYMBOL = "UUP"
VOLATILITY_BENCHMARK_SYMBOL = "VIXY"
TECH_BENCHMARK_SYMBOL = "QQQ"
SMALL_CAP_BENCHMARK_SYMBOL = "IWM"

TECH_OR_GROWTH_SYMBOLS = {
    "QQQ",
    "XLK",
    "XLC",
    "SMH",
    "SOXX",
    "XSD",
    "ARKK",
    "IWF",
    "VUG",
    "SCHG",
}

SMALL_CAP_SYMBOLS = {
    "IWM",
    "IJR",
    "IWN",
    "IWO",
    "VB",
    "VBK",
    "VBR",
}

BOND_SYMBOLS = {
    "AGG",
    "BND",
    "GOVT",
    "IEF",
    "IEI",
    "SHY",
    "TLH",
    "TLT",
    "VGIT",
    "VGLT",
    "VGSH",
    "SCHZ",
    "SCHP",
    "STIP",
    "TIP",
    "VTIP",
}

DURATION_SYMBOLS = {
    "TLT",
    "TLH",
    "VGLT",
}

CREDIT_SYMBOLS = {
    "HYG",
    "JNK",
    "SHYG",
    "LQD",
    "VCIT",
    "VCSH",
    "EMB",
    "HYD",
    "MUB",
    "BKLN",
    "SRLN",
}

HIGH_YIELD_SYMBOLS = {
    "HYG",
    "JNK",
    "SHYG",
    "HYD",
}

COMMODITY_SYMBOLS = {
    "DBC",
    "DBA",
    "GSG",
    "COMT",
    "PDBC",
    "USCI",
    "BCI",
    "GLD",
    "GLDM",
    "IAU",
    "SLV",
    "SIVR",
    "GDX",
    "GDXJ",
    "USO",
    "BNO",
    "USL",
    "UNG",
    "UNL",
    "UGA",
    "CORN",
    "WEAT",
    "SOYB",
    "CANE",
    "CPER",
    "PICK",
    "COPX",
    "PALL",
    "PPLT",
    "SIL",
    "SILJ",
    "XOP",
    "OIH",
    "XME",
}

CURRENCY_SYMBOLS = {
    "UUP",
    "UDN",
    "FXA",
    "FXB",
    "FXC",
    "FXE",
    "FXY",
    "CEW",
}

VOLATILITY_SYMBOLS = {
    "VIXY",
    "VIXM",
    "VXX",
    "UVXY",
    "SVXY",
}

SECTOR_SYMBOLS = {
    "XLB",
    "XLC",
    "XLE",
    "XLF",
    "XLI",
    "XLK",
    "XLP",
    "XLRE",
    "XLU",
    "XLV",
    "XLY",
}


def infer_asset_class_from_symbol(symbol: Any) -> str:
    cleaned = _clean_symbol(symbol)

    if cleaned in BOND_SYMBOLS:
        return "bonds"
    if cleaned in CREDIT_SYMBOLS:
        return "credit"
    if cleaned in COMMODITY_SYMBOLS:
        return "commodities"
    if cleaned in CURRENCY_SYMBOLS:
        return "currencies"
    if cleaned in VOLATILITY_SYMBOLS:
        return "volatility"

    return "equities"


def resolve_benchmark_symbol(
    *,
    symbol: Any,
    asset_class: Any | None = None,
    explicit_benchmark_symbol: Any | None = None,
) -> str:
    """Resolve the default benchmark used for asset-behavior relative strength.

    The resolver is intentionally simple and deterministic. Callers may override
    it with an explicit benchmark symbol, while the builder can always emit a
    benchmark_symbol so downstream relative-strength logic does not need to guess.
    """

    explicit = _clean_symbol(explicit_benchmark_symbol)
    if explicit:
        return explicit

    cleaned = _clean_symbol(symbol)
    normalized_asset_class = _clean_text(asset_class) or infer_asset_class_from_symbol(cleaned)

    if normalized_asset_class == "bonds":
        return DURATION_BENCHMARK_SYMBOL if cleaned in DURATION_SYMBOLS else BOND_BENCHMARK_SYMBOL

    if normalized_asset_class == "credit":
        return HIGH_YIELD_BENCHMARK_SYMBOL if cleaned in HIGH_YIELD_SYMBOLS else CREDIT_BENCHMARK_SYMBOL

    if normalized_asset_class == "commodities":
        return COMMODITY_BENCHMARK_SYMBOL

    if normalized_asset_class == "currencies":
        return CURRENCY_BENCHMARK_SYMBOL

    if normalized_asset_class == "volatility":
        return VOLATILITY_BENCHMARK_SYMBOL

    if cleaned in SMALL_CAP_SYMBOLS:
        return SMALL_CAP_BENCHMARK_SYMBOL

    if cleaned in TECH_OR_GROWTH_SYMBOLS:
        return TECH_BENCHMARK_SYMBOL

    if cleaned in SECTOR_SYMBOLS:
        return DEFAULT_BENCHMARK_SYMBOL

    return DEFAULT_BENCHMARK_SYMBOL


def _clean_symbol(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().upper()


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()




