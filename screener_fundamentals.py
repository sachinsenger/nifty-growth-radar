import time
import requests
import pandas as pd
from bs4 import BeautifulSoup

H = {
    'User-Agent': 'Mozilla/5.0 (compatible; NiftyGrowthRadar/1.0; +https://github.com/sachinsenger/nifty-growth-radar)',
    'Accept-Language': 'en-IN,en;q=0.9'
}
SESSION = requests.Session()
SESSION.headers.update(H)


def fetch(symbol):
    last_error = None
    for suffix in ['/consolidated/', '/']:
        u = 'https://www.screener.in/company/' + symbol + suffix
        for attempt in range(3):
            try:
                r = SESSION.get(u, timeout=25)
                if r.status_code == 200:
                    break
                last_error = f'HTTP {r.status_code}'
                time.sleep(2 ** attempt)
            except Exception as e:
                last_error = f'{type(e).__name__}: {e}'
                time.sleep(2 ** attempt)
        else:
            continue
        if r.status_code == 200:
            break
    else:
        raise RuntimeError(f'Screener unavailable for {symbol}: {last_error}')

    r.raise_for_status()
    s = BeautifulSoup(r.text, 'lxml')
    out = {'url': u}

    for li in s.select('#top-ratios li'):
        n = li.select_one('.name')
        v = li.select_one('.number')
        if n and v:
            out[n.get_text(' ', strip=True)] = v.get_text(' ', strip=True)

    for sec in s.select('section'):
        h = sec.select_one('h2')
        table = sec.select_one('table')
        if not h or not table:
            continue
        try:
            d = pd.read_html(str(table))[0]
        except Exception:
            continue
        if d.shape[1] < 2:
            continue
        for _, row in d.iterrows():
            label = str(row.iloc[0]).strip()
            if label.lower() == 'nan':
                continue
            out[h.get_text(' ', strip=True) + ':' + label] = str(row.iloc[-1]).strip()

    time.sleep(0.8)
    return out
