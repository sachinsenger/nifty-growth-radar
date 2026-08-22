"""Daily market-news intelligence layer."""
import html, re, urllib.parse, urllib.request, xml.etree.ElementTree as ET, json
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).parent; OUT=ROOT/'docs'; OUT.mkdir(exist_ok=True)

QUERIES=[
 ('India markets','Nifty OR Sensex OR Indian stocks OR NSE India'),
 ('RBI rates inflation','RBI India repo rate inflation rupee markets'),
 ('Crude geopolitics','India crude oil Brent Strait Hormuz Middle East markets'),
 ('India policy','India government policy tariffs capex infrastructure stocks'),
 ('IT AI','Indian IT stocks AI technology spending TCS Infosys HCLTech Wipro'),
 ('Banks NBFC','India banks NBFC credit growth RBI financial stocks'),
 ('Pharma healthcare','India pharma healthcare stocks USFDA drug pricing'),
 ('Auto','India auto stocks EV tariffs vehicle sales'),
 ('Defence industrials','India defence industrial capital goods stocks orders'),
 ('Metals mining','India metals steel aluminium mining stocks China commodity'),
 ('Energy utilities','India energy power gas oil stocks ONGC Reliance NTPC'),
 ('Global markets','US stocks Fed Treasury yields China Japan Europe markets'),
 ('AI semiconductors','AI semiconductors Nvidia chip stocks global markets')]

# Company-name matching. This is intentionally broader than ticker matching because news headlines
# usually contain company names rather than NSE symbols.
STOCK_KEYS={
 'RELIANCE':['reliance','jio'],'TCS':['tcs','tata consultancy'],'INFY':['infosys'],'HCLTECH':['hcltech','hcl technologies'],
 'WIPRO':['wipro'],'HDFCBANK':['hdfc bank'],'ICICIBANK':['icici bank'],'SBIN':['sbi','state bank of india'],
 'AXISBANK':['axis bank'],'KOTAKBANK':['kotak bank'],'BAJFINANCE':['bajaj finance'],'BAJAJFINSV':['bajaj finserv'],
 'M&M':['mahindra','mahindra & mahindra'],'MARUTI':['maruti suzuki'],'TITAN':['titan company'],'SUNPHARMA':['sun pharma','sun pharmaceutical'],
 'MARKSANS':['marksans pharma'],'MAXHEALTH':['max healthcare'],'KIMS':['kims hospital'],'LT':['larsen','l&t','larsen & toubro'],
 'MAZDOCK':['mazagon dock'],'SOLARINDS':['solar industries'],'DATAPATTNS':['data patterns'],'NTPC':['ntpc'],
 'ONGC':['ongc'],'BPCL':['bpcl'],'BHARTIARTL':['bharti airtel','airtel'],'POLYCAB':['polycab'],'DIXON':['dixon technologies'],
 'COFORGE':['coforge'],'PERSISTENT':['persistent systems'],'BSE':['bse ltd'],'CDSL':['cdsl'],'DELHIVERY':['delhivery'],
 'HAL':['hindustan aeronautics','hal ltd'],'BEL':['bharat electronics','bel ltd'],'RVNL':['rvnl'],'IRFC':['irfc'],
 'ADANIENT':['adani enterprises'],'ADANIPORTS':['adani ports'],'ADANIGREEN':['adani green'],'TRENT':['trent ltd','trent limited'],
 'ETERNAL':['eternal ltd','zomato'],'JUBLFOOD':['jubilant food'],'DMART':['avenue supermarts','dmart'],'ASIANPAINT':['asian paints'],
 'PIDILITIND':['pidilite'],'ULTRACEMCO':['ultratech cement'],'JSWSTEEL':['jsw steel'],'TATASTEEL':['tata steel'],
 'HINDALCO':['hindalco'],'COALINDIA':['coal india'],'POWERGRID':['power grid'],'TATAPOWER':['tata power'],
 'INDIGO':['indigo','interglobe aviation'],'EICHERMOT':['eicher motors'],'BAJAJ-AUTO':['bajaj auto'],'HEROMOTOCO':['hero motocorp'],
 'DRREDDY':['dr reddy'],'CIPLA':['cipla'],'DIVISLAB':['divi s'],'MANKIND':['mankind pharma']}

