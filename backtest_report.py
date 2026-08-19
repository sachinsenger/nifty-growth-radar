import json
from pathlib import Path
from market_data import fetch
from quality_engine import backtest_signals
import pandas as pd
ROOT=Path(__file__).parent; DOCS=ROOT/'docs'; s=pd.read_csv(ROOT/'stocks.csv'); results=[]
for _,x in s.iterrows():
    try:
        df,_=fetch(str(x.nse_symbol).strip()); r=backtest_signals(df); r.update({'name':x['name'],'symbol':x['nse_symbol']}); results.append(r)
    except Exception as e: results.append({'name':x['name'],'symbol':x['nse_symbol'],'error':str(e)})
(DOCS/'backtest-latest.json').write_text(json.dumps({'method':'technical breakout/volume price-only backtest','results':results},indent=2),encoding='utf-8')
print('Backtest report written:',len(results),'symbols')
