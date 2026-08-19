from datetime import datetime,timedelta
import pandas as pd

def normalize(df):
    df=df.copy(); df.columns=[str(c).strip().title() for c in df.columns]
    for c in ['Open','High','Low','Close','Volume']:
        if c not in df: raise ValueError(f'Missing {c}')
        df[c]=pd.to_numeric(df[c],errors='coerce')
    df.index=pd.to_datetime(df.index); return df[['Open','High','Low','Close','Volume']].dropna()

def fetch_openchart(symbol,start,end):
    from openchart import NSEData
    n=NSEData(); return n.historical(symbol+'-EQ','EQ',start,end,'1d')

def fetch_jugaad(symbol,start,end):
    from jugaad_data.nse import stock_df
    return stock_df(symbol=symbol,from_date=start.date(),to_date=end.date(),series='EQ')

def fetch(symbol,days=400):
    end=datetime.now(); start=end-timedelta(days=days); errors=[]
    for name,fn in [('openchart',fetch_openchart),('jugaad',fetch_jugaad)]:
        try:
            df=normalize(fn(symbol,start,end))
            if len(df)>=220:return df,name
            errors.append(f'{name}: {len(df)} rows')
        except Exception as e: errors.append(f'{name}: {e}')
    raise RuntimeError(' | '.join(errors))
