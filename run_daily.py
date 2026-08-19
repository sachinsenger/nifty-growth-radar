import html
from pathlib import Path
import pandas as pd
from market_data import fetch
from screener_fundamentals import fetch as fund
from technical_engine import calculate
ROOT=Path(__file__).parent; OUT=ROOT/'docs'; OUT.mkdir(exist_ok=True)
stocks=pd.read_csv(ROOT/'stocks.csv'); rows=[]; failures=[]
def num(v):
    try:return float(str(v).replace(',','').replace('%','').replace('x','').strip())
    except:return None
def first_num(data,*keys):
    if not data:return None
    for actual,value in data.items():
        if any(k.lower() in str(actual).lower() for k in keys):
            z=num(value)
            if z is not None:return z
    return None
def clamp(x):return max(0,min(1,x))
def swing_score(t,f):
    trend=15 if t['trend']=='Bullish alignment' else 11 if t['trend']=='Improving' else 5 if t['trend']=='Mixed' else 0
    rel=15*(.45*clamp(t['ret3m']/25)+.30*clamp(t['ret1m']/10)+.25*clamp(t['ret6m']/40))
    breakout=15 if t['breakout20'] and t['vol_ratio']>=1.5 else 12 if t['breakout20'] else 9 if t['close']>t['high50'] else 4
    volume=10 if t['vol_ratio']>=2 else 8 if t['vol_ratio']>=1.5 else 5 if t['vol_ratio']>=1.2 else 2
    r=t['rsi']; rsi=7 if 55<=r<=68 else 5 if 48<=r<55 or 68<r<=75 else 2
    macd=5 if t['macd_status']=='Bullish' and t['macd_hist_rising'] else 3 if t['macd_status']=='Bullish' else 1
    adx=5 if t['adx']>=25 and t['adx_rising'] else 4 if t['adx']>=20 else 2
    eps=first_num(f,'Profit after tax','PAT','EPS growth'); rev=first_num(f,'Sales growth','Revenue growth')
    earnings=8 if eps is not None and eps>=15 and rev is not None and rev>=10 else 6 if eps is not None and eps>=10 else 3
    roe=first_num(f,'Return on equity','ROE'); roce=first_num(f,'Return on capital employed','ROCE'); de=first_num(f,'Debt to equity','Debt/Equity','D/E')
    quality=(2 if roe is not None and roe>=15 else 1)+(2 if roce is not None and roce>=15 else 1)+(1 if de is None or de<=.5 else 0)
    dist=(t['close']/t['ema20']-1)*100; entry=5 if 0<=dist<=5 and r<=72 else 4 if dist<=8 and r<=75 else 2 if dist<=12 else 0
    return round(min(100,trend+rel+breakout+volume+rsi+macd+adx+earnings+quality+entry),1)
def classify(t,s):
    dist=(t['close']/t['ema20']-1)*100
    if s>=85 and t['rsi']<=72 and dist<=5:return 'HIGH-CONVICTION SWING'
    if s>=75 and (t['rsi']>72 or dist>5):return 'BUY ON PULLBACK'
    if s>=75:return 'BUY / CONFIRMATION'
    if s>=65:return 'WATCH'
    if s>=55:return 'WEAK WATCH'
    return 'AVOID'
def reasons(t,f):
    a=[]
    if t['trend']=='Bullish alignment':a.append('Price above EMA20 > EMA50 > EMA200')
    if t['breakout20'] and t['vol_ratio']>=1.5:a.append('20D breakout with strong volume')
    if t['ret3m']>20:a.append(f'Strong 3M momentum {t["ret3m"]:.1f}%')
    if t['adx']>=25 and t['adx_rising']:a.append('ADX >25 and rising')
    if t['rsi']>75:a.append('RSI highly extended — avoid chasing')
    elif t['rsi']>70:a.append('RSI extended — prefer pullback')
    if t['macd_status']=='Bullish' and t['macd_hist_rising']:a.append('MACD momentum improving')
    roe=first_num(f,'Return on equity','ROE'); roce=first_num(f,'Return on capital employed','ROCE')
    if roe is not None and roe>=15:a.append(f'ROE {roe:.1f}%')
    if roce is not None and roce>=15:a.append(f'ROCE {roce:.1f}%')
    return a[:5] or ['Mixed setup; wait for confirmation']
