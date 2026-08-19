# Swing-radar orchestration is intentionally kept in one file for GitHub Actions.
import html
from pathlib import Path
import pandas as pd
from market_data import fetch
from screener_fundamentals import fetch as fund
from technical_engine import calculate
ROOT=Path(__file__).parent; OUT=ROOT/'docs'; OUT.mkdir(exist_ok=True)
stocks=pd.read_csv(ROOT/'stocks.csv'); rows=[]; failures=[]
SECTORS={'RELIANCE':'Energy','HDFCBANK':'Financials','ICICIBANK':'Financials','BHARTIARTL':'Telecom','TCS':'IT','INFY':'IT','SBIN':'Financials','LICI':'Financials','ITC':'FMCG','HINDUNILVR':'FMCG','LT':'Industrials','AXISBANK':'Financials','KOTAKBANK':'Financials','BAJFINANCE':'Financials','MARUTI':'Auto','SUNPHARMA':'Pharma','HCLTECH':'IT','NTPC':'Utilities','M&M':'Auto','TITAN':'Consumer','BSE':'Financials','OFSS':'IT','SOLARINDS':'Industrials','POLYCAB':'Industrials','DIXON':'Electronics','CUMMINSIND':'Industrials','CGPOWER':'Industrials','COFORGE':'IT','FEDERALBNK':'Financials','INDIANB':'Financials','MUTHOOTFIN':'Financials','POLICYBZR':'Financials','MAZDOCK':'Industrials','ASTRAL':'Industrials','APLAPOLLO':'Industrials','PERSISTENT':'IT','MAXHEALTH':'Healthcare','SUPREMEIND':'Industrials','SONACOMS':'Auto','BHARATFORG':'Auto','ZENSARTECH':'IT','HFCL':'Telecom','AEGISLOG':'Logistics','NEULANDLAB':'Pharma','FORCEMOT':'Auto','BLS':'Services','ECLERX':'IT','GREAVESCOT':'Auto','MARKSANS':'Pharma','BALAMINES':'Chemicals','CDSL':'Financials','DELHIVERY':'Logistics','ATHERENERG':'Auto','KIMS':'Healthcare','DATAPATTNS':'Defence','KIRLOSENG':'Industrials','CAMS':'Financials','NH':'Healthcare','KVBL':'Financials'}
def num(v):
    try:return float(str(v).replace(',','').replace('%','').replace('x','').replace('₹','').strip())
    except:return None
def first_num(data,*keys):
    for actual,value in (data or {}).items():
        low=str(actual).lower().replace(' ','')
        if any(k.lower().replace(' ','') in low for k in keys):
            z=num(value)
            if z is not None:return z
    return None
def fundamentals(f):
    return {'pe':first_num(f,'Stock P/E','P/E','Price to Earning'),'pb':first_num(f,'Price to book','P/B'),'roe':first_num(f,'Return on equity','ROE'),'roce':first_num(f,'Return on capital employed','ROCE'),'de':first_num(f,'Debt to equity','Debt/Eq','D/E'),'current':first_num(f,'Current ratio'),'sales_growth':first_num(f,'Sales growth','Revenue growth','YOY Quarterly sales'),'pat_growth':first_num(f,'Profit growth','PAT growth','YOY Quarterly profit'),'eps_growth':first_num(f,'EPS growth'),'op_margin':first_num(f,'OPM','Operating profit margin'),'cfo':first_num(f,'Cash from operating activity','Cash from operating activities','Operating cash flow'),'capex':first_num(f,'Fixed assets purchased','Capital expenditure','Capex'),'fcf':first_num(f,'Free cash flow'),'cfo_pat':first_num(f,'CFO/PAT','Cash flow to profit'),'interest':first_num(f,'Interest coverage')}
