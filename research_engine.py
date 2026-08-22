"""Build a standalone Nifty & F&O Research page.

This page is intentionally independent from the Daily Growth Radar.
It fetches its own Nifty/index and stock OHLCV data and never reads the
radar's generated JSON or scores. The only shared item is stocks.csv, which
is a static universe definition, not radar output.
"""
import html
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).parent
OUT = ROOT / "docs"
OUT.mkdir(exist_ok=True)
TODAY = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")

SECTORS = {
    "RELIANCE":"Energy", "HDFCBANK":"Financials", "ICICIBANK":"Financials", "BHARTIARTL":"Telecom",
    "TCS":"IT", "INFY":"IT", "SBIN":"Financials", "LICI":"Financials", "ITC":"FMCG",
    "HINDUNILVR":"FMCG", "LT":"Industrials", "AXISBANK":"Financials", "KOTAKBANK":"Financials",
    "BAJFINANCE":"Financials", "MARUTI":"Auto", "SUNPHARMA":"Pharma", "HCLTECH":"IT",
    "NTPC":"Utilities", "M&M":"Auto", "TITAN":"Consumer", "BSE":"Financials", "OFSS":"IT",
    "SOLARINDS":"Industrials", "POLYCAB":"Industrials", "DIXON":"Electronics", "CUMMINSIND":"Industrials",
    "CGPOWER":"Industrials", "COFORGE":"IT", "FEDERALBNK":"Financials", "INDIANB":"Financials",
    "MUTHOOTFIN":"Financials", "POLICYBZR":"Financials", "MAZDOCK":"Industrials", "ASTRAL":"Industrials",
    "APLAPOLLO":"Industrials", "PERSISTENT":"IT", "MAXHEALTH":"Healthcare", "SUPREMEIND":"Industrials",
    "SONACOMS":"Auto", "BHARATFORG":"Auto", "ZENSARTECH":"IT", "HFCL":"Telecom", "AEGISLOG":"Logistics",
    "NEULANDLAB":"Pharma", "FORCEMOT":"Auto", "BLS":"Services", "ECLERX":"IT", "GREAVESCOT":"Auto",
    "MARKSANS":"Pharma", "BALAMINES":"Chemicals", "CDSL":"Financials", "DELHIVERY":"Logistics",
    "ATHERENERG":"Auto", "KIMS":"Healthcare", "DATAPATTNS":"Defence", "KIRLOSENG":"Industrials",
    "CAMS":"Financials", "NH":"Healthcare", "KVBL":"Financials",
}


def safe(v, digits=2):
    try:
        if v is None or not math.isfinite(float(v)):
            return "—"
        return f"{float(v):.{digits}f}"
    except Exception:
        return "—"


def pct(v, digits=2):
    try:
        return f"{float(v):+.{digits}f}%"
    except Exception:
        return "—"


def indicators(df):
    x = df.copy().sort_index()
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        x[col] = pd.to_numeric(x[col], errors="coerce")
    close = x["Close"]
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    x["RSI"] = 100 - 100 / (1 + rs)
    x["EMA20"] = close.ewm(span=20, adjust=False).mean()
    x["EMA50"] = close.ewm(span=50, adjust=False).mean()
    x["EMA200"] = close.ewm(span=200, adjust=False).mean()
    tr = pd.concat([
        x["High"] - x["Low"],
        (x["High"] - close.shift()).abs(),
        (x["Low"] - close.shift()).abs(),
    ], axis=1).max(axis=1)
    x["ATR"] = tr.rolling(14).mean()
    x["ret5"] = close.pct_change(5) * 100
    x["ret20"] = close.pct_change(20) * 100
    x["ret60"] = close.pct_change(60) * 100
    x["gap"] = (x["Open"] / close.shift(1) - 1) * 100
    x["range"] = (x["High"] / x["Low"] - 1) * 100
    x["vol20"] = x["Volume"].rolling(20).mean()
    x["vol_ratio"] = x["Volume"] / x["vol20"].replace(0, np.nan)
    x["high20"] = close.rolling(20).max().shift(1)
    return x.dropna(subset=["RSI", "EMA20", "EMA50", "ATR", "ret5", "ret20", "ret60", "gap", "vol_ratio"])


def yf_download(tickers, period="8y"):
    raw = yf.download(
        tickers=tickers,
        period=period,
        interval="1d",
        auto_adjust=False,
        progress=False,
        group_by="ticker",
        threads=True,
    )
    if raw is None or raw.empty:
        raise RuntimeError("Yahoo Finance returned no daily OHLCV data")
    result = {}
    if isinstance(raw.columns, pd.MultiIndex):
        first = set(raw.columns.get_level_values(0))
        # group_by=ticker normally produces ticker at level 0.
        for ticker in tickers:
            if ticker not in first:
                continue
            df = raw[ticker].copy()
            if "Close" in df.columns:
                result[ticker] = df.dropna(how="all")
    else:
        result[tickers[0]] = raw
    return result