SECTOR_KEYS={'Financials':['bank','banks','nbfc','lending','credit','rbi','insurance','fintech'],
 'IT':['software','it services','technology','ai','artificial intelligence','cloud','cybersecurity','semiconductor'],
 'Pharma':['pharma','pharmaceutical','drug','fda','usfda','healthcare','biotech'],
 'Auto':['auto','automobile','ev','electric vehicle','vehicle sales','cars','two-wheeler'],
 'Defence':['defence','defense','missile','drone','navy','army','aerospace'],
 'Industrials':['capital goods','infrastructure','order win','railway','engineering','manufacturing'],
 'Energy':['crude','brent','oil','gas','power','electricity','lng','renewable'],
 'Metals':['steel','aluminium','copper','metal','mining','iron ore'],
 'Telecom':['telecom','5g','spectrum','airtel'],'FMCG':['fmcg','consumer','rural demand','food inflation'],
 'Chemicals':['chemical','specialty chemicals']}

# Representative liquid names used when a macro/sector story does not mention a company explicitly.
SECTOR_STOCKS={
 'Financials':['HDFCBANK','ICICIBANK','SBIN','AXISBANK','KOTAKBANK','BAJFINANCE'],
 'IT':['TCS','INFY','HCLTECH','WIPRO','COFORGE','PERSISTENT'],
 'Pharma':['SUNPHARMA','DRREDDY','CIPLA','DIVISLAB','MANKIND'],
 'Auto':['MARUTI','M&M','BAJAJ-AUTO','EICHERMOT','HEROMOTOCO'],
 'Defence':['HAL','BEL','MAZDOCK','SOLARINDS','DATAPATTNS'],
 'Industrials':['LT','RVNL','IRFC','POLYCAB','DIXON'],
 'Energy':['RELIANCE','ONGC','BPCL','NTPC','POWERGRID','TATAPOWER'],
 'Metals':['TATASTEEL','JSWSTEEL','HINDALCO','COALINDIA'],
 'Telecom':['BHARTIARTL'],'FMCG':['TRENT','DMART','TITAN'],'Chemicals':['PIDILITIND','ASIANPAINT']}

POS=['upgrade','beat','strong','surge','growth','approval','order win','capex','inflow','easing','buyback','dividend','deal','rebound','cut rate','contract']
NEG=['downgrade','miss','fall','drop','inflation','tariff','war','sanction','hawkish','rate hike','selloff','weak','cut guidance','fraud','higher crude','yield rises']
MACRO=['crude','brent','rbi','repo','treasury yield','fed','tariff','war','hormuz','inflation','rupee','usd/inr','fii','dii']

def fetch_feed(label,q):
    url='https://news.google.com/rss/search?'+urllib.parse.urlencode({'q':q+' when:1d','hl':'en-IN','gl':'IN','ceid':'IN:en'})
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 NiftyGrowthRadar/1.0'})
    with urllib.request.urlopen(req,timeout=15) as r: data=r.read()
    root=ET.fromstring(data); out=[]
    for item in root.findall('./channel/item')[:15]:
        title=item.findtext('title','').strip(); link=item.findtext('link','').strip(); desc=re.sub('<.*?>',' ',item.findtext('description','') or '').strip(); pub=item.findtext('pubDate','').strip(); source=item.findtext('source','').strip()
        if title: out.append({'query':label,'title':title,'link':link,'description':re.sub(r'\s+',' ',desc)[:500],'published':pub,'source':source})
    return out

def classify(a):
    text=(a['title']+' '+a['description']).lower()
    stocks=[s for s,keys in STOCK_KEYS.items() if any(k in text for k in keys)][:6]
    sectors=[s for s,keys in SECTOR_KEYS.items() if any(k in text for k in keys)][:4]
    if not sectors: sectors=[a['query']]
    p=sum(x in text for x in POS); n=sum(x in text for x in NEG); tone='Positive' if p>n else 'Negative' if n>p else 'Mixed/Neutral'
    impact='High' if stocks or any(x in text for x in MACRO) else 'Medium'
    if 'crude' in text or 'brent' in text: affected=['Oil & Gas','Airlines','Paints','Chemicals','Tyres']
    elif 'treasury yield' in text or 'fed' in text: affected=['Financials','IT','High-growth/valuations']
    elif 'tariff' in text: affected=['Auto','IT','Pharma','Metals','Chemicals']
    else: affected=sectors
    # If the story names no company, surface representative liquid stocks for the affected sector.
    implied=[]
    for s in sectors:
        implied += SECTOR_STOCKS.get(s,[])
    watch=stocks or list(dict.fromkeys(implied))[:6] or sectors
    return {**a,'stocks':stocks,'sectors':sectors,'affected':affected,'tone':tone,'impact':impact,'watch':watch,'macro':any(x in text for x in MACRO)}

