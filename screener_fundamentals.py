import requests,pandas as pd
from bs4 import BeautifulSoup
H={'User-Agent':'Mozilla/5.0 NiftyGrowthRadar/1.0'}
def fetch(symbol):
    for suffix in ['/consolidated/','/']:
        u='https://www.screener.in/company/'+symbol+suffix
        r=requests.get(u,headers=H,timeout=20)
        if r.status_code==200: break
    r.raise_for_status(); s=BeautifulSoup(r.text,'lxml'); out={'url':u}
    for li in s.select('#top-ratios li'):
        n=li.select_one('.name'); v=li.select_one('.number')
        if n and v: out[n.get_text(' ',strip=True)]=v.get_text(' ',strip=True)
    for sec in s.select('section'):
        h=sec.select_one('h2'); table=sec.select_one('table')
        if not h or not table: continue
        try: d=pd.read_html(str(table))[0]
        except Exception: continue
        if d.shape[1]<2: continue
        for _,row in d.iterrows():
            label=str(row.iloc[0]).strip()
            if label.lower()=='nan': continue
            out[h.get_text(' ',strip=True)+':'+label]=str(row.iloc[-1]).strip()
    return out
