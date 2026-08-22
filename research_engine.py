"""Build the Nifty & F&O Research V1 page and research dataset.

V1 deliberately uses daily OHLCV data only. It provides weekly/expiry-proxy
statistics, gaps, 5-day behaviour, historical analogues, outliers and a
stock scanner sourced from the daily radar snapshot. Intraday ORB/options
chain are shown as planned extensions until intraday/options data is wired.
"""
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from market_data import fetch

ROOT = Path(__file__).parent
OUT = ROOT / "docs"
OUT.mkdir(exist_ok=True)
TODAY = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")


def indicators(df):
    x = df.copy()
    close = x["Close"]
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    x["RSI"] = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    x["EMA20"] = close.ewm(span=20, adjust=False).mean()
    x["EMA50"] = close.ewm(span=50, adjust=False).mean()
    tr = pd.concat([x["High"] - x["Low"], (x["High"] - close.shift()).abs(), (x["Low"] - close.shift()).abs()], axis=1).max(axis=1)
    x["ATR"] = tr.rolling(14).mean()
    x["ret5"] = close.pct_change(5) * 100
    x["ret20"] = close.pct_change(20) * 100
    x["gap"] = (x["Open"] / close.shift(1) - 1) * 100
    x["range"] = (x["High"] / x["Low"] - 1) * 100
    x["vol20"] = x["Volume"].rolling(20).mean()
    x["vol_ratio"] = x["Volume"] / x["vol20"]
    return x.dropna()


def stats(values):
    s = pd.Series(values).dropna()
    if not len(s):
        return {"n": 0, "avg": None, "median": None, "win": None, "std": None, "best": None, "worst": None}
    return {"n": int(len(s)), "avg": float(s.mean()), "median": float(s.median()), "win": float((s > 0).mean() * 100),
            "std": float(s.std(ddof=1)) if len(s) > 1 else 0, "best": float(s.max()), "worst": float(s.min())}


def weekly_expiry_returns(df):
    """Expiry proxy: Thu-to-Thu before 2025-09-01, Tue-to-Tue thereafter."""
    x = df.copy()
    x.index = pd.to_datetime(x.index).tz_localize(None)
    pre = x[x.index < pd.Timestamp("2025-09-01")].resample("W-THU").last()["Close"].pct_change() * 100
    post = x[x.index >= pd.Timestamp("2025-09-01")].resample("W-TUE").last()["Close"].pct_change() * 100
    return pd.concat([pre, post]).sort_index().dropna()


def load_index():
    errors = []
    for symbol in ["NIFTY 50", "NIFTY50", "NIFTY"]:
        try:
            df, source = fetch(symbol, days=1900)
            return symbol, source, indicators(df), errors
        except Exception as exc:
            errors.append(f"{symbol}: {type(exc).__name__}: {exc}")
    return None, None, None, errors


def safe(v, digits=2):
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "—"
    return f"{v:.{digits}f}"


symbol, source, idx, index_errors = load_index()
if idx is not None and len(idx):
    weekly = weekly_expiry_returns(idx)
    weekly_s = stats(weekly)
    gap_s = stats(idx["gap"])
    five_s = stats(idx["ret5"])
    out_cut_hi = idx["ret5"].quantile(.975)
    out_cut_lo = idx["ret5"].quantile(.025)
    outliers = idx[(idx["ret5"] >= out_cut_hi) | (idx["ret5"] <= out_cut_lo)].tail(24)
    current = idx.iloc[-1]

    # Historical analogue: nearest prior observations on three current-state dimensions.
    feature_cols = ["ret5", "RSI", "gap"]
    hist = idx.iloc[:-1].dropna(subset=feature_cols).copy()
    zscale = hist[feature_cols].std().replace(0, 1)
    target = current[feature_cols]
    hist["distance"] = (((hist[feature_cols] - target) / zscale) ** 2).sum(axis=1) ** .5
    analogues = hist.nsmallest(8, "distance").copy()
    analogues["next5"] = idx["Close"].pct_change(5).shift(-5).reindex(analogues.index) * 100
    analogues["next20"] = idx["Close"].pct_change(20).shift(-20).reindex(analogues.index) * 100