def build():
    all_items=[]
    for label,q in QUERIES:
        try: all_items += fetch_feed(label,q)
        except Exception: pass
    seen=set(); items=[]
    for a in all_items:
        key=re.sub(r'\W','',a['title'].lower())
        if key in seen: continue
        seen.add(key); items.append(classify(a))
    rank={'High':3,'Medium':2,'Low':1}; items.sort(key=lambda a:(rank.get(a['impact'],1),a['macro'],1 if a['tone']=='Negative' else 0),reverse=True); items=items[:30]
    date=datetime.now(timezone.utc).strftime('%Y-%m-%d'); high=[a for a in items if a['impact']=='High']; sector_counts={}
    for a in items:
        for s in a['sectors']: sector_counts[s]=sector_counts.get(s,0)+1
    sectors=sorted(sector_counts.items(),key=lambda x:x[1],reverse=True)[:10]; macro=[a for a in items if a['macro']]
    cards=[]
    for a in items[:20]:
        c='neg' if a['tone']=='Negative' else 'pos' if a['tone']=='Positive' else 'mix'; watch=', '.join(a['watch'][:6]) or 'Sector-level only'
        impact_text='Potential downside pressure' if a['tone']=='Negative' else 'Potential tailwind' if a['tone']=='Positive' else 'Potentially mixed'
        cards.append(f'<article class="news {c}"><span class="badge">{a["impact"]} impact</span> <span class="badge">{html.escape(a["tone"])}</span><h3><a href="{html.escape(a["link"])}" target="_blank" rel="noopener">{html.escape(a["title"])}</a></h3><p>{html.escape(a["description"])}</p><small>{html.escape(a["source"] or "Google News")} • {html.escape(a["published"])}</small><p><b>Affected sector:</b> {html.escape(", ".join(a["affected"]))}<br><b>Stocks to watch:</b> {html.escape(watch)}<br><b>Possible impact:</b> {impact_text}. Validate against price, volume, relative strength and fundamentals before acting.</p></article>')
    sector_html=''.join(f'<span class="sector">{html.escape(s)} <b>{n}</b></span>' for s,n in sectors)
    macro_html=''.join(f'<li><b>{html.escape(a["title"])}</b> — {html.escape(a["tone"])}; watch <b>{html.escape(", ".join(a["watch"]) or ", ".join(a["sectors"]))}</b></li>' for a in macro[:8]) or '<li>No major macro item detected from the public feeds.</li>'
    page=f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Market News Intelligence {date}</title><style>body{{font-family:system-ui;margin:0;background:#f3f6fa;color:#172033}}header{{background:#17365d;color:#fff;padding:22px}}main{{max-width:1200px;margin:auto;padding:14px}}.news{{background:#fff;border-radius:14px;padding:15px;margin:12px 0;box-shadow:0 2px 8px #0001;border-left:5px solid #98a2b3}}.news.neg{{border-left-color:#d92d20}}.news.pos{{border-left-color:#12b76a}}.news.mix{{border-left-color:#f79009}}a{{color:#175cd3;text-decoration:none}}.badge,.sector,.stock{{display:inline-block;background:#eef2f6;border-radius:99px;padding:4px 8px;font-size:11px;margin:2px}.stock{{font-weight:700;background:#e7f0ff;color:#174ea6}}.sector b{{font-size:12px}}small,p{{color:#667085;font-size:12px}}.panel{{background:#fff;border-radius:14px;padding:15px;margin:12px 0}}</style></head><body><header><h1>📰 Market News Intelligence</h1><div>{date} • Global + India • previous 24 hours</div></header><main><div class="panel"><h2>🧠 News → Sector → Stock → Impact</h2><p>News is mapped to named stocks where possible; sector-level stories also show representative liquid stocks to investigate. Impact is a research flag, not a trading guarantee.</p></div><div class="panel"><h2>🚨 Macro risks / catalysts</h2><ul>{macro_html}</ul></div><div class="panel"><h2>📊 Sector attention map</h2>{sector_html}</div><h2>📰 Top market-moving stories</h2>{''.join(cards)}<div class="panel"><h3>Trading discipline</h3><p>News alone never triggers BUY. Require technical confirmation: trend, relative strength, volume, structure and risk/reward. Confirm financial data and the original source before trading.</p></div></main></body></html>'''
    (OUT/'news.html').write_text(page,encoding='utf-8'); (OUT/f'news-{date}.html').write_text(page,encoding='utf-8'); (OUT/f'news-{date}.json').write_text(json.dumps({'date':date,'items':items,'high_impact':high,'sectors':sectors},indent=2),encoding='utf-8')
    return {'date':date,'items':len(items),'high_impact':len(high),'sectors':sectors}
if __name__=='__main__': print('News generated:',build())