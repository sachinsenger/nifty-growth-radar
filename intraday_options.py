"""Intraday ORB and option-chain analytics for the Research page.

Data sources:
- Yahoo Finance chart endpoint for 15-minute NSE index candles (historical intraday).
- Yahoo Finance option-chain endpoint for the current NIFTY/BANKNIFTY chain when
  Yahoo exposes the contracts. Missing option data is reported as unavailable;
  the engine never fabricates an option chain.

This module intentionally keeps option-chain analysis snapshot-based. Historical
option-chain backtests require a licensed/historical derivatives data source and
are not inferred from today's chain.
"""
from __future__ import annotations

from datetime import datetime
from urllib.parse import quote

import pandas as pd
import requests

IST = "Asia/Kolkata"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
}

YAHOO_SYMBOLS = {"NIFTY": "^NSEI", "BANKNIFTY": "^NSEBANK"}


def _session():
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def fetch_15m(symbol="NIFTY", range_days=60):
    """Fetch Yahoo 15m candles and return an IST-indexed dataframe."""
    yahoo = YAHOO_SYMBOLS.get(symbol, symbol)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(yahoo, safe='')}"
    params = {"interval": "15m", "range": f"{range_days}d", "events": "history", "includeAdjustedClose": "true"}
    r = _session().get(url, params=params, timeout=20)
    r.raise_for_status()
    result = r.json()["chart"]["result"]
    if not result:
        raise ValueError("Yahoo returned no intraday result")
    item = result[0]
    ts = item.get("timestamp") or []
    q = (item.get("indicators", {}).get("quote") or [{}])[0]
    df = pd.DataFrame({
        "Open": q.get("open", []), "High": q.get("high", []),
        "Low": q.get("low", []), "Close": q.get("close", []),
        "Volume": q.get("volume", []),
    }, index=pd.to_datetime(ts, unit="s", utc=True))
    df.index = df.index.tz_convert(IST)
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    df = df.between_time("09:15", "15:30")
    return df


def orb_backtest(df, target_r=1.0):
    """Backtest one opening-range breakout per session.

    Entry is the first 15m candle close beyond the opening-range high/low.
    Stop is the opposite side of the opening range. Target is target_r times
    the range. If target and stop are both touched in the same candle, the
    result is conservatively classified as a stop.
    """
    rows = []
    if df is None or df.empty:
        return {"source_rows": 0, "days": 0, "signals": 0, "win_rate": None, "avg_r": None, "profit_factor": None, "trades": []}
    x = df.copy()
    x["session"] = x.index.date
    for day, g in x.groupby("session"):
        g = g.sort_index()
        opening = g.between_time("09:15", "09:30", inclusive="left")
        if opening.empty:
            continue
        orb_high = float(opening["High"].max())
        orb_low = float(opening["Low"].min())
        risk = orb_high - orb_low
        if risk <= 0:
            continue
        after = g[g.index.time >= datetime.strptime("09:30", "%H:%M").time()]
        signal = None
        for ts, bar in after.iterrows():
            if float(bar["Close"]) > orb_high:
                signal = ("LONG", ts, float(bar["Close"]))
                break
            if float(bar["Close"]) < orb_low:
                signal = ("SHORT", ts, float(bar["Close"]))
                break
        if signal is None:
            continue
        side, entry_ts, entry = signal
        stop = orb_low if side == "LONG" else orb_high
        target = entry + target_r * risk if side == "LONG" else entry - target_r * risk
        forward = g[g.index >= entry_ts]
        outcome = "EOD"
        r_multiple = None
        for _, bar in forward.iterrows():
            hi, lo = float(bar["High"]), float(bar["Low"])
            if side == "LONG":
                if lo <= stop:
                    outcome, r_multiple = "STOP", -1.0
                    break
                if hi >= target:
                    outcome, r_multiple = "TARGET", target_r
                    break
            else:
                if hi >= stop:
                    outcome, r_multiple = "STOP", -1.0
                    break
                if lo <= target:
                    outcome, r_multiple = "TARGET", target_r
                    break
        if r_multiple is None:
            close = float(forward.iloc[-1]["Close"])
            r_multiple = ((close - entry) / risk) if side == "LONG" else ((entry - close) / risk)
        rows.append({"date": str(day), "side": side, "entry": entry, "orb_high": orb_high, "orb_low": orb_low,
                     "entry_time": entry_ts.strftime("%H:%M"), "outcome": outcome, "r": float(r_multiple)})
    trades = pd.DataFrame(rows)
    if trades.empty:
        return {"source_rows": int(len(df)), "days": int(df["session"].nunique()), "signals": 0, "win_rate": None, "avg_r": None, "profit_factor": None, "trades": []}
    gains = trades.loc[trades.r > 0, "r"].sum()
    losses = -trades.loc[trades.r < 0, "r"].sum()
    pf = float(gains / losses) if losses > 0 else None
    return {"source_rows": int(len(df)), "days": int(df["session"].nunique()), "signals": int(len(trades)),
            "win_rate": float((trades.r > 0).mean() * 100), "avg_r": float(trades.r.mean()),
            "profit_factor": pf, "trades": rows[-12:]}