def weekly_expiry_returns(df):
    x = df.copy()
    x.index = pd.to_datetime(x.index).tz_localize(None)
    pre = x[x.index < pd.Timestamp("2025-09-01")].resample("W-THU").last()["Close"].pct_change() * 100
    post = x[x.index >= pd.Timestamp("2025-09-01")].resample("W-TUE").last()["Close"].pct_change() * 100
    return pd.concat([pre, post]).sort_index().dropna()


def stats(values):
    s = pd.Series(values).dropna()
    if len(s) == 0:
        return {"n": 0, "avg": None, "median": None, "win": None, "std": None, "best": None, "worst": None}
    return {
        "n": int(len(s)), "avg": float(s.mean()), "median": float(s.median()),
        "win": float((s > 0).mean() * 100),
        "std": float(s.std(ddof=1)) if len(s) > 1 else 0.0,
        "best": float(s.max()), "worst": float(s.min()),
    }


def load_universe():
    stocks = pd.read_csv(ROOT / "stocks.csv")
    tickers = ["^NSEI"] + [f"{str(x).strip()}.NS" for x in stocks["nse_symbol"]]
    # Deduplicate while preserving order.
    tickers = list(dict.fromkeys(tickers))
    raw = yf_download(tickers, period="8y")
    return stocks, raw


def technical_score(t, benchmark):
    close = float(t["Close"])
    trend = 28 if close > t["EMA20"] > t["EMA50"] else 20 if close > t["EMA50"] else 8
    long_trend = 12 if close > t["EMA200"] else 3
    momentum = min(18, max(0, 9 + float(t["ret60"]) * 0.25))
    rs = float(t["ret60"]) - float(benchmark["ret60"])
    relative = min(15, max(0, 7 + rs * 0.35))
    breakout = 12 if close > float(t["high20"]) else 5 if close > float(t["EMA20"]) else 0
    volume = 10 if float(t["vol_ratio"]) >= 1.5 else 7 if float(t["vol_ratio"]) >= 1.15 else 3
    rsi = float(t["RSI"])
    rsi_quality = 5 if 52 <= rsi <= 68 else 3 if 45 <= rsi < 52 or 68 < rsi <= 73 else 1
    return round(min(100, trend + long_trend + momentum + relative + breakout + volume + rsi_quality), 1), rs


def classify(score, rsi, distance):
    if score >= 80 and rsi <= 72 and distance <= 7:
        return "STRONG SETUP"
    if score >= 72 and (rsi > 72 or distance > 7):
        return "PULLBACK WATCH"
    if score >= 65:
        return "WATCH"
    return "LOW PRIORITY"


def card(label, value, sub=""):
    return f"<div class='metric'><span>{html.escape(label)}</span><strong>{html.escape(str(value))}</strong><small>{html.escape(sub)}</small></div>"


stocks, raw = load_universe()
idx_raw = raw.get("^NSEI")
idx = indicators(idx_raw) if idx_raw is not None else pd.DataFrame()

if idx.empty:
    raise RuntimeError("Independent Nifty research data unavailable from Yahoo Finance")

weekly = weekly_expiry_returns(idx)
weekly_s = stats(weekly)
gap_s = stats(idx["gap"])
five_s = stats(idx["ret5"])
current = idx.iloc[-1]

feature_cols = ["ret5", "RSI", "gap"]
hist = idx.iloc[:-1].dropna(subset=feature_cols).copy()
zscale = hist[feature_cols].std().replace(0, 1)
target = current[feature_cols]
hist["distance"] = (((hist[feature_cols] - target) / zscale) ** 2).sum(axis=1) ** 0.5
analogues = hist.nsmallest(10, "distance").copy()
analogues["next5"] = idx["Close"].pct_change(5).shift(-5).reindex(analogues.index) * 100
analogues["next20"] = idx["Close"].pct_change(20).shift(-20).reindex(analogues.index) * 100

out_hi = idx["ret5"].quantile(.975)
out_lo = idx["ret5"].quantile(.025)
outliers = idx[(idx["ret5"] >= out_hi) | (idx["ret5"] <= out_lo)].tail(30)

