"""Extend the generated Research V1 page with intraday ORB and option-chain analytics."""
import json
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from intraday_options import collect_research_data

ROOT = Path(__file__).parent
OUT = ROOT / "docs"
TODAY = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")


def fmt(v, suffix="", digits=2):
    if v is None:
        return "—"
    try:
        return f"{float(v):.{digits}f}{suffix}"
    except Exception:
        return escape(str(v))


def card(label, value, sub=""):
    return f"<div class='metric'><span>{escape(label)}</span><strong>{escape(value)}</strong><small>{escape(sub)}</small></div>"


data = collect_research_data()

intraday_cards = []
orb_tables = []
for symbol in ["NIFTY", "BANKNIFTY"]:
    item = data["intraday"].get(symbol, {})
    orb = item.get("orb", {})
    if orb and orb.get("signals"):
        intraday_cards.append(card(f"{symbol} ORB signals", str(orb["signals"]), f"{orb.get('days', 0)} sessions"))
        intraday_cards.append(card(f"{symbol} ORB win rate", fmt(orb.get("win_rate"), "%", 1), "1R target / opening-range stop"))
        intraday_cards.append(card(f"{symbol} average R", fmt(orb.get("avg_r"), "R", 2), "first breakout only"))
        intraday_cards.append(card(f"{symbol} profit factor", fmt(orb.get("profit_factor"), "", 2), "positive R / negative R"))
        trades = orb.get("trades", [])
        rows = "".join(
            f"<tr><td>{escape(str(t.get('date')))}</td><td>{escape(str(t.get('side')))}</td><td>{escape(str(t.get('entry_time')))}</td>"
            f"<td>{fmt(t.get('entry'))}</td><td>{escape(str(t.get('outcome')))}</td><td>{fmt(t.get('r'), 'R')}</td></tr>"
            for t in trades
        ) or "<tr><td colspan='6'>No ORB signals in the returned intraday history.</td></tr>"
        orb_tables.append(
            f"<div><h3>{symbol} — latest ORB trades</h3><div class='tablewrap'><table><thead><tr>"
            f"<th>Date</th><th>Side</th><th>Entry</th><th>Price</th><th>Outcome</th><th>R</th></tr></thead><tbody>{rows}</tbody></table></div></div>"
        )
    else:
        reason = item.get("reason", "Intraday data unavailable")
        intraday_cards.append(card(f"{symbol} ORB", "Unavailable", reason[:70]))

option_blocks = []
for symbol in ["NIFTY", "BANKNIFTY"]:
    item = data["options"].get(symbol, {})
    if not item.get("available"):
        option_blocks.append(
            f"<div class='state'><b>{symbol} option chain unavailable</b><p class='note'>{escape(str(item.get('reason', 'No option-chain data returned.')))}</p></div>"
        )
        continue
    calls = item.get("call_walls", [])
    puts = item.get("put_walls", [])
    call_rows = "".join(f"<tr><td>{fmt(x.get('strike'))}</td><td>{fmt(x.get('oi'), '', 0)}</td><td>{fmt(x.get('volume'), '', 0)}</td><td>{fmt(x.get('iv') * 100 if x.get('iv') is not None else None, '%', 1)}</td></tr>" for x in calls)
    put_rows = "".join(f"<tr><td>{fmt(x.get('strike'))}</td><td>{fmt(x.get('oi'), '', 0)}</td><td>{fmt(x.get('volume'), '', 0)}</td><td>{fmt(x.get('iv') * 100 if x.get('iv') is not None else None, '%', 1)}</td></tr>" for x in puts)
    option_blocks.append(
        f"<div class='section'><h3>{symbol} — current option structure</h3>"
        f"<div class='metrics'>{card('Spot', fmt(item.get('underlying')))}{card('Expiry', str(item.get('expiry') or '—'))}"
        f"{card('ATM', fmt(item.get('atm')))}{card('PCR (OI)', fmt(item.get('pcr_oi'), '', 2))}{card('Max pain', fmt(item.get('max_pain')))}</div>"
        f"<div class='grid2'><div><h3>Top Call OI walls</h3><div class='tablewrap'><table><thead><tr><th>Strike</th><th>OI</th><th>Volume</th><th>IV</th></tr></thead><tbody>{call_rows}</tbody></table></div></div>"
        f"<div><h3>Top Put OI walls</h3><div class='tablewrap'><table><thead><tr><th>Strike</th><th>OI</th><th>Volume</th><th>IV</th></tr></thead><tbody>{put_rows}</tbody></table></div></div></div>"
        f"<p class='note'>This is a current-chain snapshot, not historical option-chain data. OI walls are descriptive and are not automatically treated as support/resistance.</p></div>"
    )

section = f"""
<section class='section' id='intraday-options'><h2>⑦ Intraday ORB & Options</h2>
<div class='sub'>15-minute opening-range breakout backtest plus the latest available option-chain snapshot. Intraday history comes from Yahoo Finance; option-chain availability depends on Yahoo exposing NSE contracts.</div>
<div class='metrics'>{''.join(intraday_cards)}</div>
<div class='grid2'>{''.join(orb_tables) if orb_tables else '<div class="state"><b>No intraday ORB results</b></div>'}</div>
<div class='note' style='margin-top:12px'><b>ORB definition:</b> first 15-minute range (09:15–09:30 IST); first subsequent candle close outside the range is the signal; opposite range edge is the stop; 1R is the range width. If target and stop occur in the same candle, the backtest uses the conservative stop outcome.</div>
</section>
{''.join(option_blocks)}
<section class='section'><h2>Data limitations</h2><p class='note'>Yahoo Finance provides the intraday price history used here and may expose an NSE option chain only for some contracts/expiries. We do not manufacture missing option data. Historical option-premium decay, IV/OI change and expiry-by-expiry option backtests require a proper historical derivatives dataset or broker/data-vendor feed and will be added as a separate data connector.</p></section>
"""

path = OUT / "research.html"
if path.exists():
    page = path.read_text(encoding="utf-8")
    marker = "<section class='section'><h2>V1 → V2 roadmap</h2>"
    if marker in page:
        page = page.replace(marker, section + marker, 1)
    elif "id='intraday-options'" not in page:
        page = page.replace("</main></body></html>", section + "</main></body></html>")
    path.write_text(page, encoding="utf-8")

payload_path = OUT / "research-latest.json"
base = json.loads(payload_path.read_text(encoding="utf-8")) if payload_path.exists() else {"date": TODAY}
base["intraday_orb_options"] = data
payload_path.write_text(json.dumps(base, indent=2, default=str), encoding="utf-8")
(OUT / f"research-{TODAY}.json").write_text(json.dumps(base, indent=2, default=str), encoding="utf-8")
print("Research V2 intraday/options extension generated")