else:
    weekly_s = gap_s = five_s = {"n": 0, "avg": None, "median": None, "win": None, "std": None, "best": None, "worst": None}
    outliers = pd.DataFrame()
    analogues = pd.DataFrame()
    current = None

# Reuse the daily stock radar data for the F&O scanner.
data_path = OUT / f"data-{TODAY}.json"
if data_path.exists():
    snapshot = json.loads(data_path.read_text(encoding="utf-8"))
    stocks = snapshot.get("stocks", [])
else:
    snapshot = {"market_regime": "Unknown", "stocks": []}
    stocks = []

stocks = sorted(stocks, key=lambda r: float(r.get("score", 0)), reverse=True)
scanner = stocks[:20]


def pct(v):
    return "—" if v is None else f"{v:+.2f}%"


def metric_card(label, value, sub=""):
    return f"<div class='metric'><span>{label}</span><strong>{value}</strong><small>{sub}</small></div>"


def table_rows(items, fn):
    return "".join(fn(x) for x in items)


weekly_html = metric_card("Average weekly / expiry-proxy", pct(weekly_s["avg"])) + metric_card("Win rate", f"{safe(weekly_s['win'],1)}%") + metric_card("Best", pct(weekly_s["best"])) + metric_card("Worst", pct(weekly_s["worst"]))
gap_html = metric_card("Average gap", pct(gap_s["avg"])) + metric_card("Gap volatility", f"{safe(gap_s['std'],2)}%") + metric_card("Gap-up win sample", f"{safe(gap_s['win'],1)}%") + metric_card("5-day average", pct(five_s["avg"]))

scanner_rows = table_rows(scanner, lambda r: (
    f"<tr><td><b>{r.get('nse_symbol','')}</b></td><td>{r.get('sector','')}</td><td><b>{safe(float(r.get('score',0)),1)}</b></td>"
    f"<td>{r.get('rec','')}</td><td>{r.get('horizon','')}</td><td>{pct(r.get('rs3'))}</td>"
    f"<td>{safe(r.get('technical',{}).get('rsi'),1)}</td><td>{r.get('technical',{}).get('trend','—')}</td>"
    f"<td>{safe(r.get('technical',{}).get('adx'),1)}</td><td>{safe(r.get('technical',{}).get('vol_ratio'),2)}x</td></tr>"
))

analogue_rows = table_rows(analogues.itertuples(), lambda r: (
    f"<tr><td>{r.Index.strftime('%Y-%m-%d')}</td><td>{safe(r.ret5,2)}%</td><td>{safe(r.RSI,1)}</td>"
    f"<td>{safe(r.gap,2)}%</td><td>{safe(r.next5,2)}%</td><td>{safe(r.next20,2)}%</td></tr>"
)) if len(analogues) else "<tr><td colspan='6'>Historical index data unavailable in this run.</td></tr>"

outlier_rows = table_rows(outliers.sort_index(ascending=False).itertuples(), lambda r: (
    f"<tr><td>{r.Index.strftime('%Y-%m-%d')}</td><td>{safe(r.ret5,2)}%</td><td>{safe(r.RSI,1)}</td>"
    f"<td>{safe(r.gap,2)}%</td><td>{'Upside' if r.ret5 > 0 else 'Downside'}</td></tr>"
)) if len(outliers) else "<tr><td colspan='5'>No outliers available.</td></tr>"

current_state = (
    f"<div class='state'><b>Current market state</b><div class='stategrid'>"
    f"<span>Close <b>{safe(current.Close)}</b></span><span>5D <b>{pct(current.ret5)}</b></span>"
    f"<span>RSI <b>{safe(current.RSI,1)}</b></span><span>Gap <b>{pct(current.gap)}</b></span>"
    f"<span>EMA20 <b>{'Above' if current.Close > current.EMA20 else 'Below'}</b></span>"
    f"<span>EMA50 <b>{'Above' if current.Close > current.EMA50 else 'Below'}</b></span>"
    f"</div></div>" if current is not None else "<div class='state'><b>Current market state unavailable</b></div>"
)