benchmark = current
ranked = []
failures = []
for _, row in stocks.iterrows():
    symbol = str(row["nse_symbol"]).strip()
    ticker = f"{symbol}.NS"
    df = raw.get(ticker)
    if df is None or len(df) < 220:
        failures.append({"symbol": symbol, "error": "Insufficient independent Yahoo daily history"})
        continue
    try:
        tdf = indicators(df)
        if tdf.empty:
            raise ValueError("No usable technical rows")
        t = tdf.iloc[-1]
        score, rs = technical_score(t, benchmark)
        distance = (float(t["Close"]) / float(t["EMA20"]) - 1) * 100
        action = classify(score, float(t["RSI"]), distance)
        stop = min(float(t["EMA20"]), float(t["Close"]) - 1.5 * float(t["ATR"]))
        risk = max(0.01, float(t["Close"]) - stop)
        target_price = float(t["Close"]) + risk * (1.8 if score >= 80 else 1.5)
        ranked.append({
            "name": row["name"], "symbol": symbol, "cap": row["cap"], "sector": SECTORS.get(symbol, "Other"),
            "score": score, "action": action, "close": float(t["Close"]), "rsi": float(t["RSI"]),
            "ret20": float(t["ret20"]), "ret60": float(t["ret60"]), "rs60": rs,
            "trend": "Bullish alignment" if float(t["Close"]) > float(t["EMA20"]) > float(t["EMA50"]) else "Mixed",
            "adx": None, "vol_ratio": float(t["vol_ratio"]), "atr_pct": float(t["ATR"] / t["Close"] * 100),
            "ema20": float(t["EMA20"]), "ema50": float(t["EMA50"]), "ema200": float(t["EMA200"]),
            "stop": stop, "target": target_price, "rr": round((target_price - float(t["Close"])) / risk, 1),
        })
    except Exception as exc:
        failures.append({"symbol": symbol, "error": f"{type(exc).__name__}: {exc}"})

ranked.sort(key=lambda r: r["score"], reverse=True)

weekly_html = (
    card("Average weekly / expiry-proxy", pct(weekly_s["avg"]))
    + card("Win rate", f"{safe(weekly_s['win'],1)}%")
    + card("Best", pct(weekly_s["best"]))
    + card("Worst", pct(weekly_s["worst"]))
)
gap_html = (
    card("Average gap", pct(gap_s["avg"]))
    + card("Gap volatility", f"{safe(gap_s['std'])}%")
    + card("Gap-up / positive sample", f"{safe(gap_s['win'],1)}%")
    + card("5-day average", pct(five_s["avg"]))
)

current_state = (
    f"<div class='state'><b>Current Nifty 50 state</b><div class='stategrid'>"
    f"<span>Close<b>{safe(current.Close)}</b></span>"
    f"<span>5D<b>{pct(current.ret5)}</b></span>"
    f"<span>RSI<b>{safe(current.RSI,1)}</b></span>"
    f"<span>Gap<b>{pct(current.gap)}</b></span>"
    f"<span>EMA20<b>{'Above' if current.Close > current.EMA20 else 'Below'}</b></span>"
    f"<span>EMA50<b>{'Above' if current.Close > current.EMA50 else 'Below'}</b></span>"
    f"</div></div>"
)

analogue_rows = "".join(
    f"<tr><td>{r.Index.strftime('%Y-%m-%d')}</td><td>{safe(r.ret5)}%</td><td>{safe(r.RSI,1)}</td>"
    f"<td>{safe(r.gap)}%</td><td>{safe(r.next5)}%</td><td>{safe(r.next20)}%</td></tr>"
    for r in analogues.itertuples()
)
outlier_rows = "".join(
    f"<tr><td>{r.Index.strftime('%Y-%m-%d')}</td><td>{safe(r.ret5)}%</td><td>{safe(r.RSI,1)}</td>"
    f"<td>{safe(r.gap)}%</td><td>{'Upside' if r.ret5 > 0 else 'Downside'}</td></tr>"
    for r in outliers.sort_index(ascending=False).itertuples()
)

stock_rows = "".join(
    f"<tr><td>{i}</td><td><b>{html.escape(str(r['name']))}</b></td><td>{html.escape(r['symbol'])}</td>"
    f"<td>{html.escape(r['sector'])}</td><td>{r['score']:.1f}</td><td>{r['action']}</td><td>₹{r['close']:.2f}</td>"
    f"<td>{r['ret20']:+.1f}%</td><td>{r['ret60']:+.1f}%</td><td>{r['rs60']:+.1f}pp</td><td>{r['rsi']:.1f}</td>"
    f"<td>{r['trend']}</td><td>{r['vol_ratio']:.2f}x</td><td>{r['atr_pct']:.2f}%</td>"
    f"<td>₹{r['stop']:.2f}</td><td>₹{r['target']:.2f}</td><td>1:{r['rr']:.1f}</td></tr>"
    for i, r in enumerate(ranked, 1)
)