def clamp(x,a=0,b=1):return max(a,min(b,x))
def swing_score(t,f,market_ok=True,rs3=0,sector_rs=0):
    trend=15 if t['trend']=='Bullish alignment' else 11 if t['trend']=='Improving' else 5 if t['trend']=='Mixed' else 0
    rs=15*(.55*clamp((rs3+10)/35)+.25*clamp((t['ret1m']+5)/20)+.20*clamp((t['ret6m']+5)/45)); rs=max(0,min(15,rs+2*clamp((sector_rs+5)/25)))
    breakout=15 if t['breakout20'] and t['vol_ratio']>=1.5 else 12 if t['breakout20'] else 9 if t['close']>t['high50'] else 4
    volume=10 if t['vol_ratio']>=2 else 8 if t['vol_ratio']>=1.5 else 5 if t['vol_ratio']>=1.2 else 2
    r=t['rsi']; rsi=7 if 55<=r<=68 else 5 if 48<=r<55 or 68<r<=75 else 2
    macd=5 if t['macd_status']=='Bullish' and t['macd_hist_rising'] else 3 if t['macd_status']=='Bullish' else 1
    adx=5 if t['adx']>=25 and t['adx_rising'] else 4 if t['adx']>=20 else 2
    earnings=8 if f['eps_growth'] is not None and f['eps_growth']>=15 and f['sales_growth'] is not None and f['sales_growth']>=10 else 6 if f['eps_growth'] is not None and f['eps_growth']>=10 else 3
    quality=(2 if f['roe'] is not None and f['roe']>=15 else 1)+(2 if f['roce'] is not None and f['roce']>=15 else 1)+(1 if f['de'] is None or f['de']<=.5 else 0)
    dist=(t['close']/t['ema20']-1)*100; entry=5 if 0<=dist<=5 and r<=72 else 4 if dist<=8 and r<=75 else 2 if dist<=12 else 0
    if not market_ok: trend*=.65; rs*=.75
    return round(min(100,trend+rs+breakout+volume+rsi+macd+adx+earnings+quality+entry),1)
def classify(t,s):
    d=(t['close']/t['ema20']-1)*100
    if s>=85 and t['rsi']<=72 and d<=5:return 'HIGH-CONVICTION SWING'
    if s>=75 and (t['rsi']>72 or d>5):return 'BUY ON PULLBACK'
    if s>=75:return 'BUY / CONFIRMATION'
    if s>=65:return 'WATCH'
    if s>=55:return 'WEAK WATCH'
    return 'AVOID'
def reasons(t,f,rs3,sector_rs,market_ok):
    a=['Market regime supportive' if market_ok else 'Market regime cautious — reduced score']
    if t['trend']=='Bullish alignment':a.append('Price above EMA20/50/200')
    if t['breakout20'] and t['vol_ratio']>=1.5:a.append('20D breakout with strong volume')
    if rs3>10:a.append(f'Strong vs universe 3M (+{rs3:.1f}pp)')
    if sector_rs>10:a.append(f'Strong vs sector peers (+{sector_rs:.1f}pp)')
    if t['adx']>=25 and t['adx_rising']:a.append('ADX >25 and rising')
    if t['rsi']>75:a.append('RSI highly extended — avoid chasing')
    elif t['rsi']>70:a.append('RSI extended — prefer pullback')
    if t['macd_status']=='Bullish' and t['macd_hist_rising']:a.append('MACD momentum improving')
    if f['roe'] is not None and f['roe']>=15:a.append(f'ROE {f["roe"]:.1f}%')
    if f['roce'] is not None and f['roce']>=15:a.append(f'ROCE {f["roce"]:.1f}%')
    if f['fcf'] is not None and f['fcf']>0:a.append('Positive free cash flow')
    return a[:5]
# Try free NIFTY index feed; otherwise use large-cap breadth.
market_t=None
for idx in ['NIFTY 50','NIFTY50','NIFTY']:
    try: market_t=calculate(fetch(idx)[0]); break
    except Exception: pass
for _,x in stocks.iterrows():
    try:
        t=calculate(fetch(str(x.nse_symbol).strip())[0])
        try:fraw=fund(str(x.screener_symbol).strip())
        except Exception as e:fraw={'_error':f'{type(e).__name__}: {e}'}
        rows.append({**x.to_dict(),'sector':SECTORS.get(str(x.nse_symbol).strip(),'Other'),'t':t,'f':fundamentals(fraw),'source':'free-market'})
    except Exception as e:failures.append({'name':x['name'],'symbol':x['nse_symbol'],'error':f'{type(e).__name__}: {e}'})
