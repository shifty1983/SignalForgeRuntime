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

OBJECT_STORE_ROOT = "signalforge_canonical_options_backfill_20210601_20260531"
ROWS_PER_PART = 500


class SignalForgeCanonicalOptionQuoteBackfill(QCAlgorithm):

    def Initialize(self):
        self.rows = []
        self.error_rows = []

        try:
            batch = self._decode_batch(BATCH_PAYLOAD_B64)

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

    def _quote_row(self, req, wanted, contract):
        ident = self._contract_identity(contract)

        bid = self._safe_float(getattr(contract, "BidPrice", None))
        ask = self._safe_float(getattr(contract, "AskPrice", None))
        last = self._safe_float(getattr(contract, "LastPrice", None))
        mid = None
        if bid is not None and ask is not None:
            mid = (bid + ask) / 2.0

        greeks = getattr(contract, "Greeks", None)

        quote_date = str(req.get("quote_date") or "")[:10]
        exp_dt = datetime.strptime(ident["expiration"], "%Y-%m-%d")
        q_dt = datetime.strptime(quote_date, "%Y-%m-%d")

        return {
            "underlying_symbol": str(req.get("symbol") or "").upper(),
            "quote_date": quote_date,
            "option_symbol": ident["option_symbol"],
            "occ_symbol": ident["occ_symbol"],
            "expiration": ident["expiration"],
            "dte": (exp_dt.date() - q_dt.date()).days,
            "strike": ident["strike"],
            "option_right": ident["option_right"],
            "bid": bid,
            "ask": ask,
            "mid": mid,
            "last": last,
            "volume": self._safe_float(getattr(contract, "Volume", None)),
            "open_interest": self._safe_float(getattr(contract, "OpenInterest", None)),
            "implied_volatility": self._safe_float(getattr(contract, "ImpliedVolatility", None)),
            "delta": self._safe_float(getattr(greeks, "Delta", None)) if greeks else None,
            "gamma": self._safe_float(getattr(greeks, "Gamma", None)) if greeks else None,
            "theta": self._safe_float(getattr(greeks, "Theta", None)) if greeks else None,
            "vega": self._safe_float(getattr(greeks, "Vega", None)) if greeks else None,
            "rho": self._safe_float(getattr(greeks, "Rho", None)) if greeks else None,
            "underlying_price": self._safe_float(getattr(contract, "UnderlyingLastPrice", None)),
            "source": "quantconnect_backtest_objectstore",
            "source_batch_id": BATCH_ID,
            "source_request_id": req.get("request_id"),
            "quote_resolution_state": "quote_found",
            "requested_option_symbol": wanted.get("option_symbol"),
            "requested_expiration": str(wanted.get("expiration") or "")[:10],
            "requested_strike": wanted.get("strike"),
            "requested_option_right": self._normalize_right(wanted.get("option_right")),
        }

    def _missing_row(self, req, wanted, state, error_message=None):
        return {
            "underlying_symbol": str(req.get("symbol") or "").upper(),
            "quote_date": str(req.get("quote_date") or "")[:10],
            "option_symbol": wanted.get("option_symbol"),
            "occ_symbol": wanted.get("occ_symbol"),
            "expiration": str(wanted.get("expiration") or "")[:10],
            "dte": None,
            "strike": self._safe_float(wanted.get("strike")),
            "option_right": self._normalize_right(wanted.get("option_right")),
            "bid": None,
            "ask": None,
            "mid": None,
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
            "source": "quantconnect_backtest_objectstore",
            "source_batch_id": BATCH_ID,
            "source_request_id": req.get("request_id"),
            "quote_resolution_state": state,
            "requested_option_symbol": wanted.get("option_symbol"),
            "requested_expiration": str(wanted.get("expiration") or "")[:10],
            "requested_strike": wanted.get("strike"),
            "requested_option_right": self._normalize_right(wanted.get("option_right")),
            "error_message": error_message,
            "diagnostic_contract_symbol": wanted.get("diagnostic_contract_symbol"),
        }

    def _write_object_store_outputs(self, batch):
        prefix = OBJECT_STORE_ROOT + "_" + BATCH_ID
        rows = self.rows

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
                "artifact_type": "signalforge_canonical_options_backfill_part",
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
            "artifact_type": "signalforge_canonical_options_backfill_summary",
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
            "artifact_type": "signalforge_canonical_options_backfill_failure",
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






