from pathlib import Path
from typing import Any

import yaml


class UniverseManager:
    """
    Loads and manages tradable universes, watchlists, and benchmarks.
    """

    def __init__(self, config_path: str | Path = "config/universes.yaml") -> None:
        self.config_path = Path(config_path)
        self.config = self._load_config()

    def _load_config(self) -> dict[str, Any]:
        if not self.config_path.exists():
            raise FileNotFoundError(f"Universe config not found: {self.config_path}")

        with self.config_path.open("r", encoding="utf-8") as file:
            config = yaml.safe_load(file)

        if config is None:
            raise ValueError(f"Universe config is empty: {self.config_path}")

        return config

    @staticmethod
    def _extract_symbols(entry: Any) -> list[str]:
        """
        Supports both formats:

        Old format:
            sectors:
              - XLK
              - XLF

        Expanded format:
            sectors:
              description: Sector ETFs
              symbols:
                - XLK
                - XLF
        """
        if isinstance(entry, list):
            return entry

        if isinstance(entry, dict):
            symbols = entry.get("symbols", [])

            if not isinstance(symbols, list):
                raise TypeError("Universe symbols field must be a list")

            return symbols

        raise TypeError("Universe entry must be a list or dictionary")

    @staticmethod
    def _normalize_symbols(symbols: list[str]) -> list[str]:
        return sorted({symbol.upper().strip() for symbol in symbols if symbol})

    def list_universes(self) -> list[str]:
        return sorted(self.config.get("universes", {}).keys())

    def list_watchlists(self) -> list[str]:
        return sorted(self.config.get("watchlists", {}).keys())

    def list_benchmarks(self) -> list[str]:
        return sorted(self.config.get("benchmarks", {}).keys())

    def get_universe(self, name: str) -> list[str]:
        universes = self.config.get("universes", {})

        if name not in universes:
            raise KeyError(f"Universe not found: {name}")

        symbols = self._extract_symbols(universes[name])
        return self._normalize_symbols(symbols)

    def get_watchlist(self, name: str) -> list[str]:
        watchlists = self.config.get("watchlists", {})

        if name not in watchlists:
            raise KeyError(f"Watchlist not found: {name}")

        symbols = self._extract_symbols(watchlists[name])
        return self._normalize_symbols(symbols)

    def get_benchmark(self, name: str) -> str:
        benchmarks = self.config.get("benchmarks", {})

        if name not in benchmarks:
            raise KeyError(f"Benchmark not found: {name}")

        return benchmarks[name].upper().strip()

    def combine_universes(self, names: list[str]) -> list[str]:
        symbols: set[str] = set()

        for name in names:
            symbols.update(self.get_universe(name))

        return sorted(symbols)

    def combine_watchlists(self, names: list[str]) -> list[str]:
        symbols: set[str] = set()

        for name in names:
            symbols.update(self.get_watchlist(name))

        return sorted(symbols)

    def get_all_symbols(self) -> list[str]:
        symbols: set[str] = set()

        for universe_name in self.list_universes():
            symbols.update(self.get_universe(universe_name))

        for watchlist_name in self.list_watchlists():
            symbols.update(self.get_watchlist(watchlist_name))

        for benchmark in self.config.get("benchmarks", {}).values():
            symbols.add(benchmark.upper().strip())

        return sorted(symbols)

    def get_ingestion_symbols(self) -> list[str]:
        ingestion_universes = self.config.get("ingestion_universes", [])

        if not ingestion_universes:
            return self.get_all_symbols()

        return self.combine_universes(ingestion_universes)

    def get_audit_symbols(self) -> list[str]:
        audit_universes = self.config.get("audit_universes", [])

        if not audit_universes:
            return self.get_all_symbols()

        return self.combine_universes(audit_universes)

    def resolve_symbols(
        self,
        universes: list[str] | None = None,
        watchlists: list[str] | None = None,
        symbols: list[str] | None = None,
    ) -> list[str]:
        resolved: set[str] = set()

        if universes:
            for universe in universes:
                resolved.update(self.get_universe(universe))

        if watchlists:
            for watchlist in watchlists:
                resolved.update(self.get_watchlist(watchlist))

        if symbols:
            resolved.update(self._normalize_symbols(symbols))

        return sorted(resolved)

def load_universe(name: str, config_dir: str | Path = "config/universe") -> list[str]:
    """
    Compatibility helper for scripts that load a simple text-file universe.

    Supports:
    - config/universe/<name>
    - direct file paths
    - one symbol/series per line
    - blank lines and # comments
    """
    candidate = Path(name)

    if not candidate.exists():
        candidate = Path(config_dir) / name

    if not candidate.exists():
        manager = UniverseManager()
        try:
            return manager.get_universe(name)
        except KeyError:
            try:
                return manager.get_watchlist(name)
            except KeyError as error:
                raise FileNotFoundError(f"Universe not found: {name}") from error

    values: list[str] = []

    with candidate.open("r", encoding="utf-8") as file:
        for line in file:
            value = line.strip()
            if not value or value.startswith("#"):
                continue
            values.append(value.upper())

    return sorted(set(values))