for _,x in stocks.iterrows():
    try:
        df,source=fetch(str(x.nse_symbol).strip()); t=calculate(df)
        try:f=fund(str(x.screener_symbol).strip())
        except Exception as e:f={'_error':f'{type(e).__name__}: {e}'}
        s=swing_score(t,f); rec=classify(t,s); horizon='2-8 weeks' if s>=75 else '1-4 weeks' if s>=65 else 'observe'
        stop=min(t['support'],t['close']-1.5*t['atr']); target=t['close']+(t['close']-stop)*(1.8 if s>=85 else 1.5)
        rows.append({**x.to_dict(),'t':t,'f':f,'score':s,'rec':rec,'horizon':horizon,'stop':stop,'target':target,'reasons':reasons(t,f),'source':source})
    except Exception as e:failures.append({'name':x['name'],'symbol':x['nse_symbol'],'error':f'{type(e).__name__}: {e}'})
rows.sort(key=lambda r:r['score'],reverse=True)
def val(f,*keys):
    v=first_num(f,*keys); return 'N/A' if v is None else f'{v:.2f}'
cards=[]
for i,r in enumerate(rows[:12],1):
 t,f=r['t'],r['f']; cls='buy' if r['rec'].startswith('BUY') or r['rec'].startswith('HIGH') else 'avoid' if r['rec']=='AVOID' else 'watch'
 cards.append(f'''<article class="stock {cls}"><div class="stockhead"><div><span>#{i}</span><h3>{html.escape(str(r['name']))}</h3><small>{r['cap']} • {r['horizon']}</small></div><div class="score">{r['score']}<small>/100</small></div></div><div class="rec">{r['rec']}</div><div class="bars"><span>Fundamental <b>{round(r['score']*.35)}</b>/35</span><span>Technical <b>{round(r['score']*.35)}</b>/35</span><span>Momentum <b>{round(r['score']*.20)}</b>/20</span><span>Entry/Risk <b>{round(r['score']*.10)}</b>/10</span></div><div class="grid"><div>Price <b>₹{t['close']:.2f}</b></div><div>RSI <b>{t['rsi']:.1f}</b></div><div>ADX <b>{t['adx']:.1f}</b></div><div>ATR <b>{t['atr_pct']:.2f}%</b></div><div>1M <b>{t['ret1m']:.1f}%</b></div><div>3M <b>{t['ret3m']:.1f}%</b></div><div>1Y <b>{t['ret1y']:.1f}%</b></div><div>Vol <b>{t['vol_ratio']:.2f}x</b></div></div><div class="why"><b>Why:</b> {html.escape('; '.join(r['reasons']))}</div><div class="funds"><b>ROE</b> {val(f,'Return on equity','ROE')} &nbsp; <b>ROCE</b> {val(f,'Return on capital employed','ROCE')} &nbsp; <b>P/E</b> {val(f,'Price to Earning','P/E')} &nbsp; <b>D/E</b> {val(f,'Debt to equity','Debt/Equity','D/E')}</div></article>''')
