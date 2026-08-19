import pandas as pd, json, html
from pathlib import Path
from market_data import fetch
from technical_engine import calculate
from screener_fundamentals import fetch as fund
ROOT=Path(__file__).parent; OUT=ROOT/'docs'; OUT.mkdir(exist_ok=True)
stocks=pd.read_csv(ROOT/'stocks.csv'); rows=[]; failures=[]
def num(v):
    try:return float(str(v).replace(',','').replace('%','').replace('x',''))
    except:return None
def score(t,f):
    s=0
    s+=15 if t['trend']=='Bullish alignment' else 11 if t['trend']=='Improving' else 5 if t['trend']=='Mixed' else 0
    s+=8 if 45<=t['rsi']<=68 else 5 if 30<=t['rsi']<45 or 68<t['rsi']<=75 else 2
    s+=8 if t['macd_hist']>0 else 2; s+=7 if t['adx']>=25 else 4 if t['adx']>=18 else 1
    s+=7 if t['vol_ratio']>=1.2 else 4; s+=5 if t['close']>t['ema200'] else 1
    s+=5 if t['dist_high']>-10 else 3 if t['dist_high']>-20 else 1
    roe=num(f.get('Return on equity')) if f else None; roce=num(f.get('Return on capital employed')) if f else None; pe=num(f.get('Price to Earning')) if f else None
    s+=10 if roe is not None and roe>=18 else 6 if roe is not None and roe>=12 else 1
    s+=10 if roce is not None and roce>=18 else 6 if roce is not None and roce>=12 else 1
    s+=5 if pe is not None and 0<pe<35 else 3 if pe is not None and pe<60 else 1
    return min(100,round(s,1))
for _,x in stocks.iterrows():
    try:
        df,source=fetch(x.nse_symbol); t=calculate(df)
        try:f=fund(x.screener_symbol)
        except Exception as e:f={'_error':str(e)}
        sc=score(t,f); rec='BUY ON CONFIRMATION' if sc>=80 else 'BUY ON PULLBACK' if sc>=70 else 'HOLD-WATCH' if sc>=55 else 'AVOID'; horizon='3-6 months' if sc>=80 else '1-3 months' if sc>=65 else '2-4 weeks'
        rows.append({**x.to_dict(),'t':t,'f':f,'score':sc,'rec':rec,'horizon':horizon,'source':source})
    except Exception as e: failures.append({'name':x['name'],'error':str(e)})
rows.sort(key=lambda r:r['score'],reverse=True)
trs=[]
for i,r in enumerate(rows,1):
 t=r['t']; f=r['f']; cls='buy' if r['rec'].startswith('BUY') else 'avoid' if r['rec']=='AVOID' else 'watch'
 trs.append('<tr>'+''.join([f'<td>{i}</td>',f'<td>{html.escape(r["cap"])}</td>',f'<td><b>{html.escape(r["name"])}</b></td>',f'<td><b>{r["score"]}</b></td>',f'<td class="{cls}">{r["rec"]}</td>',f'<td>{r["horizon"]}</td>',f'<td>{t["close"]:.2f}</td>',f'<td>{t["rsi"]:.1f} ({t["rsi_status"]})</td>',f'<td>{t["ema20"]:.2f}/{t["ema50"]:.2f}/{t["ema200"]:.2f}</td>',f'<td>{t["trend"]}</td>',f'<td>{t["macd_hist"]:.2f}</td>',f'<td>{t["adx"]:.1f}</td>',f'<td>{t["atr_pct"]:.2f}%</td>',f'<td>{t["vol_ratio"]:.2f}x</td>',f'<td>{t["high52"]:.2f}/{t["low52"]:.2f}</td>',f'<td>{t["dist_high"]:.2f}%</td>',f'<td>{t["support"]:.2f}/{t["resistance"]:.2f}</td>',f'<td>{t["ret1m"]:.2f}% / {t["ret3m"]:.2f}% / {t["ret1y"]:.2f}%</td>',f'<td>{html.escape(str(f.get("Price to Earning","N/A")))}</td>',f'<td>{html.escape(str(f.get("Return on equity","N/A")))}</td>',f'<td>{html.escape(str(f.get("Return on capital employed","N/A")))}</td>'])+'</tr>')
top=''.join(f'<li><b>{html.escape(r["name"])}</b> — {r["score"]}/100 — {r["rec"]} — {r["horizon"]}</li>' for r in rows[:10])
page='''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Nifty Growth Radar</title><style>body{font-family:system-ui;margin:0;background:#f5f7fb;color:#172033}header{background:#17365d;color:white;padding:24px}main{max-width:1900px;margin:auto;padding:18px}.card{background:white;padding:18px;margin:14px 0;border-radius:14px;overflow:auto}table{border-collapse:collapse;width:100%;min-width:2200px}th,td{padding:7px;border-bottom:1px solid #ddd;font-size:11px;text-align:left}th{background:#17365d;color:white;position:sticky;top:0}.buy{font-weight:800;color:#087f23}.watch{font-weight:800;color:#9a6700}.avoid{font-weight:800;color:#b42318}.note{color:#667085}</style></head><body><header><h1>📊 Nifty Growth Radar</h1><div>Daily NSE research screen • latest completed session</div></header><main><div class="card"><h2>🔥 Top opportunities</h2><ol>'''+top+'''</ol><p class="note">Systematic research ranking only. It does not guarantee future returns or constitute personalized investment advice.</p></div><div class="card"><table><thead><tr><th>Rank</th><th>Cap</th><th>Stock</th><th>Score</th><th>Recommendation</th><th>Horizon</th><th>Close</th><th>RSI</th><th>EMA20/50/200</th><th>Trend</th><th>MACD Hist</th><th>ADX</th><th>ATR%</th><th>Vol/20D</th><th>52W H/L</th><th>Dist High</th><th>Support/Resistance</th><th>1M/3M/1Y</th><th>P/E</th><th>ROE</th><th>ROCE</th></tr></thead><tbody>'''+''.join(trs)+'''</tbody></table></div><div class="card"><p class="note">Sources: NSE market data via OpenChart with jugaad-data fallback; financial data via Screener. Missing values remain N/A rather than being fabricated.</p></div></main></body></html>'''
(OUT/'index.html').write_text(page,encoding='utf-8'); pd.DataFrame(failures).to_csv(OUT/'failures.csv',index=False); print(f'Generated {len(rows)} stocks; failures={len(failures)}')