source_note = f"Index source: {symbol} via {source}." if symbol else "Index history could not be fetched; the page still provides the stock scanner from the daily radar."

page = f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Nifty & F&O Research V1</title><style>
:root{{--bg:#0b1020;--panel:#121a2c;--muted:#98a2b3;--text:#f8fafc;--line:#26334d;--accent:#7dd3fc;--green:#34d399;--red:#fb7185;}}
*{{box-sizing:border-box}}body{{margin:0;background:linear-gradient(135deg,#090e1a,#111827);font-family:Inter,system-ui,sans-serif;color:var(--text)}}
header{{padding:24px 28px;border-bottom:1px solid var(--line);position:sticky;top:0;background:#0b1020ee;backdrop-filter:blur(12px);z-index:5}}
header h1{{margin:0 0 5px;font-size:28px}}header p{{margin:0;color:var(--muted);font-size:13px}}main{{max-width:1500px;margin:auto;padding:22px}}
.nav{{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 18px}}.nav a{{color:#dbeafe;text-decoration:none;border:1px solid var(--line);padding:8px 12px;border-radius:999px;font-size:12px}}
.controls{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:18px}}select,input{{background:var(--panel);color:var(--text);border:1px solid var(--line);border-radius:9px;padding:9px 12px}}
.section{{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:18px;margin:14px 0;box-shadow:0 10px 30px #0003}}
.section h2{{margin:0 0 6px;font-size:20px}}.sub{{color:var(--muted);font-size:12px;margin-bottom:14px}}.metrics{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}}
.metric{{background:#0d1526;border:1px solid var(--line);border-radius:12px;padding:13px}}.metric span,.metric small{{display:block;color:var(--muted);font-size:11px}}.metric strong{{display:block;font-size:24px;margin:5px 0}}
.state{{border:1px solid #1e4d66;background:#0c2030;border-radius:12px;padding:14px;margin-bottom:12px}}.stategrid{{display:grid;grid-template-columns:repeat(6,1fr);gap:8px;margin-top:10px}}.stategrid span{{font-size:11px;color:var(--muted);background:#091624;padding:9px;border-radius:8px}}.stategrid b{{display:block;color:var(--text);font-size:14px;margin-top:3px}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}table{{width:100%;border-collapse:collapse;min-width:780px}}th,td{{padding:9px;border-bottom:1px solid var(--line);font-size:11px;text-align:left}}th{{color:#cbd5e1;background:#0c1424;position:sticky;top:77px}}.tablewrap{{overflow:auto;border:1px solid var(--line);border-radius:10px}}
.badge{{display:inline-block;padding:5px 8px;border-radius:7px;background:#143326;color:#a7f3d0;font-size:10px;font-weight:800}}.note{{color:var(--muted);font-size:11px;line-height:1.6}}.warning{{color:#fde68a;background:#2b2410;border:1px solid #6b5718;padding:10px;border-radius:9px;font-size:11px}}
@media(max-width:850px){{.metrics{{grid-template-columns:repeat(2,1fr)}}.grid2{{grid-template-columns:1fr}}.stategrid{{grid-template-columns:repeat(2,1fr)}}}}
</style></head><body><header><h1>📊 Nifty & F&O Research</h1><p>V1 — historical behaviour, conditional analogues, gaps, outliers and F&O stock ranking</p></header>
<main><div class='nav'><a href='index.html'>← Growth Radar</a><a href='news.html'>📰 News Intelligence</a><a href='research.html'>📊 Research</a></div>
<div class='controls'><select id='universe'><option>Nifty 50</option><option>Bank Nifty</option><option>F&O Stocks</option></select><select id='period'><option>Weekly</option><option>Monthly</option><option>Expiry proxy</option></select><select id='calc'><option>Close → Close</option><option>Open → Close</option><option>High → Low</option></select><input type='date' value='2021-01-01'><span class='badge'>Daily snapshot: {TODAY}</span></div>
<section class='section'><h2>① Overview</h2><div class='sub'>{source_note}</div>{current_state}<div class='metrics'>{weekly_html}</div></section>
<section class='section'><h2>② Expiry / Weekly Behaviour</h2><div class='sub'>Expiry proxy follows Thursday-to-Thursday before 1 Sep 2025 and Tuesday-to-Tuesday after the Nifty expiry weekday change.</div><div class='metrics'>{weekly_html}</div><p class='note'>Use the distribution, not just the average. A positive average can coexist with large downside tails.</p></section>
<section class='section'><h2>③ Intraday & Gap</h2><div class='sub'>V1 starts with opening gaps and 5-session behaviour from daily OHLCV.</div><div class='metrics'>{gap_html}</div><p class='warning'>15-minute ORB is intentionally not enabled yet because this repository currently has daily OHLCV data. We will add it when an intraday source is connected rather than backfilling or fabricating it.</p></section>
<section class='section'><h2>④ Historical Analogues</h2><div class='sub'>Closest historical states using 5-day return, RSI and opening gap. The next-5D and next-20D columns show what happened after those analogous dates.</div><div class='tablewrap'><table><thead><tr><th>Date</th><th>5D at setup</th><th>RSI</th><th>Gap</th><th>Next 5D</th><th>Next 20D</th></tr></thead><tbody>{analogue_rows}</tbody></table></div></section>
<section class='section'><h2>⑤ F&O Stock Scanner</h2><div class='sub'>Ranks the same daily universe used by the Growth Radar. Score combines trend, relative strength, breakout/volume, momentum and fundamental quality; it is not a trade recommendation.</div><div class='tablewrap'><table><thead><tr><th>Symbol</th><th>Sector</th><th>Score</th><th>Action</th><th>Horizon</th><th>RS 3M</th><th>RSI</th><th>Trend</th><th>ADX</th><th>Vol/20D</th></tr></thead><tbody>{scanner_rows or '<tr><td colspan="10">No daily stock snapshot available.</td></tr>'}</tbody></table></div></section>
<section class='section'><h2>⑥ Outliers & Events</h2><div class='sub'>Extreme 5-session moves based on the 2.5% tails. Event/news linking will be connected to the existing News Intelligence data next.</div><div class='tablewrap'><table><thead><tr><th>Date</th><th>5D return</th><th>RSI</th><th>Gap</th><th>Type</th></tr></thead><tbody>{outlier_rows}</tbody></table></div></section>
<section class='section'><h2>V1 → V2 roadmap</h2><p class='note'><b>V1 now:</b> weekly/expiry-proxy behaviour, gaps, 5D behaviour, historical analogues, outliers and stock ranking. <b>Next:</b> 15-minute ORB, live option-chain/IV/OI, Bank Nifty-specific history, sector correlation, event attribution and an AI query layer that answers from these datasets.</p></section>
<p class='note'>Generated {datetime.now(timezone.utc).isoformat()}. Missing data is shown as unavailable. This tool is for quantitative research, not a guarantee of returns.</p>
</main></body></html>"""

payload = {
    "date": TODAY, "index_symbol": symbol, "index_source": source, "index_fetch_errors": index_errors,
    "weekly_expiry_proxy": weekly_s, "gap": gap_s, "five_day": five_s,
    "current": None if current is None else {k: float(current[k]) for k in ["Close","RSI","EMA20","EMA50","ret5","gap"]},
    "analogues": [] if not len(analogues) else [{"date": r.Index.strftime("%Y-%m-%d"), "setup_5d": float(r.ret5), "rsi": float(r.RSI), "gap": float(r.gap), "next5": None if pd.isna(r.next5) else float(r.next5), "next20": None if pd.isna(r.next20) else float(r.next20)} for r in analogues.itertuples()],
    "outliers": [] if not len(outliers) else [{"date": r.Index.strftime("%Y-%m-%d"), "ret5": float(r.ret5), "rsi": float(r.RSI), "gap": float(r.gap)} for r in outliers.itertuples()],
    "scanner_symbols": [r.get("nse_symbol") for r in scanner],
}
(OUT / "research-latest.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
(OUT / f"research-{TODAY}.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
(OUT / "research.html").write_text(page, encoding="utf-8")
print(f"Generated docs/research.html and research data; index={symbol or 'unavailable'}; scanner={len(scanner)}")