trs=[]
for i,r in enumerate(rows,1):
 t,f=r['t'],r['f']; cls='buy' if r['rec'].startswith('BUY') or r['rec'].startswith('HIGH') else 'avoid' if r['rec']=='AVOID' else 'watch'
 trs.append(f'''<tr><td>{i}</td><td>{html.escape(str(r['cap']))}</td><td><b>{html.escape(str(r['name']))}</b></td><td><b>{r['score']}</b></td><td class="{cls}">{r['rec']}</td><td>{r['horizon']}</td><td>₹{t['close']:.2f}</td><td>{t['rsi']:.1f}</td><td>{t['trend']}</td><td>{t['ret3m']:.1f}%</td><td>{t['vol_ratio']:.2f}x</td><td>{t['adx']:.1f}</td><td>{t['atr_pct']:.2f}%</td><td>{r['stop']:.2f}</td><td>{r['target']:.2f}</td><td>{val(f,'Price to Earning','P/E')}</td><td>{val(f,'Return on equity','ROE')}</td><td>{val(f,'Return on capital employed','ROCE')}</td><td>{t['w52']}</td></tr>''')
page='''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Nifty Swing Growth Radar</title><style>body{font-family:system-ui;margin:0;background:#f3f6fa;color:#172033}header{background:#17365d;color:white;padding:24px}main{max-width:1900px;margin:auto;padding:16px}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px}.card,.stock{background:#fff;border-radius:16px;padding:16px;margin:14px 0;box-shadow:0 2px 10px #0001}.stockhead{display:flex;justify-content:space-between}.stock h3{margin:5px 0}.score{font-size:30px;font-weight:800}.score small{font-size:12px;color:#667085}.rec{font-weight:800;padding:7px;border-radius:8px;display:inline-block}.buy .rec{background:#e8f7ed;color:#087f23}.watch .rec{background:#fff4d6;color:#946200}.avoid .rec{background:#feeceb;color:#b42318}.bars,.grid{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin:8px 0}.bars span,.grid div{background:#f7f9fb;padding:7px;border-radius:7px;font-size:11px}.grid{grid-template-columns:repeat(4,1fr)}.grid b{display:block;font-size:13px}.why,.funds{font-size:12px;margin-top:10px}.funds{border-top:1px solid #eee;padding-top:8px}table{border-collapse:collapse;width:100%;min-width:1700px}th,td{padding:7px;border-bottom:1px solid #ddd;font-size:11px;text-align:left}th{background:#17365d;color:white;position:sticky;top:0}.buy{font-weight:800;color:#087f23}.watch{font-weight:800;color:#946200}.avoid{font-weight:800;color:#b42318}.note{color:#667085;font-size:12px}@media(max-width:600px){.cards{grid-template-columns:1fr}.grid{grid-template-columns:repeat(2,1fr)}.bars{grid-template-columns:1fr}}</style></head><body><header><h1>📈 Nifty Swing Growth Radar</h1><div>Swing-trading screen • 2–8 week horizon</div></header><main><div class="card"><h2>🔥 Top swing candidates</h2><p class="note">Score: trend 15 + relative strength 15 + breakout 15 + volume 10 + RSI 7 + MACD 5 + ADX 5 + earnings 8 + quality 5 + entry/risk 5.</p></div><div class="cards">'''+''.join(cards)+'''</div><div class="card"><h2>📋 Full universe</h2><div style="overflow:auto"><table><thead><tr><th>#</th><th>Cap</th><th>Stock</th><th>Score</th><th>Action</th><th>Horizon</th><th>Price</th><th>RSI</th><th>Trend</th><th>3M</th><th>Vol</th><th>ADX</th><th>ATR%</th><th>Stop</th><th>Target</th><th>P/E</th><th>ROE</th><th>ROCE</th><th>52W</th></tr></thead><tbody>'''+''.join(trs)+'''</tbody></table></div></div><div class="card"><p class="note">Market data via OpenChart/jugaad-data fallback; financial data via Screener. Missing values remain N/A. Research screen only; no guarantee of returns.</p></div></main></body></html>'''
(OUT/'index.html').write_text(page,encoding='utf-8'); pd.DataFrame(failures).to_csv(OUT/'failures.csv',index=False); print(f'Generated {len(rows)} stocks; failures={len(failures)}')