if market_t: market_ok=market_t['close']>market_t['ema50'] and market_t['ema50']>market_t['ema200'] and market_t['rsi']>=50; market_label='Bullish' if market_ok else 'Cautious/Bearish'
else:
    large=[r for r in rows if r['cap']=='Large']; bull=sum(r['t']['close']>r['t']['ema50'] for r in large); market_ok=bull/max(1,len(large))>=.55; market_label=f'Breadth proxy {bull}/{len(large)} above EMA50'
benchmark3=sum(r['t']['ret3m'] for r in rows)/max(1,len(rows)); sec={}
for r in rows:sec.setdefault(r['sector'],[]).append(r['t']['ret3m'])
for r in rows:
    rs3=r['t']['ret3m']-benchmark3; vals=sec[r['sector']]; sec_rs=r['t']['ret3m']-(sum(vals)-r['t']['ret3m'])/max(1,len(vals)-1); s=swing_score(r['t'],r['f'],market_ok,rs3,sec_rs); rec=classify(r['t'],s); stop=min(r['t']['support'],r['t']['close']-1.5*r['t']['atr']); rr=1.8 if s>=85 else 1.5; target=r['t']['close']+(r['t']['close']-stop)*rr; r.update(score=s,rec=rec,horizon='2-8 weeks' if s>=75 else '1-4 weeks' if s>=65 else 'observe',stop=stop,target=target,rr=rr,rs3=rs3,sector_rs=sec_rs,reasons=reasons(r['t'],r['f'],rs3,sec_rs,market_ok))
rows.sort(key=lambda r:r['score'],reverse=True)
def v(f,*k):z=first_num(f,*k);return 'N/A' if z is None else f'{z:.2f}'
cards=[]
for i,r in enumerate(rows[:12],1):
 t,f=r['t'],r['f']; cards.append(f'<article class="stock"><div class="head"><div><b>#{i}</b><h3>{html.escape(str(r["name"]))}</h3><small>{r["cap"]} • {r["sector"]} • {r["horizon"]}</small></div><strong>{r["score"]}<small>/100</small></strong></div><div class="rec">{r["rec"]}</div><div class="grid"><div>Price<br><b>₹{t["close"]:.2f}</b></div><div>RSI<br><b>{t["rsi"]:.1f}</b></div><div>ADX<br><b>{t["adx"]:.1f}</b></div><div>Vol<br><b>{t["vol_ratio"]:.2f}x</b></div><div>RS vs Universe<br><b>{r["rs3"]:+.1f}pp</b></div><div>RS vs Sector<br><b>{r["sector_rs"]:+.1f}pp</b></div><div>ROE<br><b>{v(f,'Return on equity','ROE')}</b></div><div>ROCE<br><b>{v(f,'Return on capital employed','ROCE')}</b></div></div><p><b>Entry plan:</b> stop ₹{r["stop"]:.2f} • target ₹{r["target"]:.2f} • R:R 1:{r["rr"]:.1f}</p><p class="why"><b>Why:</b> {html.escape('; '.join(r["reasons"]))}</p></article>')
trs=[]
for i,r in enumerate(rows,1):
 t,f=r['t'],r['f']; trs.append(f'<tr><td>{i}</td><td>{r["cap"]}</td><td>{r["sector"]}</td><td><b>{html.escape(str(r["name"]))}</b></td><td>{r["score"]}</td><td>{r["rec"]}</td><td>{r["horizon"]}</td><td>{t["close"]:.2f}</td><td>{r["rs3"]:+.1f}%</td><td>{r["sector_rs"]:+.1f}%</td><td>{t["rsi"]:.1f}</td><td>{t["trend"]}</td><td>{t["adx"]:.1f}</td><td>{t["vol_ratio"]:.2f}x</td><td>{t["atr_pct"]:.2f}%</td><td>{v(f,'Price to Earning','P/E')}</td><td>{v(f,'Price to book','P/B')}</td><td>{v(f,'Return on equity','ROE')}</td><td>{v(f,'Return on capital employed','ROCE')}</td><td>{v(f,'Debt to equity','Debt/Eq','D/E')}</td><td>{v(f,'Sales growth','Revenue growth')}</td><td>{v(f,'Profit growth','PAT growth')}</td><td>{v(f,'EPS growth')}</td><td>{v(f,'Cash from operating activity','Operating cash flow')}</td><td>{v(f,'Free cash flow')}</td><td>{r["stop"]:.2f}</td><td>{r["target"]:.2f}</td><td>1:{r["rr"]:.1f}</td><td>{html.escape('; '.join(r["reasons"]))}</td></tr>')
