
from __future__ import annotations
import json, math
from argparse import Namespace
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, Iterable, List, Optional, Tuple

def _read_jsonl(path: Path):
    with path.open('r', encoding='utf-8-sig', errors='ignore') as f:
        for line in f:
            line=line.strip()
            if line: yield json.loads(line)

def _write_jsonl(path: Path, rows):
    n=0
    with path.open('w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True, separators=(',',':'))+'\n'); n+=1
    return n

def _first(row, names, default=None):
    for n in names:
        if n in row and row.get(n) not in (None,''): return row.get(n)
    low={str(k).lower():v for k,v in row.items()}
    for n in names:
        k=str(n).lower()
        if k in low and low[k] not in (None,''): return low[k]
    return default

def _to_float(v, default=None):
    if v is None: return default
    try:
        s=str(v).strip()
        if not s or s.lower() in {'none','null','nan'}: return default
        x=float(s)
        return default if math.isnan(x) else x
    except Exception: return default

def _date(v):
    if v is None: return None
    s=str(v).strip()
    return s[:10] if s else None

def _dt(v):
    d=_date(v)
    if not d: return None
    try: return datetime.strptime(d, '%Y-%m-%d')
    except Exception: return None

def _days(a,b):
    x=_dt(a); y=_dt(b)
    return None if x is None or y is None else (y-x).days

def _trade_id(row):
    v=_first(row,['trade_id','selected_trade_id','portfolio_trade_id','position_id','request_id','candidate_id'])
    return str(v) if v not in (None,'') else None

def _leg_index(row):
    return str(_first(row,['leg_index','selected_leg_index','strategy_leg_index','leg_id','leg_sequence','index'], '0'))

def _contract(row):
    v=_first(row,['contract_symbol','option_symbol','canonical_contract_symbol','leg_contract_symbol','selected_contract_symbol'])
    return str(v) if v not in (None,'') else None

def _strategy(row):
    v=_first(row,['selected_strategy','strategy','strategy_name','strategy_family'])
    return str(v) if v not in (None,'') else None

def _symbol(row):
    v=_first(row,['selected_symbol','symbol','underlying','underlying_symbol'])
    return str(v) if v not in (None,'') else None

def _infer_side(row):
    n=_to_float(_first(row,['side_sign','position_sign','leg_sign','signed_quantity','signed_contract_quantity']))
    if n is not None and n != 0: return 1 if n>0 else -1
    vals=[]
    for f in ['side','leg_side','position_side','entry_side','entry_action','action','order_action','open_action','leg_action','instruction','position','leg_position','leg_role','role']:
        if row.get(f) not in (None,''): vals.append(str(row.get(f)).lower())
    c=' '.join(vals).replace('_','').replace('-','').replace(' ','')
    for t in ['short','selltoopen','sellopen','sto','sell','creditleg','shortcall','shortput','written','write']:
        if t in c: return -1
    for t in ['long','buytoopen','buyopen','bto','buy','debitleg','longcall','longput','purchased']:
        if t in c: return 1
    return None

def _qty(row):
    q=_to_float(_first(row,['leg_quantity','quantity','contract_quantity','contracts','ratio','leg_ratio','abs_quantity'],1),1.0)
    return abs(q or 1.0)

def _entry_price(row, side, mode):
    explicit=_to_float(_first(row,['entry_fill_price','entry_price','selected_entry_price','open_price','fill_price']))
    if explicit is not None and explicit>=0 and mode=='manifest_first': return explicit
    bid=_to_float(_first(row,['entry_bid','selected_entry_bid','bid_at_entry','bid']))
    ask=_to_float(_first(row,['entry_ask','selected_entry_ask','ask_at_entry','ask']))
    mid=_to_float(_first(row,['entry_mid','entry_mid_price','selected_entry_mid','mid_at_entry','mid','mid_price']))
    if mode=='mid':
        if mid is not None: return mid
        if bid is not None and ask is not None: return (bid+ask)/2
    if side>0 and ask is not None: return ask
    if side<0 and bid is not None: return bid
    if explicit is not None and explicit>=0: return explicit
    if mid is not None: return mid
    if bid is not None and ask is not None: return (bid+ask)/2
    return None

def _quote_prices(row):
    bid=_to_float(_first(row,['bid','bid_close','bidclose','quote_bid']))
    ask=_to_float(_first(row,['ask','ask_close','askclose','quote_ask']))
    mid=_to_float(_first(row,['mid','mid_price','close','mark','quote_mid']))
    if mid is None and bid is not None and ask is not None: mid=(bid+ask)/2
    return bid,ask,mid

def _close_price(row, side, mode):
    bid,ask,mid=_quote_prices(row)
    if mode=='mid': return mid
    if side>0: return bid if bid is not None else mid
    return ask if ask is not None else mid

def _path_state(row): return str(_first(row,['path_state','quote_path_state','state'],'unknown'))
def _quote_date(row): return _date(_first(row,['quote_date','date','time']))
def _expiration(row): return _date(_first(row,['expiration','expiry','option_expiration','expiry_date']))

def _load_manifest(path, entry_price_mode):
    trades={}; bad=[]
    for row in _read_jsonl(path):
        tid=_trade_id(row)
        if not tid:
            bad.append({'reason':'missing_trade_id','row':row}); continue
        if tid not in trades:
            trades[tid]={'trade_id':tid,'selected_strategy':_strategy(row),'selected_symbol':_symbol(row),'entry_date':_date(_first(row,['entry_date','selected_entry_date','entry_quote_date','open_date','portfolio_entry_date'])),'original_exit_date':_date(_first(row,['exit_date','selected_exit_date','exit_quote_date','portfolio_realization_date','outcome_availability_date','original_exit_date'])),'legs':{},'source_examples':[]}
        t=trades[tid]
        t['selected_strategy']=t.get('selected_strategy') or _strategy(row)
        t['selected_symbol']=t.get('selected_symbol') or _symbol(row)
        t['entry_date']=t.get('entry_date') or _date(_first(row,['entry_date','selected_entry_date','entry_quote_date','open_date','portfolio_entry_date']))
        t['original_exit_date']=t.get('original_exit_date') or _date(_first(row,['exit_date','selected_exit_date','exit_quote_date','portfolio_realization_date','outcome_availability_date','original_exit_date']))
        leg=_leg_index(row); side=_infer_side(row); contract=_contract(row)
        if side is None:
            bad.append({'reason':'missing_or_unparseable_side','trade_id':tid,'leg_index':leg,'contract_symbol':contract,'available_keys':sorted(row.keys()),'row_sample':row})
            side=0
        ep=_entry_price(row, side if side else 1, entry_price_mode) if side else None
        t['legs'][leg]={'trade_id':tid,'leg_index':leg,'contract_symbol':contract,'side':side,'quantity':_qty(row),'entry_price':ep,'expiration':_expiration(row),'manifest_row':row}
        if len(t['source_examples'])<2: t['source_examples'].append(row)
    return trades,bad

def _load_trade_states(path):
    states={}
    if path is None or not Path(path).exists(): return states
    for row in _read_jsonl(Path(path)):
        tid=_trade_id(row)
        if tid: states[tid]=str(_first(row,['path_state','trade_path_state','state'],'unknown'))
    return states

def _load_path_rows(path):
    g=defaultdict(lambda: defaultdict(list))
    for row in _read_jsonl(path):
        tid=_trade_id(row); qd=_quote_date(row)
        if tid and qd: g[tid][qd].append(row)
    return g

def _select_leg(row, trade):
    lk=_leg_index(row)
    if lk in trade['legs']: return trade['legs'][lk]
    c=_contract(row)
    if c:
        m=[x for x in trade['legs'].values() if x.get('contract_symbol')==c]
        if len(m)==1: return m[0]
    if len(trade['legs'])==1: return next(iter(trade['legs'].values()))
    return None

def _min_exp(trade):
    vals=[x.get('expiration') for x in trade['legs'].values() if x.get('expiration')]
    return min(vals) if vals else None

def _marks(trade, by_date, mult, mode):
    warns=[]; legs=trade['legs']; leg_count=len(legs)
    if not legs: return [], ['missing_manifest_legs']
    if any(x.get('side') not in (-1,1) for x in legs.values()): return [], ['missing_or_unparseable_leg_side']
    if any(x.get('entry_price') is None for x in legs.values()): return [], ['missing_entry_price']
    open_cf=0.0; gross=0.0
    for leg in legs.values():
        cf=-int(leg['side'])*float(leg['entry_price'])*float(leg['quantity'])*mult
        open_cf+=cf; gross+=abs(cf)
    denom=abs(open_cf) if abs(open_cf)>1e-9 else gross
    exp=_min_exp(trade); out=[]
    for qd in sorted(by_date.keys()):
        close_cf=0.0; used=set(); states=[]; sources=[]
        for row in by_date[qd]:
            leg=_select_leg(row, trade)
            if leg is None:
                warns.append(f'unmatched_path_leg_on_{qd}'); continue
            lid=str(leg['leg_index'])
            if lid in used: continue
            states.append(_path_state(row)); sources.append(str(_first(row,['quote_source'],'unknown')))
            if _path_state(row)!='complete': continue
            px=_close_price(row, int(leg['side']), mode)
            if px is None: continue
            close_cf += int(leg['side'])*float(px)*float(leg['quantity'])*mult
            used.add(lid)
        if len(used)!=leg_count:
            warns.append(f'not_all_legs_markable_on_{qd}'); continue
        pnl=open_cf+close_cf; ret=pnl/denom if denom and denom>0 else None
        out.append({'adapter_type':'baseline_exit_overlay_daily_trade_mark','artifact_type':'signalforge_baseline_exit_overlay_daily_trade_mark','contract':'baseline_exit_overlay_daily_trade_mark','trade_id':trade['trade_id'],'selected_symbol':trade.get('selected_symbol'),'selected_strategy':trade.get('selected_strategy'),'quote_date':qd,'entry_date':trade.get('entry_date'),'original_exit_date':trade.get('original_exit_date'),'min_expiration':exp,'dte':_days(qd,exp) if exp else None,'open_cashflow':open_cf,'gross_entry_cash':gross,'return_denominator':denom,'close_cashflow':close_cf,'pnl':pnl,'return_on_entry_cash':ret,'leg_count':leg_count,'path_row_state_counts':dict(Counter(states)),'quote_source_counts':dict(Counter(sources)),'does_select_strategy':False,'does_feed_exit_result_to_expectancy':False,'does_change_position_size':False})
    return out,warns

def _pick(marks, trade, args):
    if not marks: return None,'no_markable_path'
    entry=trade.get('entry_date'); orig=trade.get('original_exit_date')
    target=args.profit_target_return
    stop=args.loss_stop_return
    if stop is not None and stop>0: stop=-stop
    fallback=None
    if orig:
        exact=[m for m in marks if m['quote_date']==orig]
        prior=[m for m in marks if m['quote_date']<=orig]
        fallback=(exact[-1] if exact else (prior[-1] if prior else None))
    fallback=fallback or marks[-1]
    for m in marks:
        qd=m['quote_date']
        if args.ignore_entry_date_triggers and entry and qd<=entry: continue
        ret=m.get('return_on_entry_cash'); held=_days(entry,qd); dte=m.get('dte')
        if stop is not None and ret is not None and ret<=stop: return m,'loss_stop'
        if target is not None and ret is not None and ret>=target: return m,'profit_target'
        if args.max_holding_days is not None and held is not None and held>=args.max_holding_days: return m,'max_holding_days'
        if args.close_dte_less_equal is not None and dte is not None and dte<=args.close_dte_less_equal: return m,'dte_exit'
    return fallback,'original_exit'

def _stat(vals, kind):
    x=[float(v) for v in vals if v is not None and not math.isnan(float(v))]
    if not x: return None
    return {'sum':sum,'mean':mean,'median':median,'min':min,'max':max}[kind](x)

def build_exit_overlay_evaluation(daily_quote_path_rows:Path, trade_leg_manifest:Path, output_dir:Path, trade_summaries:Optional[Path]=None, scenario_name='close_on_original_exit_only', profit_target_return=None, loss_stop_return=None, max_holding_days=None, close_dte_less_equal=None, allow_partial_trades=False, mark_price_mode='closeable', entry_price_mode='manifest_first', contract_multiplier=100.0, ignore_entry_date_triggers=True, write_daily_marks=True):
    output_dir.mkdir(parents=True, exist_ok=True)
    args=Namespace(profit_target_return=profit_target_return,loss_stop_return=loss_stop_return,max_holding_days=max_holding_days,close_dte_less_equal=close_dte_less_equal,ignore_entry_date_triggers=ignore_entry_date_triggers)
    trades,bad=_load_manifest(Path(trade_leg_manifest), entry_price_mode)
    paths=_load_path_rows(Path(daily_quote_path_rows))
    states=_load_trade_states(trade_summaries)
    outcomes=[]; skips=[]; allmarks=[]; exit_counts=Counter(); state_counts=Counter(); skip_counts=Counter(); strat_counts=Counter(); sym_counts=Counter()
    for tid in sorted(trades):
        tr=trades[tid]; st=states.get(tid,'unknown')
        if st not in {'complete','unknown'} and not allow_partial_trades:
            sk={'adapter_type':'baseline_exit_overlay_rule_evaluation_skipped_trade','artifact_type':'signalforge_baseline_exit_overlay_rule_evaluation_skipped_trade','contract':'baseline_exit_overlay_rule_evaluation_skipped_trade','trade_id':tid,'selected_symbol':tr.get('selected_symbol'),'selected_strategy':tr.get('selected_strategy'),'skip_reason':'path_not_complete','path_state':st,'does_select_strategy':False,'does_feed_exit_result_to_expectancy':False,'does_change_position_size':False}
            skips.append(sk); skip_counts[sk['skip_reason']]+=1; state_counts['skipped_path_not_complete']+=1; continue
        marks,warns=_marks(tr, paths.get(tid,{}), contract_multiplier, mark_price_mode)
        if write_daily_marks: allmarks.extend(marks)
        m,reason=_pick(marks,tr,args)
        if m is None:
            sk={'adapter_type':'baseline_exit_overlay_rule_evaluation_skipped_trade','artifact_type':'signalforge_baseline_exit_overlay_rule_evaluation_skipped_trade','contract':'baseline_exit_overlay_rule_evaluation_skipped_trade','trade_id':tid,'selected_symbol':tr.get('selected_symbol'),'selected_strategy':tr.get('selected_strategy'),'skip_reason':reason,'path_state':st,'warnings':warns[:25],'does_select_strategy':False,'does_feed_exit_result_to_expectancy':False,'does_change_position_size':False}
            skips.append(sk); skip_counts[reason]+=1; state_counts['skipped_no_markable_path']+=1; continue
        orig=tr.get('original_exit_date')
        exact=[x for x in marks if orig and x['quote_date']==orig]
        prior=[x for x in marks if (not orig or x['quote_date']<=orig)]
        bm=exact[-1] if exact else (prior[-1] if prior else marks[-1])
        rets=[x.get('return_on_entry_cash') for x in marks if x.get('return_on_entry_cash') is not None]
        pnls=[x.get('pnl') for x in marks if x.get('pnl') is not None]
        mp=m.get('pnl'); bp=bm.get('pnl'); mr=m.get('return_on_entry_cash'); br=bm.get('return_on_entry_cash')
        o={'adapter_type':'baseline_exit_overlay_rule_evaluator','artifact_type':'signalforge_baseline_exit_overlay_rule_evaluation_trade_outcome','contract':'baseline_exit_overlay_rule_evaluation_trade_outcome','scenario_name':scenario_name,'trade_id':tid,'selected_symbol':tr.get('selected_symbol'),'selected_strategy':tr.get('selected_strategy'),'entry_date':tr.get('entry_date'),'managed_exit_date':m.get('quote_date'),'original_exit_date':orig,'exit_reason':reason,'exit_overlay_state':'evaluated','path_state':st,'path_trade_mark_count':len(marks),'leg_count':len(tr['legs']),'days_held_managed':_days(tr.get('entry_date'),m.get('quote_date')),'days_held_original':_days(tr.get('entry_date'),orig),'open_cashflow':m.get('open_cashflow'),'gross_entry_cash':m.get('gross_entry_cash'),'return_denominator':m.get('return_denominator'),'managed_close_cashflow':m.get('close_cashflow'),'managed_pnl':mp,'managed_return_on_entry_cash':mr,'original_exit_close_cashflow':bm.get('close_cashflow'),'original_exit_pnl':bp,'original_exit_return_on_entry_cash':br,'delta_pnl_vs_original_exit':mp-bp if mp is not None and bp is not None else None,'delta_return_vs_original_exit':mr-br if mr is not None and br is not None else None,'mae_return_on_entry_cash':_stat(rets,'min'),'mfe_return_on_entry_cash':_stat(rets,'max'),'mae_pnl':_stat(pnls,'min'),'mfe_pnl':_stat(pnls,'max'),'exit_rule_parameters':{'profit_target_return':profit_target_return,'loss_stop_return':loss_stop_return,'max_holding_days':max_holding_days,'close_dte_less_equal':close_dte_less_equal,'allow_partial_trades':allow_partial_trades,'mark_price_mode':mark_price_mode,'entry_price_mode':entry_price_mode,'contract_multiplier':contract_multiplier,'ignore_entry_date_triggers':ignore_entry_date_triggers},'warnings':warns[:25],'does_select_strategy':False,'does_feed_exit_result_to_expectancy':False,'does_change_position_size':False,'does_apply_position_sizing':False}
        outcomes.append(o); exit_counts[reason]+=1; state_counts['evaluated']+=1; strat_counts[str(tr.get('selected_strategy') or 'unknown')]+=1; sym_counts[str(tr.get('selected_symbol') or 'unknown')]+=1
    op=output_dir/'baseline_exit_overlay_rule_evaluation_trade_outcomes.jsonl'; sp=output_dir/'baseline_exit_overlay_rule_evaluation_skipped_trades.jsonl'; mpth=output_dir/'baseline_exit_overlay_rule_evaluation_daily_trade_marks.jsonl'; bp=output_dir/'baseline_exit_overlay_rule_evaluation_bad_manifest_legs.jsonl'; sump=output_dir/'baseline_exit_overlay_rule_evaluation_summary.json'
    oc=_write_jsonl(op,outcomes); sc=_write_jsonl(sp,skips); bc=_write_jsonl(bp,bad); mc=_write_jsonl(mpth,allmarks) if write_daily_marks else 0
    vals=lambda k:[r.get(k) for r in outcomes if r.get(k) is not None]
    def block(v): return {'sum':_stat(v,'sum'),'mean':_stat(v,'mean'),'median':_stat(v,'median'),'min':_stat(v,'min'),'max':_stat(v,'max')}
    warnings=[]
    if bc: warnings.append({'warning_type':'bad_manifest_legs_present','bad_manifest_leg_count':bc,'path':str(bp)})
    if sc: warnings.append({'warning_type':'skipped_trades_present','skipped_trade_count':sc,'path':str(sp)})
    blockers=[]
    if oc==0: blockers.append({'blocker_type':'no_evaluated_trades','message':'No trades were evaluable from supplied manifest/path rows.'})
    summary={'adapter_type':'baseline_exit_overlay_rule_evaluator','artifact_type':'signalforge_baseline_exit_overlay_rule_evaluation','contract':'baseline_exit_overlay_rule_evaluation','scenario_name':scenario_name,'is_ready':len(blockers)==0,'readiness_state':'ready' if not blockers else 'blocked','blocker_count':len(blockers),'blockers':blockers,'warning_count':len(warnings),'warnings':warnings,'input_trade_count':len(trades),'evaluated_trade_count':oc,'skipped_trade_count':sc,'bad_manifest_leg_count':bc,'daily_trade_mark_count':mc,'exit_reason_counts':dict(exit_counts),'state_counts':dict(state_counts),'skip_reason_counts':dict(skip_counts),'top_strategy_counts':dict(strat_counts.most_common(25)),'top_symbol_counts':dict(sym_counts.most_common(25)),'managed_return_on_entry_cash':block(vals('managed_return_on_entry_cash')),'original_exit_return_on_entry_cash':block(vals('original_exit_return_on_entry_cash')),'delta_return_vs_original_exit':block(vals('delta_return_vs_original_exit')),'managed_pnl_per_1x_leg_ratio':block(vals('managed_pnl')),'original_exit_pnl_per_1x_leg_ratio':block(vals('original_exit_pnl')),'delta_pnl_vs_original_exit_per_1x_leg_ratio':block(vals('delta_pnl_vs_original_exit')),'policy':{'does_select_strategy':False,'does_feed_exit_result_to_expectancy':False,'does_change_position_size':False,'does_apply_position_sizing':False,'uses_locked_selected_trades_only':True,'uses_daily_quote_path':True,'uses_quote_native_close_prices':mark_price_mode in {'closeable','conservative'},'does_forward_fill':False,'does_invent_prices':False,'partial_trade_handling':'excluded' if not allow_partial_trades else 'allowed_if_markable'},'paths':{'trade_outcomes_path':str(op),'skipped_trades_path':str(sp),'daily_trade_marks_path':str(mpth) if write_daily_marks else None,'bad_manifest_legs_path':str(bp),'summary_path':str(sump)},'parameters':{'profit_target_return':profit_target_return,'loss_stop_return':loss_stop_return,'max_holding_days':max_holding_days,'close_dte_less_equal':close_dte_less_equal,'allow_partial_trades':allow_partial_trades,'mark_price_mode':mark_price_mode,'entry_price_mode':entry_price_mode,'contract_multiplier':contract_multiplier,'ignore_entry_date_triggers':ignore_entry_date_triggers}}
    sump.write_text(json.dumps(summary, indent=2, sort_keys=True)+'\n', encoding='utf-8')
    return summary
