# Enhanced daily swing radar. Generates latest + dated HTML snapshots and machine-readable data.
import html
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from market_data import fetch
from screener_fundamentals import fetch as fund
from technical_engine import calculate

ROOT = Path(__file__).parent
OUT = ROOT / "docs"
OUT.mkdir(exist_ok=True)
stocks = pd.read_csv(ROOT / "stocks.csv")
rows = []
failures = []

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


def num(value):
    try:
        return float(str(value).replace(",", "").replace("%", "").replace("x", "").replace("₹", "").strip())
    except Exception:
        return None


def first_num(data, *keys):
    for actual, value in (data or {}).items():
        low = str(actual).lower().replace(" ", "")
        if any(k.lower().replace(" ", "") in low for k in keys):
            parsed = num(value)
            if parsed is not None:
                return parsed
    return None


def fundamentals(data):
    return {
        "pe": first_num(data, "Stock P/E", "P/E", "Price to Earning"),
        "pb": first_num(data, "Price to book", "P/B"),
        "roe": first_num(data, "Return on equity", "ROE"),
        "roce": first_num(data, "Return on capital employed", "ROCE"),
        "de": first_num(data, "Debt to equity", "Debt/Eq", "D/E"),
        "current": first_num(data, "Current ratio"),
        "sales_growth": first_num(data, "Sales growth", "Revenue growth", "YOY Quarterly sales"),
        "pat_growth": first_num(data, "Profit growth", "PAT growth", "YOY Quarterly profit"),
        "eps_growth": first_num(data, "EPS growth"),
        "op_margin": first_num(data, "OPM", "Operating profit margin"),
        "cfo": first_num(data, "Cash from operating activity", "Cash from operating activities", "Operating cash flow"),
        "capex": first_num(data, "Fixed assets purchased", "Capital expenditure", "Capex"),
        "fcf": first_num(data, "Free cash flow"),
        "cfo_pat": first_num(data, "CFO/PAT", "Cash flow to profit"),
        "interest": first_num(data, "Interest coverage"),
    }


def clamp(value, low=0.0, high=1.0):
    return max(low, min(high, value))


def score(t, f, market_ok, rs3, sector_rs):
    trend = 15 if t["trend"] == "Bullish alignment" else 11 if t["trend"] == "Improving" else 5 if t["trend"] == "Mixed" else 0
    rs = 15 * (
        0.55 * clamp((rs3 + 10) / 35)
        + 0.25 * clamp((t["ret1m"] + 5) / 20)
        + 0.20 * clamp((t["ret6m"] + 5) / 45)
    )
    rs = max(0, min(15, rs + 2 * clamp((sector_rs + 5) / 25)))
    breakout = 15 if t["breakout20"] and t["vol_ratio"] >= 1.5 else 12 if t["breakout20"] else 9 if t["close"] > t["high50"] else 4
    volume = 10 if t["vol_ratio"] >= 2 else 8 if t["vol_ratio"] >= 1.5 else 5 if t["vol_ratio"] >= 1.2 else 2
    r = t["rsi"]
    rsi_score = 7 if 55 <= r <= 68 else 5 if 48 <= r < 55 or 68 < r <= 75 else 2
    macd = 5 if t["macd_status"] == "Bullish" and t["macd_hist_rising"] else 3 if t["macd_status"] == "Bullish" else 1
    adx_score = 5 if t["adx"] >= 25 and t["adx_rising"] else 4 if t["adx"] >= 20 else 2
    earnings = 8 if f["eps_growth"] is not None and f["eps_growth"] >= 15 and f["sales_growth"] is not None and f["sales_growth"] >= 10 else 6 if f["eps_growth"] is not None and f["eps_growth"] >= 10 else 3
    quality = (2 if f["roe"] is not None and f["roe"] >= 15 else 1) + (2 if f["roce"] is not None and f["roce"] >= 15 else 1) + (1 if f["de"] is None or f["de"] <= 0.5 else 0)
    distance = (t["close"] / t["ema20"] - 1) * 100
    entry = 5 if 0 <= distance <= 5 and r <= 72 else 4 if distance <= 8 and r <= 75 else 2 if distance <= 12 else 0
    if not market_ok:
        trend *= 0.65
        rs *= 0.75
    return round(min(100, trend + rs + breakout + volume + rsi_score + macd + adx_score + earnings + quality + entry), 1)


