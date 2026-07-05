from pathlib import Path
import json

path = Path("config/options_execution/base_strategy_execution_map_v1.json")
config = json.loads(path.read_text(encoding="utf-8-sig"))

required = [
    "long_call",
    "long_put",
    "bull_call_debit_spread",
    "bear_put_debit_spread",
    "put_credit_spread",
    "call_credit_spread",
    "iron_condor",
    "iron_butterfly",
    "calendar_spread",
    "diagonal_spread",
]

actual = [row.get("strategy") for row in config.get("strategies", [])]

summary = {
    "adapter_type": "strategy_execution_map_system_name_coverage_auditor",
    "artifact_type": "signalforge_strategy_execution_map_system_name_coverage",
    "is_ready": set(required).issubset(set(actual)),
    "required_count": len(required),
    "actual_count": len(actual),
    "missing": [x for x in required if x not in actual],
    "extra": [x for x in actual if x not in required],
    "required": required,
    "actual": actual,
}

print(json.dumps(summary, indent=2))
raise SystemExit(0 if summary["is_ready"] else 1)
