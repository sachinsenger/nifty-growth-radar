import json,html
from pathlib import Path
from datetime import datetime,timezone
from quality_engine import compare_history,risk_position,corporate_events
ROOT=Path(__file__).parent; DOCS=ROOT/'docs'; today=datetime.now(timezone.utc).strftime('%Y-%m-%d'); p=DOCS/f'data-{today}.json'
if not p.exists(): raise SystemExit(f'Missing {p}')
d=json.loads(p.read_text()); d=compare_history(d)
cfg=json.loads((ROOT/'config.json').read_text()) if (ROOT/'config.json').exists() else {}; capital=float(cfg.get('paper_capital',500000)); risk_pct=float(cfg.get('risk_per_trade_pct',1.0))
for x in d['stocks']:
    t=x.get('technical',{}); entry=t.get('close'); stop=x.get('stop'); x['risk']=risk_position(capital,risk_pct,entry,stop) if entry and stop else None; x['corporate_events']=corporate_events(x.get('nse_symbol',''))
p.write_text(json.dumps(d,indent=2,default=str),encoding='utf-8')
h=DOCS/f'{today}.html'; text=h.read_text(encoding='utf-8') if h.exists() else (DOCS/'index.html').read_text(encoding='utf-8')
changed=[x for x in d['stocks'] if x.get('signal_change') in ('IMPROVED','WEAKENED')]
status=' '.join(f"{x['name']}: {x['signal_change']} ({x.get('previous_score')}→{x['score']})" for x in changed[:12]) or 'No material score changes versus previous snapshot.'
panel=f'''<section style="background:#fff;padding:16px;margin:14px;border-radius:15px;box-shadow:0 2px 9px #0001"><h2>Quality & Risk Layer</h2><p><b>Paper capital:</b> ₹{capital:,.0f} &nbsp; <b>Risk/trade:</b> {risk_pct:.2f}%</p><p><b>Signal changes:</b> {html.escape(status)}</p><p><b>Corporate events:</b> No verified free event source is configured; events are never invented.</p><p style="color:#667085;font-size:12px">Position sizing is a research aid, not an execution instruction.</p></section>'''
if 'Quality & Risk Layer' in text:
    a=text.find('<section style="background:#fff;padding:16px;margin:14px'); b=text.find('</section>',a)+10; text=text[:a]+panel+text[b:]
else:text=text.replace('<main>', '<main>'+panel,1)
for out in (h,DOCS/'index.html'): out.write_text(text,encoding='utf-8')
print(f'Quality layer updated {today}; {len(changed)} material signal changes')
