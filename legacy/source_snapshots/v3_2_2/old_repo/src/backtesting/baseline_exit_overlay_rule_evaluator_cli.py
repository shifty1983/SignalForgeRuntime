
from __future__ import annotations
import argparse, json
from pathlib import Path
from .baseline_exit_overlay_rule_evaluator import build_exit_overlay_evaluation

def _of(v): return None if v is None or str(v).strip()=='' else float(v)
def _oi(v): return None if v is None or str(v).strip()=='' else int(v)

def main():
    p=argparse.ArgumentParser(description='Evaluate managed exit rules on locked baseline/search daily quote paths without changing strategy selection, expectancy, or sizing.')
    p.add_argument('--daily-quote-path-rows', required=True, type=Path)
    p.add_argument('--trade-leg-manifest', required=True, type=Path)
    p.add_argument('--trade-summaries', type=Path, default=None)
    p.add_argument('--output-dir', required=True, type=Path)
    p.add_argument('--scenario-name', default='close_on_original_exit_only')
    p.add_argument('--profit-target-return', type=_of, default=None)
    p.add_argument('--loss-stop-return', type=_of, default=None)
    p.add_argument('--max-holding-days', type=_oi, default=None)
    p.add_argument('--close-dte-less-equal', type=_oi, default=None)
    p.add_argument('--mark-price-mode', choices=['closeable','mid','conservative'], default='closeable')
    p.add_argument('--entry-price-mode', choices=['manifest_first','quote_native','mid'], default='manifest_first')
    p.add_argument('--contract-multiplier', type=float, default=100.0)
    p.add_argument('--allow-partial-trades', action='store_true')
    p.add_argument('--include-entry-date-triggers', action='store_true')
    p.add_argument('--no-daily-marks', action='store_true')
    a=p.parse_args()
    s=build_exit_overlay_evaluation(daily_quote_path_rows=a.daily_quote_path_rows, trade_leg_manifest=a.trade_leg_manifest, trade_summaries=a.trade_summaries, output_dir=a.output_dir, scenario_name=a.scenario_name, profit_target_return=a.profit_target_return, loss_stop_return=a.loss_stop_return, max_holding_days=a.max_holding_days, close_dte_less_equal=a.close_dte_less_equal, allow_partial_trades=a.allow_partial_trades, mark_price_mode=a.mark_price_mode, entry_price_mode=a.entry_price_mode, contract_multiplier=a.contract_multiplier, ignore_entry_date_triggers=not a.include_entry_date_triggers, write_daily_marks=not a.no_daily_marks)
    print(json.dumps(s, indent=2, sort_keys=True))
    return 0 if s.get('is_ready') else 1
if __name__ == '__main__':
    raise SystemExit(main())