def classify(t, s):
    distance = (t["close"] / t["ema20"] - 1) * 100
    if s >= 85 and t["rsi"] <= 72 and distance <= 5:
        return "HIGH-CONVICTION SWING"
    if s >= 75 and (t["rsi"] > 72 or distance > 5):
        return "BUY ON PULLBACK"
    if s >= 75:
        return "BUY / CONFIRMATION"
    if s >= 65:
        return "WATCH"
    if s >= 55:
        return "WEAK WATCH"
    return "AVOID"


def reasons(t, f, rs3, sector_rs, market_ok):
    items = ["Market regime supportive" if market_ok else "Market regime cautious — reduced score"]
    if t["trend"] == "Bullish alignment":
        items.append("Price above EMA20/50/200")
    if t["breakout20"] and t["vol_ratio"] >= 1.5:
        items.append("20D breakout with strong volume")
    if rs3 > 10:
        items.append(f"Strong vs universe 3M ({rs3:+.1f}pp)")
    if sector_rs > 10:
        items.append(f"Strong vs sector peers ({sector_rs:+.1f}pp)")
    if t["adx"] >= 25 and t["adx_rising"]:
        items.append("ADX >25 and rising")
    if t["rsi"] > 75:
        items.append("RSI highly extended — avoid chasing")
    elif t["rsi"] > 70:
        items.append("RSI extended — prefer pullback")
    if t["macd_status"] == "Bullish" and t["macd_hist_rising"]:
        items.append("MACD momentum improving")
    if f["roe"] is not None and f["roe"] >= 15:
        items.append(f"ROE {f['roe']:.1f}%")
    if f["roce"] is not None and f["roce"] >= 15:
        items.append(f"ROCE {f['roce']:.1f}%")
    if f["fcf"] is not None and f["fcf"] > 0:
        items.append("Positive free cash flow")
    return items[:5]


def display_num(f, *keys):
    value = first_num(f, *keys)
    return "N/A" if value is None else f"{value:.2f}"


# Fetch the benchmark first. If free index data is unavailable, use large-cap breadth.
market_t = None
for symbol in ("NIFTY 50", "NIFTY50", "NIFTY"):
    try:
        market_t = calculate(fetch(symbol)[0])
        break
    except Exception:
        continue

for _, stock in stocks.iterrows():
    symbol = str(stock.nse_symbol).strip()
    try:
        technical = calculate(fetch(symbol)[0])
        try:
            raw_fundamentals = fund(str(stock.screener_symbol).strip())
        except Exception as exc:
            raw_fundamentals = {"_error": f"{type(exc).__name__}: {exc}"}
        rows.append({
            **stock.to_dict(),
            "sector": SECTORS.get(symbol, "Other"),
            "t": technical,
            "f": fundamentals(raw_fundamentals),
        })
    except Exception as exc:
        failures.append({
            "name": stock["name"],
            "symbol": symbol,
            "error": f"{type(exc).__name__}: {exc}",
        })

if market_t:
    market_ok = market_t["close"] > market_t["ema50"] and market_t["ema50"] > market_t["ema200"] and market_t["rsi"] >= 50
    market_label = "Bullish" if market_ok else "Cautious/Bearish"
else:
    large = [r for r in rows if r["cap"] == "Large"]
    bull = sum(r["t"]["close"] > r["t"]["ema50"] for r in large)
    market_ok = bull / max(1, len(large)) >= 0.55
    market_label = f"Breadth proxy {bull}/{len(large)} above EMA50"

benchmark3 = sum(r["t"]["ret3m"] for r in rows) / max(1, len(rows))
sector_returns = {}
for row in rows:
    sector_returns.setdefault(row["sector"], []).append(row["t"]["ret3m"])

