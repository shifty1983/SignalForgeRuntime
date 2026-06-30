from __future__ import annotations

from pathlib import Path

from signalforge.migration.legacy_source_graph import build_migration_source_graph


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_migration_source_graph_finds_transitive_internal_dependencies(tmp_path: Path):
    source_root = tmp_path / "src"

    write(
        source_root / "backtesting" / "historical_decision_rows.py",
        "import json\nfrom backtesting import helper\nfrom options.schema import OptionRow\n\ndef build():\n    return helper.value()\n",
    )
    write(
        source_root / "backtesting" / "helper.py",
        "from .nested import value\n",
    )
    write(
        source_root / "backtesting" / "nested.py",
        "def value():\n    return 1\n",
    )
    write(
        source_root / "options" / "schema.py",
        "class OptionRow:\n    pass\n",
    )

    graph = build_migration_source_graph(
        source_root=source_root,
        targets=["backtesting/historical_decision_rows.py"],
    )

    summary = graph["summary"]
    paths = {node["relative_path"] for node in graph["nodes"]}

    assert summary["node_count"] == 4
    assert summary["missing_internal_dependency_count"] == 0
    assert "backtesting/historical_decision_rows.py" in paths
    assert "backtesting/helper.py" in paths
    assert "backtesting/nested.py" in paths
    assert "options/schema.py" in paths


def test_migration_source_graph_reports_missing_internal_dependencies(tmp_path: Path):
    source_root = tmp_path / "src"

    write(
        source_root / "backtesting" / "historical_decision_rows.py",
        "from strategy_selection.missing_module import build\n",
    )

    graph = build_migration_source_graph(
        source_root=source_root,
        targets=["backtesting/historical_decision_rows.py"],
    )

    summary = graph["summary"]

    assert not summary["is_ready"]
    assert summary["missing_internal_dependency_count"] == 1
    assert "missing_internal_dependencies" in summary["blockers"]

