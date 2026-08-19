import html
from pathlib import Path
import pandas as pd
from market_data import fetch
from screener_fundamentals import fetch as fund
from technical_engine import calculate

ROOT = Path(__file__).parent
OUT = ROOT / 'docs'
OUT.mkdir(exist_ok=True)
stocks = pd.read_csv(ROOT / 'stocks.csv')
rows, failures = [], []

def num(v):
    try: return float(str(v).replace(',', '').replace('%', '').replace('x', '').strip())
    except Exception: return None

def first_num(data, *keys):
    if not data: return None
    for key in keys:
        if key in data:
            v=num(data.get(key))
            if v is not None: return v
    for actual,value in data.items():
        low=str(actual).lower()
        if any(k.lower() in low for k in keys):
            v=num(value)
            if v is not None: return v
    return None

def pct_growth(v):
    return num(v)

def scores(t,f):
    roe=first_num(f,'Return on equity','ROE'); roce=first_num(f,'Return on capital employed','ROCE')
    pe=first_num(f,'Price to Earning','P/E','Price/Earnings')
    de=first_num(f,'Debt to equity','Debt/Equity','D/E')
    op=first_num(f,'Operating Profit','Operating profit')
    # Fundamental quality / valuation (35)
    fundamental = (8 if roe is not None and roe>=18 else 6 if roe is not None and roe>=12 else 2 if roe is not None else 0)
    fundamental += (8 if roce is not None and roce>=18 else 6 if roce is not None and roce>=12 else 2 if roce is not None else 0)
    fundamental += (5 if de is not None and de<0.5 else 3 if de is not None and de<1 else 1 if de is not None else 0)
    fundamental += (5 if pe is not None and 0<pe<35 else 3 if pe is not None and pe<60 else 1 if pe is not None else 0)
    fundamental += 4 if op is not None else 0
    fundamental=min(35,fundamental)
    # Technical trend / momentum (35)
    technical=(10 if t['trend']=='Bullish alignment' else 7 if t['trend']=='Improving' else 3 if t['trend']=='Mixed' else 0)
    technical += 7 if t['close']>t['ema200'] else 2
    technical += 6 if t['macd_hist']>0 else 1
    technical += 6 if t['adx']>=25 else 4 if t['adx']>=18 else 1
    technical += 6 if 45<=t['rsi']<=68 else 4 if 68<t['rsi']<=75 else 2
    technical=min(35,technical)
    # Relative strength / volume / breakout (20)
    momentum=(6 if t['ret1m']>0 else 1)+(6 if t['ret3m']>0 else 1)+(4 if t['ret1y']>0 else 1)+(4 if t['vol_ratio']>=1.2 else 2)
    momentum=min(20,momentum)
    # Entry/risk quality (10): reward orderly entries, penalize extreme extension
    entry=6 if t['dist_high']>-15 else 4
    if t['rsi']>75: entry-=3
    if t['atr_pct']>6: entry-=2
    if t['close']>t['ema20']*1.08: entry-=2
    entry=max(0,min(10,entry))
    overall=round(fundamental+technical+momentum+entry,1)
    if overall>=82 and entry>=6: rec='BUY NOW'
    elif overall>=70: rec='BUY ON PULLBACK'
    elif overall>=55: rec='WATCH'
    elif overall>=45: rec='HIGH RISK / MOMENTUM'
    else: rec='AVOID'
    horizon='3-6 months' if overall>=82 else '1-3 months' if overall>=65 else '2-6 weeks'
    return fundamental,technical,momentum,entry,overall,rec,horizon

for _,x in stocks.iterrows():
    symbol=str(x.nse_symbol).strip()
    try:
        df,source=fetch(symbol); t=calculate(df)
        try: f=fund(str(x.screener_symbol).strip())
        except Exception as exc: f={'_error':f'{type(exc).__name__}: {exc}'}
        fs,ts,ms,es,overall,rec,horizon=scores(t,f)
        rows.append({**x.to_dict(),'t':t,'f':f,'fund_score':fs,'tech_score':ts,'momentum_score':ms,'entry_score':es,'score':overall,'rec':rec,'horizon':horizon,'source':source})
    except Exception as exc: failures.append({'name':x['name'],'symbol':symbol,'error':f'{type(exc).__name__}: {exc}'})