page='''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Nifty Swing Growth Radar</title><style>body{font-family:system-ui;margin:0;background:#f3f6fa;color:#172033}header{background:#17365d;color:white;padding:22px}main{max-width:2200px;margin:auto;padding:14px}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px}.card,.stock{background:white;border-radius:15px;padding:15px;margin:12px 0;box-shadow:0 2px 9px #0001}.head{display:flex;justify-content:space-between}.head h3{margin:4px 0}.head>strong{font-size:30px}.head small{font-size:11px;color:#667085}.rec{font-weight:800;margin:8px 0;padding:7px;background:#eef8f0;border-radius:8px;display:inline-block}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:6px}.grid div{background:#f7f9fb;padding:7px;border-radius:7px;font-size:11px}.why,.note{font-size:12px;color:#667085}table{border-collapse:collapse;width:100%;min-width:2800px}th,td{padding:7px;border-bottom:1px solid #ddd;font-size:11px;text-align:left}th{background:#17365d;color:white;position:sticky;top:0}.tablewrap{overflow:auto}@media(max-width:600px){.grid{grid-template-columns:repeat(2,1fr)}} </style></head><body><header><h1>📈 Nifty Swing Growth Radar</h1><div>Multi-factor swing screen • 2–8 weeks • daily 4 PM IST</div></header><main><div class="cards"><div class="card"><b>Market regime</b><h2>'''+market_label+'''</h2><p class="note">NIFTY trend filter when the free index feed works; otherwise large-cap breadth proxy.</p></div><div class="card"><b>Universe</b><h2>'''+str(len(rows))+''' stocks</h2></div><div class="card"><b>High conviction</b><h2>'''+str(sum(r['score']>=85 for r in rows))+'''</h2></div><div class="card"><b>Buy / pullback</b><h2>'''+str(sum(r['score']>=75 for r in rows))+'''</h2></div></div><div class="card"><h2>🔥 Top swing candidates</h2><p class="note">Trend 15 • Relative strength 15 • Breakout 15 • Volume 10 • RSI 7 • MACD 5 • ADX 5 • Earnings 8 • Quality 5 • Entry/Risk 5.</p></div><div class="cards">'''+''.join(cards)+'''</div><div class="card"><h2>📋 Full technical + financial table</h2><div class="tablewrap"><table><thead><tr><th>#</th><th>Cap</th><th>Sector</th><th>Stock</th><th>Score</th><th>Action</th><th>Horizon</th><th>Price</th><th>RS vs Universe 3M</th><th>RS vs Sector</th><th>RSI</th><th>Trend</th><th>ADX</th><th>Vol/20D</th><th>ATR%</th><th>P/E</th><th>P/B</th><th>ROE</th><th>ROCE</th><th>D/E</th><th>Sales Growth</th><th>PAT Growth</th><th>EPS Growth</th><th>CFO</th><th>FCF</th><th>Stop</th><th>Target</th><th>R:R</th><th>Why</th></tr></thead><tbody>'''+''.join(trs)+'''</tbody></table></div></div><div class="card"><p class="note">Free data: OpenChart/jugaad-data + Screener. Missing values remain N/A. The score is a research screen, not a return guarantee; validate liquidity, corporate events and chart structure before trading.</p></div></main></body></html>'''
(OUT/'index.html').write_text(page,encoding='utf-8'); pd.DataFrame(failures).to_csv(OUT/'failures.csv',index=False); print(f'Generated {len(rows)} stocks; failures={len(failures)}; market={market_label}')