for row in rows:
    rs3 = row["t"]["ret3m"] - benchmark3
    peers = sector_returns[row["sector"]]
    peer_values = [v for v in peers if v != row["t"]["ret3m"]]
    sector_rs = row["t"]["ret3m"] - (sum(peer_values) / max(1, len(peer_values)))
    s = score(row["t"], row["f"], market_ok, rs3, sector_rs)
    stop = min(row["t"]["support"], row["t"]["close"] - 1.5 * row["t"]["atr"])
    rr = 1.8 if s >= 85 else 1.5
    target = row["t"]["close"] + (row["t"]["close"] - stop) * rr
    row.update(
        score=s,
        rec=classify(row["t"], s),
        horizon="2-8 weeks" if s >= 75 else "1-4 weeks" if s >= 65 else "observe",
        stop=stop,
        target=target,
        rr=rr,
        rs3=rs3,
        sector_rs=sector_rs,
        reasons=reasons(row["t"], row["f"], rs3, sector_rs, market_ok),
    )

rows.sort(key=lambda r: r["score"], reverse=True)
today = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")

def snapshot_stock(row):
    return {
        "name": row["name"], "nse_symbol": row["nse_symbol"], "cap": row["cap"], "sector": row["sector"],
        "score": row["score"], "rec": row["rec"], "horizon": row["horizon"], "stop": row["stop"],
        "target": row["target"], "rr": row["rr"], "rs3": row["rs3"], "sector_rs": row["sector_rs"],
        "reasons": row["reasons"], "technical": row["t"], "fundamentals": row["f"],
    }

snapshot = {
    "date": today,
    "generated_utc": datetime.now(timezone.utc).isoformat(),
    "market_regime": market_label,
    "stocks": [snapshot_stock(r) for r in rows],
    "failures": failures,
}
(OUT / f"data-{today}.json").write_text(json.dumps(snapshot, default=str, indent=2), encoding="utf-8")

cards = []
for rank, row in enumerate(rows[:12], 1):
    t, f = row["t"], row["f"]
    name = html.escape(str(row["name"]))
    why = html.escape("; ".join(row["reasons"]))
    roe = display_num(f, "Return on equity", "ROE")
    roce = display_num(f, "Return on capital employed", "ROCE")
    cards.append(
        f"<article class='stock'><div class='head'><div><b>#{rank}</b><h3>{name}</h3>"
        f"<small>{row['cap']} • {row['sector']} • {row['horizon']}</small></div>"
        f"<strong>{row['score']}<small>/100</small></strong></div>"
        f"<div class='rec'>{row['rec']}</div><div class='grid'>"
        f"<div>Price<br><b>₹{t['close']:.2f}</b></div><div>RSI<br><b>{t['rsi']:.1f}</b></div>"
        f"<div>ADX<br><b>{t['adx']:.1f}</b></div><div>Vol<br><b>{t['vol_ratio']:.2f}x</b></div>"
        f"<div>RS vs Universe<br><b>{row['rs3']:+.1f}pp</b></div><div>RS vs Sector<br><b>{row['sector_rs']:+.1f}pp</b></div>"
        f"<div>ROE<br><b>{roe}</b></div><div>ROCE<br><b>{roce}</b></div></div>"
        f"<p><b>Entry:</b> ₹{t['close']:.2f} • <b>Stop:</b> ₹{row['stop']:.2f} • "
        f"<b>Target:</b> ₹{row['target']:.2f} • <b>R:R:</b> 1:{row['rr']:.1f}</p>"
        f"<p class='why'><b>Why:</b> {why}</p></article>"
    )

trs = []
for rank, row in enumerate(rows, 1):
    t, f = row["t"], row["f"]
    cells = [
        str(rank), row["cap"], row["sector"], html.escape(str(row["name"])), f"{row['score']:.1f}", row["rec"], row["horizon"],
        f"{t['close']:.2f}", f"{row['rs3']:+.1f}%", f"{row['sector_rs']:+.1f}%", f"{t['rsi']:.1f}", t["trend"],
        f"{t['adx']:.1f}", f"{t['vol_ratio']:.2f}x", f"{t['atr_pct']:.2f}%",
        display_num(f, "Price to Earning", "P/E"), display_num(f, "Price to book", "P/B"),
        display_num(f, "Return on equity", "ROE"), display_num(f, "Return on capital employed", "ROCE"),
        display_num(f, "Debt to equity", "Debt/Eq", "D/E"), display_num(f, "Sales growth", "Revenue growth"),
        display_num(f, "Profit growth", "PAT growth"), display_num(f, "EPS growth"),
        display_num(f, "Cash from operating activity", "Operating cash flow"), display_num(f, "Free cash flow"),
        f"{row['stop']:.2f}", f"{row['target']:.2f}", f"1:{row['rr']:.1f}", html.escape("; ".join(row["reasons"])),
    ]
    trs.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")