rows.sort(key=lambda r:r['score'],reverse=True)

def val(f,*keys):
    v=first_num(f,*keys); return 'N/A' if v is None else f'{v:.2f}'

def reasons(r):
    t=r['t']; f=r['f']; out=[]
    if t['trend']=='Bullish alignment': out.append('Price above EMA20 > EMA50 > EMA200')
    if t['ret3m']>10: out.append(f'Strong 3M momentum {t["ret3m"]:.1f}%')
    if t['vol_ratio']>=1.2: out.append(f'Volume {t["vol_ratio"]:.1f}x 20D average')
    if t['adx']>=25: out.append(f'ADX {t["adx"]:.0f} confirms trend strength')
    roe=first_num(f,'Return on equity','ROE'); roce=first_num(f,'Return on capital employed','ROCE')
    if roe is not None and roe>=18: out.append(f'ROE {roe:.1f}%')
    if roce is not None and roce>=18: out.append(f'ROCE {roce:.1f}%')
    if t['rsi']>70: out.append('RSI extended — avoid chasing')
    return out[:4] or ['Mixed setup; wait for confirmation']

cards=[]
for i,r in enumerate(rows[:12],1):
    t,f=r['t'],r['f']; cls='buy' if r['rec'].startswith('BUY') else 'avoid' if r['rec']=='AVOID' else 'watch'
    rs='; '.join(reasons(r))
    cards.append(f'''<article class="stock {cls}"><div class="stockhead"><div><span class="rank">#{i}</span><h3>{html.escape(str(r['name']))}</h3><span>{r['cap']} • {r['horizon']}</span></div><div class="score">{r['score']}<small>/100</small></div></div><div class="rec">{r['rec']}</div><div class="bars"><span>Fundamental <b>{r['fund_score']}</b>/35</span><span>Technical <b>{r['tech_score']}</b>/35</span><span>Momentum <b>{r['momentum_score']}</b>/20</span><span>Entry <b>{r['entry_score']}</b>/10</span></div><div class="grid"><div>Price <b>₹{t['close']:.2f}</b></div><div>RSI <b>{t['rsi']:.1f}</b></div><div>ADX <b>{t['adx']:.1f}</b></div><div>ATR <b>{t['atr_pct']:.2f}%</b></div><div>1M <b>{t['ret1m']:.1f}%</b></div><div>3M <b>{t['ret3m']:.1f}%</b></div><div>1Y <b>{t['ret1y']:.1f}%</b></div><div>Vol <b>{t['vol_ratio']:.2f}x</b></div></div><div class="why"><b>Why:</b> {html.escape(rs)}</div><div class="funds"><b>ROE</b> {val(f,'Return on equity','ROE')} &nbsp; <b>ROCE</b> {val(f,'Return on capital employed','ROCE')} &nbsp; <b>P/E</b> {val(f,'Price to Earning','P/E')} &nbsp; <b>D/E</b> {val(f,'Debt to equity','Debt/Equity','D/E')}</div></article>''')

trs=[]
for i,r in enumerate(rows,1):
    t,f=r['t'],r['f']; cls='buy' if r['rec'].startswith('BUY') else 'avoid' if r['rec']=='AVOID' else 'watch'
    trs.append(f'''<tr><td>{i}</td><td>{html.escape(str(r['cap']))}</td><td><b>{html.escape(str(r['name']))}</b></td><td><b>{r['score']}</b></td><td>{r['fund_score']}/35</td><td>{r['tech_score']}/35</td><td>{r['momentum_score']}/20</td><td>{r['entry_score']}/10</td><td class="{cls}">{r['rec']}</td><td>{r['horizon']}</td><td>₹{t['close']:.2f}</td><td>{t['rsi']:.1f}</td><td>{t['trend']}</td><td>{t['adx']:.1f}</td><td>{t['vol_ratio']:.2f}x</td><td>{t['ret1m']:.1f}% / {t['ret3m']:.1f}% / {t['ret1y']:.1f}%</td><td>{val(f,'Price to Earning','P/E')}</td><td>{val(f,'Return on equity','ROE')}</td><td>{val(f,'Return on capital employed','ROCE')}</td><td>{t['w52']}</td></tr>''')

