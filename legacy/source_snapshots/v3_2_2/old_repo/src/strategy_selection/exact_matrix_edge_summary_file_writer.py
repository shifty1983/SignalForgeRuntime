from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from src.signalforge.engines.strategy_selection.exact_matrix_edge_summary import (
    summarize_signalforge_exact_matrix_edge_summary,
)

EXACT_MATRIX_EDGE_SUMMARY_RESULT_FILENAME = "signalforge_exact_matrix_edge_summary.json"
EXACT_MATRIX_EDGE_SUMMARY_COMPACT_FILENAME = "signalforge_exact_matrix_edge_summary_summary.json"
EXACT_MATRIX_EDGE_CELLS_FILENAME = "signalforge_exact_matrix_edge_cells.json"


def write_exact_matrix_edge_summary_result(
    result: Mapping[str, Any], output_dir: str | Path
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    result_path = output_path / EXACT_MATRIX_EDGE_SUMMARY_RESULT_FILENAME
    summary_path = output_path / EXACT_MATRIX_EDGE_SUMMARY_COMPACT_FILENAME
    cells_path = output_path / EXACT_MATRIX_EDGE_CELLS_FILENAME

    result_path.write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    cells_path.write_text(
        json.dumps(result.get("exact_matrix_edge_cells") or [], indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    summary = summarize_signalforge_exact_matrix_edge_summary(result)
    summary.update(
        {
            "result_path": str(result_path),
            "summary_path": str(summary_path),
            "cells_path": str(cells_path),
            "output_dir": str(output_path),
        }
    )
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return summary