page = f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Nifty Swing Growth Radar {today}</title><style>
body{{font-family:system-ui;margin:0;background:#f3f6fa;color:#172033}}header{{background:#17365d;color:white;padding:22px}}
main{{max-width:2200px;margin:auto;padding:14px}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px}}
.card,.stock{{background:white;border-radius:15px;padding:15px;margin:12px 0;box-shadow:0 2px 9px #0001}}
.head{{display:flex;justify-content:space-between}}.head h3{{margin:4px 0}}.head>strong{{font-size:30px}}.head small{{font-size:11px;color:#667085}}
.rec{{font-weight:800;margin:8px 0;padding:7px;background:#eef8f0;border-radius:8px;display:inline-block}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:6px}}.grid div{{background:#f7f9fb;padding:7px;border-radius:7px;font-size:11px}}
.why,.note{{font-size:12px;color:#667085}}table{{border-collapse:collapse;width:100%;min-width:2800px}}th,td{{padding:7px;border-bottom:1px solid #ddd;font-size:11px;text-align:left}}
th{{background:#17365d;color:white;position:sticky;top:0}}.tablewrap{{overflow:auto}}@media(max-width:600px){{.grid{{grid-template-columns:repeat(2,1fr)}}}}
</style></head><body><header><h1>📈 Nifty Swing Growth Radar</h1>
<div>{today} • Daily 4 PM IST • Multi-factor swing screen</div></header><main>
<div class='cards'><div class='card'><b>Market regime</b><h2>{market_label}</h2><p class='note'>NIFTY trend filter when index data is available; otherwise breadth proxy.</p></div>
<div class='card'><b>Universe</b><h2>{len(rows)} stocks</h2><p class='note'>{len(failures)} data failures • missing values are not fabricated.</p></div>
<div class='card'><b>High conviction</b><h2>{sum(r['score'] >= 85 for r in rows)}</h2></div>
<div class='card'><b>Signal philosophy</b><p class='note'>Strong trend + relative strength + breakout/volume + earnings/quality + controlled entry. RSI alone never triggers BUY.</p></div></div>
<h2>🔥 Top swing candidates</h2><div class='cards'>{''.join(cards)}</div>
<div class='card'><h2>Full universe</h2><div class='tablewrap'><table><thead><tr>
<th>#</th><th>Cap</th><th>Sector</th><th>Stock</th><th>Score</th><th>Action</th><th>Horizon</th><th>Price</th><th>RS vs U</th><th>RS vs Sector</th><th>RSI</th><th>Trend</th><th>ADX</th><th>Vol/20D</th><th>ATR%</th><th>P/E</th><th>P/B</th><th>ROE</th><th>ROCE</th><th>D/E</th><th>Sales Growth</th><th>PAT Growth</th><th>EPS Growth</th><th>CFO</th><th>FCF</th><th>Stop</th><th>Target</th><th>R:R</th><th>Why</th>
</tr></thead><tbody>{''.join(trs)}</tbody></table></div></div>
<div class='card'><p class='note'>Data snapshot: <a href='data-{today}.json'>data-{today}.json</a>. This is a screening system, not a guarantee of returns. Validate execution, liquidity, corporate events and slippage before trading.</p></div>
</main></body></html>"""

(OUT / "index.html").write_text(page, encoding="utf-8")
(OUT / f"{today}.html").write_text(page, encoding="utf-8")
pd.DataFrame(failures).to_csv(OUT / f"failures-{today}.csv", index=False)
print(f"Generated latest + {today}.html + data-{today}.json; stocks={len(rows)} failures={len(failures)}")