page='''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Nifty Growth Radar</title><style>
body{font-family:system-ui,-apple-system,sans-serif;margin:0;background:#f3f6fa;color:#172033}header{background:#17365d;color:white;padding:24px}main{max-width:1800px;margin:auto;padding:16px}.card{background:#fff;border-radius:16px;padding:18px;margin:14px 0;box-shadow:0 2px 10px #0000000d}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:14px}.stock{border:1px solid #dbe2ea;border-radius:14px;padding:16px}.stockhead{display:flex;justify-content:space-between;align-items:flex-start}.stock h3{margin:5px 0;font-size:18px}.rank{color:#667085;font-size:12px}.score{font-size:30px;font-weight:800}.score small{font-size:13px;color:#667085}.rec{display:inline-block;padding:6px 9px;border-radius:8px;font-weight:800;margin:8px 0}.buy .rec{background:#e8f7ed;color:#087f23}.watch .rec{background:#fff4d6;color:#946200}.avoid .rec{background:#feeceb;color:#b42318}.bars{display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:11px;margin:8px 0}.bars span{background:#f5f7fa;padding:7px;border-radius:7px}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;font-size:11px}.grid div{background:#f7f9fb;padding:7px;border-radius:7px}.grid b{display:block;font-size:13px}.why{margin-top:10px;font-size:12px;line-height:1.5}.funds{margin-top:10px;padding-top:9px;border-top:1px solid #eee;font-size:11px}.funds b{color:#475467}table{border-collapse:collapse;width:100%;min-width:1800px}th,td{padding:7px;border-bottom:1px solid #e5e7eb;font-size:11px;text-align:left}th{background:#17365d;color:white;position:sticky;top:0}.buy{font-weight:800;color:#087f23}.watch{font-weight:800;color:#946200}.avoid{font-weight:800;color:#b42318}.note{color:#667085;font-size:12px}.legend{display:flex;gap:12px;flex-wrap:wrap;font-size:12px}.pill{padding:6px 10px;border-radius:20px;background:#eef2f6}@media(max-width:600px){header{padding:18px}.grid{grid-template-columns:repeat(2,1fr)}.bars{grid-template-columns:1fr}.cards{grid-template-columns:1fr}}</style></head><body><header><h1>📊 Nifty Growth Radar</h1><div>Multi-factor stock research • technical + fundamentals + momentum + entry quality</div></header><main><div class="card"><h2>🏆 Top opportunities</h2><div class="legend"><span class="pill">🟢 BUY NOW</span><span class="pill">🟢 BUY ON PULLBACK</span><span class="pill">🟡 WATCH</span><span class="pill">🔴 AVOID</span></div><p class="note">Overall score: Fundamentals 35 + Technical 35 + Momentum 20 + Entry/Risk 10. RSI is a context signal, not a standalone buy/sell trigger.</p></div><div class="cards">'''+''.join(cards)+'''</div><div class="card"><h2>📋 Full 60-stock ranking</h2><div style="overflow:auto"><table><thead><tr><th>#</th><th>Cap</th><th>Stock</th><th>Total</th><th>Fund/35</th><th>Tech/35</th><th>Mom/20</th><th>Entry/10</th><th>Action</th><th>Horizon</th><th>Price</th><th>RSI</th><th>Trend</th><th>ADX</th><th>Vol/20D</th><th>1M/3M/1Y</th><th>P/E</th><th>ROE</th><th>ROCE</th><th>52W</th></tr></thead><tbody>'''+''.join(trs)+'''</tbody></table></div></div><div class="card"><p class="note">Generated automatically from NSE market data via OpenChart/jugaad-data fallback and Screener financial data. Missing values remain N/A. Research tool only; not personalized investment advice.</p></div></main></body></html>'''
(OUT/'index.html').write_text(page,encoding='utf-8')
pd.DataFrame(failures).to_csv(OUT/'failures.csv',index=False)
print(f'Generated {len(rows)} stocks; failures={len(failures)}')
