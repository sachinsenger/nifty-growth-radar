from datetime import datetime, timedelta
import time
import pandas as pd

_OPENCHART = None


def normalize(df):
    df = df.copy()
    df.columns = [str(c).strip().title() for c in df.columns]
    if 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df = df.set_index('Date')
    elif 'Timestamp' in df.columns:
        df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')
        df = df.set_index('Timestamp')
    else:
        df.index = pd.to_datetime(df.index, errors='coerce')
    for c in ['Open', 'High', 'Low', 'Close', 'Volume']:
        if c not in df.columns:
            raise ValueError(f'Missing {c}')
        df[c] = pd.to_numeric(df[c], errors='coerce')
    df = df[['Open', 'High', 'Low', 'Close', 'Volume']].dropna()
    df = df[~df.index.isna()].sort_index()
    return df


def fetch_openchart(symbol, start, end):
    global _OPENCHART
    from openchart import NSEData
    if _OPENCHART is None:
        _OPENCHART = NSEData()
        _OPENCHART.download()
    return _OPENCHART.historical(symbol, 'NSE', start, end, '1d')


def fetch_jugaad(symbol, start, end):
    from jugaad_data.nse import stock_df
    return stock_df(symbol=symbol, from_date=start.date(), to_date=end.date(), series='EQ')


def fetch(symbol, days=400):
    end = datetime.now()
    start = end - timedelta(days=days)
    errors = []
    for name, fn in [('openchart', fetch_openchart), ('jugaad', fetch_jugaad)]:
        for attempt in range(2):
            try:
                df = normalize(fn(symbol, start, end))
                if len(df) >= 220:
                    time.sleep(0.5)
                    return df, name
                errors.append(f'{name}: {len(df)} rows')
                break
            except Exception as e:
                errors.append(f'{name} attempt {attempt + 1}: {type(e).__name__}: {e}')
                time.sleep(2 ** attempt)
    raise RuntimeError(' | '.join(errors))