def _max_pain(rows):
    strikes = sorted({float(r["strike"]) for r in rows})
    if not strikes:
        return None
    pains = {}
    for settle in strikes:
        total = 0.0
        for r in rows:
            oi = float(r.get("oi") or 0)
            strike = float(r["strike"])
            if r["type"] == "CE":
                total += max(0.0, settle - strike) * oi
            else:
                total += max(0.0, strike - settle) * oi
        pains[settle] = total
    return min(pains, key=pains.get)


def _parse_yahoo_option_contracts(payload):
    result = payload.get("optionChain", {}).get("result") or []
    if not result:
        return None
    item = result[0]
    underlying = (item.get("quote") or {}).get("regularMarketPrice")
    expirations = item.get("expirationDates") or []
    chains = item.get("options") or []
    if not chains:
        return None
    raw = chains[0]
    rows = []
    for side, typ in [(raw.get("calls", []), "CE"), (raw.get("puts", []), "PE")]:
        for c in side:
            rows.append({"type": typ, "strike": c.get("strike"), "ltp": c.get("lastPrice"),
                         "bid": c.get("bid"), "ask": c.get("ask"), "volume": c.get("volume"),
                         "oi": c.get("openInterest"), "iv": c.get("impliedVolatility"),
                         "expiry": c.get("expiration")})
    if not rows:
        return None
    return {"underlying": underlying, "expirations": [datetime.fromtimestamp(int(e)).date().isoformat() for e in expirations], "rows": rows}


def fetch_option_chain(symbol="NIFTY"):
    """Fetch the current Yahoo option chain for NIFTY/BANKNIFTY."""
    yahoo = YAHOO_SYMBOLS.get(symbol)
    if not yahoo:
        raise ValueError(f"Unsupported option symbol: {symbol}")
    url = f"https://query2.finance.yahoo.com/v7/finance/options/{quote(yahoo, safe='')}"
    r = _session().get(url, timeout=20)
    r.raise_for_status()
    parsed = _parse_yahoo_option_contracts(r.json())
    if not parsed:
        return {"available": False, "source": "Yahoo Finance", "reason": "No current NSE option contracts exposed by Yahoo"}
    rows = parsed["rows"]
    spot = parsed["underlying"]
    strikes = sorted({float(x["strike"]) for x in rows})
    atm = min(strikes, key=lambda s: abs(s - float(spot))) if spot is not None and strikes else None
    expiry = rows[0].get("expiry") if rows else None
    near = [x for x in rows if x.get("expiry") == expiry]
    ce_oi = sum(float(x.get("oi") or 0) for x in near if x["type"] == "CE")
    pe_oi = sum(float(x.get("oi") or 0) for x in near if x["type"] == "PE")
    pcr = pe_oi / ce_oi if ce_oi else None
    call_walls = sorted([x for x in near if x["type"] == "CE"], key=lambda x: float(x.get("oi") or 0), reverse=True)[:5]
    put_walls = sorted([x for x in near if x["type"] == "PE"], key=lambda x: float(x.get("oi") or 0), reverse=True)[:5]
    return {"available": True, "source": "Yahoo Finance", "underlying": spot, "expiry": expiry, "atm": atm,
            "pcr_oi": pcr, "call_oi": ce_oi, "put_oi": pe_oi,
            "max_pain": _max_pain(near), "call_walls": call_walls, "put_walls": put_walls,
            "rows": near}


def collect_research_data():
    result = {"intraday": {}, "options": {}, "errors": []}
    for symbol in ["NIFTY", "BANKNIFTY"]:
        try:
            df = fetch_15m(symbol)
            result["intraday"][symbol] = {"source": "Yahoo Finance 15m", "orb": orb_backtest(df)}
        except Exception as exc:
            result["intraday"][symbol] = {"available": False, "source": "Yahoo Finance 15m", "reason": str(exc)}
            result["errors"].append(f"{symbol} intraday: {type(exc).__name__}: {exc}")
        try:
            result["options"][symbol] = fetch_option_chain(symbol)
        except Exception as exc:
            result["options"][symbol] = {"available": False, "source": "Yahoo Finance", "reason": str(exc)}
            result["errors"].append(f"{symbol} options: {type(exc).__name__}: {exc}")
    return result