top_cards = "".join(
    f"<article class='stock'><div class='head'><div><b>#{i}</b><h3>{html.escape(str(r['name']))}</h3>"
    f"<small>{r['cap']} • {r['sector']} • {r['action']}</small></div><strong>{r['score']:.0f}<small>/100</small></strong></div>"
    f"<div class='grid'><div>Price<br><b>₹{r['close']:.2f}</b></div><div>RSI<br><b>{r['rsi']:.1f}</b></div>"
    f"<div>3M return<br><b>{r['ret60']:+.1f}%</b></div><div>RS vs Nifty<br><b>{r['rs60']:+.1f}pp</b></div>"
    f"<div>Vol/20D<br><b>{r['vol_ratio']:.2f}x</b></div><div>ATR<br><b>{r['atr_pct']:.2f}%</b></div></div>"
    f"<p><b>Reference entry:</b> ₹{r['close']:.2f} • <b>Stop:</b> ₹{r['stop']:.2f} • <b>Target:</b> ₹{r['target']:.2f} • <b>R:R:</b> 1:{r['rr']:.1f}</p>"
    f"<p class='note'>Independent price/volume research only. This score is not copied from the Growth Radar.</p></article>"
    for i, r in enumerate(ranked[:10], 1)
)

page = f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Nifty & F&O Research</title><style>
:root{{--bg:#090e1a;--panel:#121a2c;--muted:#98a2b3;--text:#f8fafc;--line:#26334d;}}
*{{box-sizing:border-box}}body{{margin:0;background:linear-gradient(135deg,#090e1a,#111827);font-family:Inter,system-ui,sans-serif;color:var(--text)}}
header{{padding:24px 28px;border-bottom:1px solid var(--line);position:sticky;top:0;background:#0b1020ee;backdrop-filter:blur(12px);z-index:5}}
header h1{{margin:0 0 5px;font-size:28px}}header p{{margin:0;color:var(--muted);font-size:13px}}main{{max-width:1500px;margin:auto;padding:22px}}
.nav{{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 18px}}.nav a{{color:#dbeafe;text-decoration:none;border:1px solid var(--line);padding:8px 12px;border-radius:999px;font-size:12px}}
.badge{{display:inline-block;padding:6px 10px;border-radius:8px;background:#143326;color:#a7f3d0;font-size:11px;font-weight:800}}
.section{{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:18px;margin:14px 0;box-shadow:0 10px 30px #0003}}
.section h2{{margin:0 0 6px;font-size:20px}}.sub,.note{{color:var(--muted);font-size:12px;line-height:1.55}}.metrics{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}}
.metric{{background:#0d1526;border:1px solid var(--line);border-radius:12px;padding:13px}}.metric span,.metric small{{display:block;color:var(--muted);font-size:11px}}.metric strong{{display:block;font-size:24px;margin:5px 0}}
.state{{border:1px solid #1e4d66;background:#0c2030;border-radius:12px;padding:14px;margin-bottom:12px}}.stategrid{{display:grid;grid-template-columns:repeat(6,1fr);gap:8px;margin-top:10px}}.stategrid span{{font-size:11px;color:var(--muted);background:#091624;padding:9px;border-radius:8px}}.stategrid b{{display:block;color:var(--text);font-size:14px;margin-top:3px}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}}.stock{{background:#0d1526;border:1px solid var(--line);border-radius:14px;padding:15px}}
.head{{display:flex;justify-content:space-between}}.head h3{{margin:4px 0}}.head>strong{{font-size:30px}}.head small{{font-size:11px;color:#667085}}.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:6px}}.grid div{{background:#091424;padding:8px;border-radius:7px;font-size:10px;color:var(--muted)}}.grid b{{color:var(--text);font-size:13px}}
.tablewrap{{overflow:auto;border:1px solid var(--line);border-radius:10px}}table{{width:100%;border-collapse:collapse;min-width:1100px}}th,td{{padding:9px;border-bottom:1px solid var(--line);font-size:11px;text-align:left}}th{{color:#cbd5e1;background:#0c1424;position:sticky;top:77px}}
.warning{{color:#fde68a;background:#2b2410;border:1px solid #6b5718;padding:10px;border-radius:9px;font-size:11px}}
@media(max-width:850px){{.metrics{{grid-template-columns:repeat(2,1fr)}}.grid2{{grid-template-columns:1fr}}.stategrid{{grid-template-columns:repeat(2,1fr)}}}}
</style></head><body><header><h1>📊 Nifty & F&O Research</h1><p>Standalone historical research — Nifty behaviour, conditional analogues, gaps, outliers and independent F&O stock ranking</p></header>
<main><div class='nav'><a href='index.html'>← Main Dashboard</a><a href='news.html'>📰 News Intelligence</a><a href='research.html'>📊 Research</a><span class='badge'>Snapshot: {TODAY}</span></div>
<section class='section'><h2>① Overview</h2><div class='sub'>Independent source: Yahoo Finance daily OHLCV. This page does not read the Growth Radar's generated data or scores.</div>{current_state}<div class='metrics'>{weekly_html}</div></section>
<section class='section'><h2>② Expiry / Weekly Behaviour</h2><div class='sub'>Expiry proxy uses Thursday-to-Thursday before 1 Sep 2025 and Tuesday-to-Tuesday after the Nifty expiry weekday change.</div><div class='metrics'>{weekly_html}</div><p class='note'>Use the distribution, not just the average. A positive average can coexist with large downside tails.</p></section>
<section class='section'><h2>③ Intraday & Gap</h2><div class='sub'>V1 uses daily OHLCV for opening gaps and 5-session behaviour.</div><div class='metrics'>{gap_html}</div><p class='warning'>15-minute ORB is not included in this base section because the research page currently uses daily data. The ORB/options extension is added separately when its data source is available.</p></section>
<section class='section'><h2>④ Historical Analogues</h2><div class='sub'>Historical sessions most similar to the current Nifty state using 5-day return, RSI and opening gap. Next-5D and next-20D returns are descriptive historical outcomes, not predictions.</div><div class='tablewrap'><table><thead><tr><th>Date</th><th>5D</th><th>RSI</th><th>Gap</th><th>Next 5D</th><th>Next 20D</th></tr></thead><tbody>{analogue_rows}</tbody></table></div></section>
<section class='section'><h2>⑤ Outliers Distribution</h2><div class='sub'>The most recent historical observations outside the 2.5th / 97.5th percentile of 5-day returns.</div><div class='tablewrap'><table><thead><tr><th>Date</th><th>5D</th><th>RSI</th><th>Gap</th><th>Type</th></tr></thead><tbody>{outlier_rows}</tbody></table></div></section>
<section class='section'><h2>⑥ Independent F&O Stock Research</h2><div class='sub'>Separate price/volume ranking built directly from each stock's own Yahoo Finance history. No scores, recommendations or JSON from the Growth Radar are imported.</div><div class='cards'>{top_cards or '<div class="warning">No independent stock data was returned.</div>'}</div><div class='tablewrap' style='margin-top:14px'><table><thead><tr><th>#</th><th>Stock</th><th>Symbol</th><th>Sector</th><th>Score</th><th>Action</th><th>Price</th><th>20D</th><th>3M</th><th>RS vs Nifty</th><th>RSI</th><th>Trend</th><th>Vol/20D</th><th>ATR%</th><th>Stop</th><th>Target</th><th>R:R</th></tr></thead><tbody>{stock_rows}</tbody></table></div><p class='note'>The ranking is a research aid for multi-week candidates, not an automatic buy signal. Validate liquidity, earnings, corporate actions and risk before trading.</p></section>
<section class='section'><h2>V1 → V2 roadmap</h2><p class='note'>V2 adds independent intraday ORB analysis and current option-chain structure. Historical option IV/OI/expiry backtests require a dedicated historical derivatives dataset.</p></section>
<section class='section'><h2>Data quality</h2><p class='note'>Nifty sessions loaded: {len(idx):,}. Independent stock series loaded: {len(ranked)} / {len(stocks)}. Failed stock series: {len(failures)}. Research source: Yahoo Finance daily OHLCV.</p></section>
</main></body></html>"""

payload = {
    "date": TODAY,
    "source": "Yahoo Finance daily OHLCV",
    "nifty_rows": int(len(idx)),
    "stock_count": int(len(ranked)),
    "stock_failures": failures,
    "top_stocks": ranked[:20],
    "weekly": weekly_s,
    "gap": gap_s,
    "five_day": five_s,
}

(OUT / "research.html").write_text(page, encoding="utf-8")
(OUT / f"research-{TODAY}.html").write_text(page, encoding="utf-8")
(OUT / "research-latest.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
(OUT / f"research-{TODAY}.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
print(f"Generated standalone research.html; Nifty rows={len(idx)} stocks={len(ranked)} failures={len(failures)}")
