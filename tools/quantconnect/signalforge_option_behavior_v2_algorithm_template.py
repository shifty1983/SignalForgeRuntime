from AlgorithmImports import *
from datetime import datetime, timedelta
import base64
import gzip
import hashlib
import json
import math
import traceback


BATCH_ID = "__BATCH_ID__"
BATCH_PAYLOAD_B64 = "__BATCH_PAYLOAD_B64__"

OBJECT_STORE_ROOT = "signalforge_qc_option_behavior_v2_20210601_20260531"
ROWS_PER_PART = 500


class SignalForgeCanonicalOptionQuoteBackfill(QCAlgorithm):

    def Initialize(self):
        self.rows = []
        self.error_rows = []

        try:
            batch = self._decode_batch(BATCH_PAYLOAD_B64)
            if bool(batch.get("clear_object_store_on_start")):
                clear_result = self._clear_entire_object_store()
                self.SetRuntimeStatistic("SignalForgeObjectStoreFullClearDeleted", str(clear_result.get("deleted", 0)))
                self.SetRuntimeStatistic("SignalForgeObjectStoreFullClearFailed", str(clear_result.get("failed", 0)))
                self.SetRuntimeStatistic("SignalForgeObjectStoreFullClearSkipped", str(clear_result.get("skipped", False)))



            # In backtests, History can only see data at or before algorithm time.
            # Anchor the algorithm after the latest requested quote date.
            anchor = self._batch_anchor_date(batch)
            end = anchor + timedelta(days=1)

            self.SetStartDate(anchor.year, anchor.month, anchor.day)
            self.SetEndDate(end.year, end.month, end.day)
            self.SetCash(100000)

            self.SetRuntimeStatistic("SignalForgeBackfillState", "started")
            self.SetRuntimeStatistic("SignalForgeBackfillBatchId", BATCH_ID)
            self.SetRuntimeStatistic("SignalForgeBackfillAnchorDate", anchor.strftime("%Y-%m-%d"))

            self._run_batch(batch)
            self._write_object_store_outputs(batch)
            self.Debug("SignalForge canonical option quote backfill completed: " + BATCH_ID)

        except Exception as exc:
            self.SetRuntimeStatistic("SignalForgeBackfillState", "failed_before_or_during_write_failure")
            self.SetRuntimeStatistic("SignalForgeBackfillBatchId", BATCH_ID)
            self.SetRuntimeStatistic("SignalForgeBackfillErrorMessage", str(exc)[:3500])
            self.SetRuntimeStatistic("SignalForgeBackfillStacktraceHead", traceback.format_exc()[:3500])
            self._write_failure(str(exc), traceback.format_exc())
            self.Debug("SignalForge canonical option quote backfill failed: " + str(exc))

        self.Quit()


    def _batch_anchor_date(self, batch):
        dates = []

        for req in batch.get("requests", []):
            value = str(req.get("quote_date") or "")[:10]
            try:
                dates.append(datetime.strptime(value, "%Y-%m-%d"))
            except Exception:
                pass

        if not dates:
            return datetime(2026, 6, 15)

        latest = max(dates)

        # Move safely after the requested quote window.
        return latest + timedelta(days=10)
    def _decode_batch(self, payload_b64):
        raw = gzip.decompress(base64.b64decode(payload_b64.encode("ascii"))).decode("utf-8")
        value = json.loads(raw)

        if value.get("batch_id") != BATCH_ID:
            raise ValueError("Batch id mismatch. expected=" + BATCH_ID + " actual=" + str(value.get("batch_id")))

        return value

    def _run_batch(self, batch):
        requests = batch.get("requests", [])

        for req in requests:
            self._run_request(req)

    def _run_request(self, req):
        symbol = str(req.get("symbol") or "").upper()
        quote_date = str(req.get("quote_date") or "")[:10]
        contracts = req.get("contracts") or []

        if not symbol or not quote_date:
            for c in contracts:
                self.rows.append(self._missing_row(req, c, "bad_request_identity"))
            return

        try:
            dt = datetime.strptime(quote_date, "%Y-%m-%d")
        except Exception:
            for c in contracts:
                self.rows.append(self._missing_row(req, c, "bad_quote_date"))
            return

        try:
            # Add the underlying so LEAN has the canonical equity context.
            underlying_security = self.AddEquity(symbol, Resolution.Minute)
            underlying_symbol = underlying_security.Symbol

            for wanted in contracts:
                try:
                    contract_symbol = self._make_contract_symbol(underlying_symbol, wanted)
                    wanted["diagnostic_contract_symbol"] = str(contract_symbol)
                    quote_bar = self._last_quote_bar(contract_symbol, dt)

                    if quote_bar is None:
                        self.rows.append(self._missing_row(req, wanted, "contract_quote_history_empty"))
                        continue

                    row = self._quote_row_from_quote_bar(req, wanted, contract_symbol, quote_bar)

                    if row.get("bid") is None or row.get("ask") is None or row.get("mid") is None:
                        row["quote_resolution_state"] = "quote_values_missing"

                    self.rows.append(row)

                except Exception as contract_exc:
                    self.rows.append(
                        self._missing_row(
                            req,
                            wanted,
                            "contract_history_error",
                            traceback.format_exc()
                        )
                    )

        except Exception as exc:
            err = traceback.format_exc()
            for c in contracts:
                self.rows.append(self._missing_row(req, c, "error", err))

    def _make_contract_symbol(self, underlying_symbol, wanted):
        expiration = datetime.strptime(str(wanted.get("expiration") or "")[:10], "%Y-%m-%d")
        strike = float(wanted.get("strike"))
        right_text = self._normalize_right(wanted.get("option_right"))
        right = OptionRight.Call if right_text == "call" else OptionRight.Put

        return Symbol.CreateOption(
            underlying_symbol,
            Market.USA,
            OptionStyle.American,
            right,
            strike,
            expiration
        )

    def _last_quote_bar(self, contract_symbol, quote_dt):
        start = quote_dt
        end = quote_dt + timedelta(days=1)

        try:
            self.AddOptionContract(contract_symbol, Resolution.Minute)
        except Exception:
            pass

        candidates = []

        try:
            history = self.History[QuoteBar](contract_symbol, start, end, Resolution.Minute)
            for bar in history:
                candidates.append(bar)
        except Exception:
            pass

        if candidates:
            return self._choose_best_quote_bar(candidates)

        try:
            history = self.History(contract_symbol, start, end, Resolution.Minute)

            if hasattr(history, "empty"):
                if history.empty:
                    return None
                return self._quote_bar_proxy_from_dataframe(history)

            iterable_candidates = []
            for item in history:
                iterable_candidates.append(item)

            if iterable_candidates:
                return self._choose_best_quote_bar(iterable_candidates)

        except Exception:
            return None

        return None

    def _choose_best_quote_bar(self, bars):
        best = None
        best_score = None

        for bar in bars:
            score = self._quote_bar_quality_score(bar)
            if best is None or score > best_score:
                best = bar
                best_score = score

        return best


    def _bar_component_price(self, component):
        if component is None:
            return None

        for attr in ["Close", "Value", "Price", "Open", "High", "Low"]:
            value = self._safe_float(getattr(component, attr, None))
            if value is not None:
                return value

        return self._safe_float(component)

    def _bar_bid_ask_mid(self, quote_bar):
        if quote_bar is None:
            return None, None, None

        bid = None
        ask = None
        mid = None

        # QuantConnect QuoteBar usually has Bid/Ask bar components.
        bid = self._bar_component_price(getattr(quote_bar, "Bid", None))
        ask = self._bar_component_price(getattr(quote_bar, "Ask", None))

        # Fallbacks for proxy/simple objects.
        if bid is None:
            for attr in ["BidPrice", "bid", "Bid", "Close"]:
                bid = self._safe_float(getattr(quote_bar, attr, None))
                if bid is not None:
                    break

        if ask is None:
            for attr in ["AskPrice", "ask", "Ask", "Close"]:
                ask = self._safe_float(getattr(quote_bar, attr, None))
                if ask is not None:
                    break

        if bid is not None and ask is not None:
            mid = (bid + ask) / 2.0
        else:
            for attr in ["Mid", "mid", "Price", "Value", "Close"]:
                mid = self._safe_float(getattr(quote_bar, attr, None))
                if mid is not None:
                    break

        return bid, ask, mid

    def _quote_bar_quality_score(self, quote_bar):
        bid, ask, mid = self._bar_bid_ask_mid(quote_bar)

        has_bid = bid is not None and bid > 0
        has_ask = ask is not None and ask > 0
        has_mid = mid is not None and mid > 0

        spread_score = 0
        try:
            if has_bid and has_ask and ask >= bid:
                spread_score = -float(ask - bid)
        except Exception:
            spread_score = 0

        # Tuple ordering:
        # 1. prefer full bid/ask/mid
        # 2. then any bid/ask pair
        # 3. then any mid
        # 4. then narrower spread
        return (
            1 if has_bid and has_ask and has_mid else 0,
            1 if has_bid and has_ask else 0,
            1 if has_mid else 0,
            spread_score,
        )

    def _quote_bar_proxy_from_dataframe(self, df):
        best = None
        best_score = None

        try:
            iterator = df.iterrows()
        except Exception:
            return None

        for _, row in iterator:
            proxy = self._quote_bar_proxy_from_row(row)
            score = self._quote_bar_quality_score(proxy)

            if best is None or score > best_score:
                best = proxy
                best_score = score

        return best


    def _is_missing_row_value(self, value):
        if value is None:
            return True

        try:
            if value != value:
                return True
        except Exception:
            pass

        if isinstance(value, str) and value.strip() == "":
            return True

        return False

    def _first_row_value(self, row, names):
        if row is None:
            return None

        # Exact lookup first.
        for name in names:
            try:
                if hasattr(row, "get"):
                    value = row.get(name)
                else:
                    value = row[name]

                if not self._is_missing_row_value(value):
                    return value
            except Exception:
                pass

        # Case/format-insensitive lookup for pandas Series / dict-like rows.
        try:
            keys = list(row.index)
        except Exception:
            try:
                keys = list(row.keys())
            except Exception:
                keys = []

        lookup = {}
        for key in keys:
            norm = str(key).strip().lower().replace("_", "").replace(" ", "")
            lookup[norm] = key

        for name in names:
            norm_name = str(name).strip().lower().replace("_", "").replace(" ", "")
            key = lookup.get(norm_name)
            if key is None:
                continue

            try:
                value = row[key]
                if not self._is_missing_row_value(value):
                    return value
            except Exception:
                pass

        return None


    def _quote_bar_proxy_from_row(self, row):
        class Proxy:
            pass

        proxy = Proxy()

        proxy.BidPrice = self._first_row_value(row, [
            "bidclose", "bid_close", "bid close", "bid", "bidprice", "bid_price"
        ])
        proxy.AskPrice = self._first_row_value(row, [
            "askclose", "ask_close", "ask close", "ask", "askprice", "ask_price"
        ])
        proxy.Close = self._first_row_value(row, [
            "close", "price", "value"
        ])

        return proxy

    def _quote_row_from_quote_bar(self, req, wanted, contract_symbol, quote_bar):
        quote_date = str(req.get("quote_date") or "")[:10]
        expiration = str(wanted.get("expiration") or "")[:10]
        q_dt = datetime.strptime(quote_date, "%Y-%m-%d")
        exp_dt = datetime.strptime(expiration, "%Y-%m-%d")

        bid, ask, mid = self._bar_bid_ask_mid(quote_bar)

        strike = self._safe_float(wanted.get("strike"))
        right = self._normalize_right(wanted.get("option_right"))

        return {
            "underlying_symbol": str(req.get("symbol") or "").upper(),
            "quote_date": quote_date,
            "option_symbol": str(contract_symbol),
            "occ_symbol": self._occ_symbol(str(req.get("symbol") or "").upper(), exp_dt, right, strike),
            "expiration": expiration,
            "dte": (exp_dt.date() - q_dt.date()).days,
            "strike": strike,
            "option_right": right,
            "bid": bid,
            "ask": ask,
            "mid": mid,
            "last": self._safe_float(getattr(quote_bar, "Close", None)),
            "volume": None,
            "open_interest": None,
            "implied_volatility": None,
            "delta": None,
            "gamma": None,
            "theta": None,
            "vega": None,
            "rho": None,
            "underlying_price": None,
            "source": "quantconnect_backtest_objectstore",
            "source_batch_id": BATCH_ID,
            "source_request_id": req.get("request_id"),
            "quote_resolution_state": "quote_found",
            "requested_option_symbol": wanted.get("option_symbol"),
            "requested_expiration": expiration,
            "requested_strike": wanted.get("strike"),
            "requested_option_right": right,
        }
    def _contract_matches(self, contract, wanted):
        ident = self._contract_identity(contract)

        wanted_exp = str(wanted.get("expiration") or "")[:10]
        wanted_right = self._normalize_right(wanted.get("option_right"))
        wanted_strike = self._safe_float(wanted.get("strike"))

        if ident["expiration"] != wanted_exp:
            return False

        if ident["option_right"] != wanted_right:
            return False

        if wanted_strike is None:
            return False

        return abs(float(ident["strike"]) - float(wanted_strike)) <= 0.0001

    def _contract_identity(self, contract):
        sym = contract.Symbol
        sid = sym.ID
        right = "call" if sid.OptionRight == OptionRight.Call else "put"

        return {
            "option_symbol": str(sym),
            "occ_symbol": self._occ_symbol(str(sym.Underlying), sid.Date, right, sid.StrikePrice),
            "expiration": sid.Date.strftime("%Y-%m-%d"),
            "strike": self._safe_float(sid.StrikePrice),
            "option_right": right,
        }

    def _classify_option_quote_quality(
        self,
        bid,
        ask,
        mid,
        spread,
        spread_pct,
        implied_volatility,
        delta,
        volume,
        open_interest,
    ):
        reasons = []

        if bid is None:
            reasons.append("missing_bid")
        if ask is None:
            reasons.append("missing_ask")
        if mid is None:
            reasons.append("missing_mid")
        if spread is None:
            reasons.append("missing_spread")
        if spread_pct is None:
            reasons.append("missing_spread_pct")

        if bid is not None and ask is not None and ask < bid:
            reasons.append("crossed_bid_ask")

        if bid is not None and bid <= 0:
            reasons.append("zero_bid")

        if mid is not None and mid <= 0:
            reasons.append("nonpositive_mid")

        if implied_volatility is None:
            reasons.append("missing_iv")
        if delta is None:
            reasons.append("missing_delta")
        if volume is None:
            reasons.append("missing_volume")
        if open_interest is None:
            reasons.append("missing_open_interest")

        has_full_price = (
            bid is not None
            and ask is not None
            and mid is not None
            and spread is not None
            and spread_pct is not None
            and ask >= bid
            and mid > 0
        )

        has_core_metrics = (
            implied_volatility is not None
            and delta is not None
            and volume is not None
            and open_interest is not None
        )

        if has_full_price and has_core_metrics:
            quote_quality_state = "quote_price_full_metrics_full"
        elif has_full_price:
            quote_quality_state = "quote_price_full_metrics_partial"
        elif bid is not None or ask is not None:
            quote_quality_state = "quote_price_partial"
        else:
            quote_quality_state = "missing_quote"

        blocking_reasons = [
            reason
            for reason in reasons
            if reason in {
                "missing_bid",
                "missing_ask",
                "missing_mid",
                "missing_spread_pct",
                "crossed_bid_ask",
                "zero_bid",
                "nonpositive_mid",
            }
        ]

        execution_eligibility_state = (
            "execution_rejected" if blocking_reasons else "execution_eligible"
        )

        return quote_quality_state, execution_eligibility_state, reasons

    def _quote_row(self, req, wanted, contract):
        ident = self._contract_identity(contract)

        bid = self._safe_float(getattr(contract, "BidPrice", None))
        ask = self._safe_float(getattr(contract, "AskPrice", None))
        last = self._safe_float(getattr(contract, "LastPrice", None))

        mid = None
        if bid is not None and ask is not None:
            mid = (bid + ask) / 2.0

        spread = None
        if bid is not None and ask is not None:
            spread = ask - bid

        spread_pct = None
        if spread is not None and mid is not None and mid > 0:
            spread_pct = spread / mid

        greeks = getattr(contract, "Greeks", None)

        implied_volatility = self._safe_float(getattr(contract, "ImpliedVolatility", None))
        delta = self._safe_float(getattr(greeks, "Delta", None)) if greeks else None
        gamma = self._safe_float(getattr(greeks, "Gamma", None)) if greeks else None
        theta = self._safe_float(getattr(greeks, "Theta", None)) if greeks else None
        vega = self._safe_float(getattr(greeks, "Vega", None)) if greeks else None
        rho = self._safe_float(getattr(greeks, "Rho", None)) if greeks else None

        volume = self._safe_float(getattr(contract, "Volume", None))
        open_interest = self._safe_float(getattr(contract, "OpenInterest", None))

        quote_date = str(req.get("quote_date") or "")[:10]
        exp_dt = datetime.strptime(ident["expiration"], "%Y-%m-%d")
        q_dt = datetime.strptime(quote_date, "%Y-%m-%d")
        dte = (exp_dt.date() - q_dt.date()).days

        option_right = str(self._normalize_right(ident["option_right"]) or "").upper()
        underlying_symbol = str(req.get("symbol") or "").upper()

        contract_key = "|".join(
            [
                underlying_symbol,
                quote_date,
                ident["expiration"],
                str(ident["strike"]),
                option_right,
            ]
        )

        quote_quality_state, execution_eligibility_state, execution_reject_reasons = (
            self._classify_option_quote_quality(
                bid=bid,
                ask=ask,
                mid=mid,
                spread=spread,
                spread_pct=spread_pct,
                implied_volatility=implied_volatility,
                delta=delta,
                volume=volume,
                open_interest=open_interest,
            )
        )

        return {
            "adapter_type": "quantconnect_option_behavior_v2_export",
            "artifact_type": "signalforge_qc_replay_option_behavior_input_v2",

            "underlying_symbol": underlying_symbol,
            "quote_date": quote_date,
            "option_symbol": ident["option_symbol"],
            "occ_symbol": ident["occ_symbol"],
            "expiration": ident["expiration"],
            "dte": dte,
            "strike": ident["strike"],
            "option_right": option_right,
            "contract_key": contract_key,

            "bid": bid,
            "ask": ask,
            "mid": mid,
            "spread": spread,
            "spread_pct": spread_pct,
            "last": last,

            "volume": volume,
            "open_interest": open_interest,
            "implied_volatility": implied_volatility,
            "delta": delta,
            "gamma": gamma,
            "theta": theta,
            "vega": vega,
            "rho": rho,
            "underlying_price": self._safe_float(getattr(contract, "UnderlyingLastPrice", None)),

            "quote_seen": bid is not None or ask is not None,
            "bid_seen": bid is not None,
            "ask_seen": ask is not None,
            "mid_available": mid is not None,
            "spread_available": spread is not None,
            "spread_pct_available": spread_pct is not None,
            "iv_seen": implied_volatility is not None,
            "greeks_seen": any(x is not None for x in [delta, gamma, theta, vega, rho]),
            "volume_seen": volume is not None,
            "open_interest_seen": open_interest is not None,

            "quote_quality_state": quote_quality_state,
            "execution_eligibility_state": execution_eligibility_state,
            "execution_reject_reasons": execution_reject_reasons,

            "source": "quantconnect_backtest_objectstore",
            "source_batch_id": BATCH_ID,
            "source_request_id": req.get("request_id"),
            "quote_resolution_state": "quote_found",

            "requested_option_symbol": wanted.get("option_symbol"),
            "requested_expiration": str(wanted.get("expiration") or "")[:10],
            "requested_strike": wanted.get("strike"),
            "requested_option_right": str(self._normalize_right(wanted.get("option_right")) or "").upper(),
        }

    def _missing_row(self, req, wanted, state, error_message=None):
        underlying_symbol = str(req.get("symbol") or "").upper()
        quote_date = str(req.get("quote_date") or "")[:10]
        expiration = str(wanted.get("expiration") or "")[:10]
        strike = wanted.get("strike")
        option_right = str(self._normalize_right(wanted.get("option_right")) or "").upper()

        contract_key = "|".join(
            [
                underlying_symbol,
                quote_date,
                expiration,
                str(strike),
                option_right,
            ]
        )

        return {
            "adapter_type": "quantconnect_option_behavior_v2_export",
            "artifact_type": "signalforge_qc_replay_option_behavior_input_v2",

            "underlying_symbol": underlying_symbol,
            "quote_date": quote_date,
            "option_symbol": wanted.get("option_symbol"),
            "occ_symbol": wanted.get("occ_symbol"),
            "expiration": expiration,
            "dte": None,
            "strike": strike,
            "option_right": option_right,
            "contract_key": contract_key,

            "bid": None,
            "ask": None,
            "mid": None,
            "spread": None,
            "spread_pct": None,
            "last": None,

            "volume": None,
            "open_interest": None,
            "implied_volatility": None,
            "delta": None,
            "gamma": None,
            "theta": None,
            "vega": None,
            "rho": None,
            "underlying_price": None,

            "quote_seen": False,
            "bid_seen": False,
            "ask_seen": False,
            "mid_available": False,
            "spread_available": False,
            "spread_pct_available": False,
            "iv_seen": False,
            "greeks_seen": False,
            "volume_seen": False,
            "open_interest_seen": False,

            "quote_quality_state": "missing_quote",
            "execution_eligibility_state": "execution_rejected",
            "execution_reject_reasons": [state],

            "source": "quantconnect_backtest_objectstore",
            "source_batch_id": BATCH_ID,
            "source_request_id": req.get("request_id"),
            "quote_resolution_state": state,
            "error_message": error_message,

            "requested_option_symbol": wanted.get("option_symbol"),
            "requested_expiration": expiration,
            "requested_strike": strike,
            "requested_option_right": option_right,
        }


    def _ensure_v2_output_row(self, row):
        out = dict(row or {})

        underlying_symbol = str(out.get("underlying_symbol") or out.get("symbol") or "").upper()
        quote_date = str(out.get("quote_date") or out.get("date") or "")[:10]
        expiration = str(out.get("expiration") or out.get("requested_expiration") or "")[:10]

        strike = self._safe_float(out.get("strike"))
        if strike is None:
            strike = self._safe_float(out.get("requested_strike"))

        option_right_raw = out.get("option_right") or out.get("requested_option_right")
        option_right = str(self._normalize_right(option_right_raw) or "").upper()

        bid = self._safe_float(out.get("bid"))
        ask = self._safe_float(out.get("ask"))
        mid = self._safe_float(out.get("mid"))

        if mid is None and bid is not None and ask is not None:
            mid = (bid + ask) / 2.0

        spread = self._safe_float(out.get("spread"))
        if spread is None and bid is not None and ask is not None:
            spread = ask - bid

        spread_pct = self._safe_float(out.get("spread_pct"))
        if spread_pct is None and spread is not None and mid is not None and mid > 0:
            spread_pct = spread / mid

        implied_volatility = self._safe_float(out.get("implied_volatility"))
        delta = self._safe_float(out.get("delta"))
        volume = self._safe_float(out.get("volume"))
        open_interest = self._safe_float(out.get("open_interest"))

        contract_key = out.get("contract_key")
        if not contract_key:
            contract_key = "|".join(
                [
                    underlying_symbol,
                    quote_date,
                    expiration,
                    str(strike),
                    option_right,
                ]
            )

        quote_quality_state, execution_eligibility_state, execution_reject_reasons = (
            self._classify_option_quote_quality(
                bid=bid,
                ask=ask,
                mid=mid,
                spread=spread,
                spread_pct=spread_pct,
                implied_volatility=implied_volatility,
                delta=delta,
                volume=volume,
                open_interest=open_interest,
            )
        )

        out["adapter_type"] = "quantconnect_option_behavior_v2_export"
        out["artifact_type"] = "signalforge_qc_replay_option_behavior_input_v2"

        out["underlying_symbol"] = underlying_symbol
        out["quote_date"] = quote_date
        out["expiration"] = expiration
        out["strike"] = strike
        out["option_right"] = option_right
        out["contract_key"] = contract_key

        out["bid"] = bid
        out["ask"] = ask
        out["mid"] = mid
        out["spread"] = spread
        out["spread_pct"] = spread_pct

        out["implied_volatility"] = implied_volatility
        out["delta"] = delta
        out["gamma"] = self._safe_float(out.get("gamma"))
        out["theta"] = self._safe_float(out.get("theta"))
        out["vega"] = self._safe_float(out.get("vega"))
        out["rho"] = self._safe_float(out.get("rho"))
        out["volume"] = volume
        out["open_interest"] = open_interest

        out["quote_seen"] = bid is not None or ask is not None
        out["bid_seen"] = bid is not None
        out["ask_seen"] = ask is not None
        out["mid_available"] = mid is not None
        out["spread_available"] = spread is not None
        out["spread_pct_available"] = spread_pct is not None
        out["iv_seen"] = implied_volatility is not None
        out["greeks_seen"] = any(
            out.get(field) is not None for field in ["delta", "gamma", "theta", "vega", "rho"]
        )
        out["volume_seen"] = volume is not None
        out["open_interest_seen"] = open_interest is not None

        out["quote_quality_state"] = quote_quality_state
        out["execution_eligibility_state"] = execution_eligibility_state
        out["execution_reject_reasons"] = execution_reject_reasons

        out["source"] = out.get("source") or "quantconnect_backtest_objectstore"
        out["source_batch_id"] = BATCH_ID
        out["quote_resolution_state"] = out.get("quote_resolution_state") or quote_quality_state

        out["requested_option_symbol"] = out.get("requested_option_symbol") or out.get("option_symbol")
        out["requested_expiration"] = out.get("requested_expiration") or expiration
        out["requested_strike"] = out.get("requested_strike") if out.get("requested_strike") is not None else strike
        out["requested_option_right"] = str(
            self._normalize_right(out.get("requested_option_right") or option_right) or ""
        ).upper()

        return out


    def _clear_entire_object_store(self):
        deleted = 0
        failed = 0

        try:
            keys_obj = getattr(self.ObjectStore, "Keys", None)
            keys = list(keys_obj() if callable(keys_obj) else keys_obj)
        except Exception as err:
            self.Debug("SignalForge ObjectStore full clear skipped; key listing failed: " + str(err))
            return {"deleted": deleted, "failed": failed, "skipped": True}

        for key in keys:
            key_str = str(key)
            try:
                if hasattr(self.ObjectStore, "Delete"):
                    self.ObjectStore.Delete(key_str)
                    deleted += 1
                elif hasattr(self.ObjectStore, "Remove"):
                    self.ObjectStore.Remove(key_str)
                    deleted += 1
                else:
                    failed += 1
            except Exception as err:
                failed += 1
                self.Debug("SignalForge ObjectStore delete failed for " + key_str + ": " + str(err))

        self.Debug("SignalForge ObjectStore full clear complete: deleted=" + str(deleted) + " failed=" + str(failed))
        return {"deleted": deleted, "failed": failed, "skipped": False}

    def _write_object_store_outputs(self, batch):
        prefix = OBJECT_STORE_ROOT + "_" + BATCH_ID
        rows = [self._ensure_v2_output_row(r) for r in self.rows]

        part_keys = []
        total_parts = int(math.ceil(len(rows) / float(ROWS_PER_PART))) if rows else 1

        for index in range(total_parts):
            part_rows = rows[index * ROWS_PER_PART:(index + 1) * ROWS_PER_PART]
            raw = "\n".join(json.dumps(r, sort_keys=True, default=str) for r in part_rows).encode("utf-8")
            compressed = gzip.compress(raw)
            encoded = base64.b64encode(compressed).decode("ascii")
            sha = hashlib.sha256(compressed).hexdigest()

            key = prefix + "_part_" + str(index + 1).zfill(6) + "_jsonl_gz_b64"
            payload = {
                "artifact_type": "signalforge_qc_option_behavior_v2_part",
                "batch_id": BATCH_ID,
                "part_id": str(index + 1).zfill(6),
                "total_parts": total_parts,
                "encoding": "jsonl+gzip+base64",
                "compressed_sha256": sha,
                "row_count": len(part_rows),
                "payload": encoded,
            }

            self.ObjectStore.Save(key, json.dumps(payload))
            part_keys.append(key)

        summary = {
            "artifact_type": "signalforge_qc_option_behavior_v2_summary",
            "batch_id": BATCH_ID,
            "object_store_prefix": prefix,
            "row_count": len(rows),
            "part_count": total_parts,
            "part_keys": part_keys,
            "source_request_count": len(batch.get("requests") or []),
            "contract_request_count": sum(int(r.get("contract_count") or len(r.get("contracts") or [])) for r in batch.get("requests") or []),
        }

        manifest_key = prefix + "_manifest_json"
        self.ObjectStore.Save(manifest_key, json.dumps(summary, sort_keys=True))

        self.SetRuntimeStatistic("SignalForgeBackfillState", "object_store_written")
        self.SetRuntimeStatistic("SignalForgeBackfillBatchId", BATCH_ID)
        self.SetRuntimeStatistic("SignalForgeBackfillManifestKey", manifest_key)
        self.SetRuntimeStatistic("SignalForgeBackfillPartCount", str(total_parts))
        self.SetRuntimeStatistic("SignalForgeBackfillRowCount", str(len(rows)))

    def _write_failure(self, error_message, stacktrace):
        prefix = OBJECT_STORE_ROOT + "_" + BATCH_ID
        failure = {
            "artifact_type": "signalforge_qc_option_behavior_v2_failure",
            "batch_id": BATCH_ID,
            "error_message": error_message,
            "stacktrace": stacktrace,
        }
        key = prefix + "_failure_json"
        self.ObjectStore.Save(key, json.dumps(failure, sort_keys=True))

        self.SetRuntimeStatistic("SignalForgeBackfillState", "failed")
        self.SetRuntimeStatistic("SignalForgeBackfillBatchId", BATCH_ID)
        self.SetRuntimeStatistic("SignalForgeBackfillFailureKey", key)
        self.SetRuntimeStatistic("SignalForgeBackfillErrorMessage", str(error_message)[:3500])
        self.SetRuntimeStatistic("SignalForgeBackfillStacktraceHead", str(stacktrace)[:3500])

    def _safe_float(self, value):
        try:
            if value is None:
                return None
            x = float(value)
            if math.isnan(x) or math.isinf(x):
                return None
            return x
        except Exception:
            return None

    def _normalize_right(self, value):
        s = str(value or "").lower()
        if s in ["call", "c", "0"]:
            return "call"
        if s in ["put", "p", "1"]:
            return "put"
        return s

    def _occ_symbol(self, underlying, expiration, right, strike):
        yymmdd = expiration.strftime("%y%m%d")
        cp = "C" if str(right).lower().startswith("c") else "P"
        strike_int = int(round(float(strike) * 1000))
        return str(underlying).upper() + yymmdd + cp + str(strike_int).zfill(8)






