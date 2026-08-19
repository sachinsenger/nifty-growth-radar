from datetime import datetime, timedelta
import time
import pandas as pd

_OPENCHART = None


def normalize(df):
    if df is None or len(df) == 0:
        raise ValueError('Empty market-data response')
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
    required = ['Open', 'High', 'Low', 'Close', 'Volume']
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f'Missing columns: {missing}; got {list(df.columns)}')
    for c in required:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    df = df[required].dropna()
    df = df[~df.index.isna()].sort_index()
    return df


def fetch_openchart(symbol, start, end):
    """OpenChart 0.2.x. Use its documented EQ symbol/segment first.
    The second call supports older OpenChart builds that used NSE exchange names.
    """
    global _OPENCHART
    from openchart import NSEData
    if _OPENCHART is None:
        _OPENCHART = NSEData()
    errors = []
    candidates = [
        (f'{symbol}-EQ', 'EQ'),
        (symbol, 'NSE'),
    ]
    for oc_symbol, segment in candidates:
        try:
            data = _OPENCHART.historical(oc_symbol, segment, start, end, '1d')
            data = normalize(data)
            if len(data):
                return data
            errors.append(f'{oc_symbol}/{segment}: empty')
        except Exception as exc:
            errors.append(f'{oc_symbol}/{segment}: {type(exc).__name__}: {exc}')
    raise RuntimeError('OpenChart: ' + ' | '.join(errors))


def fetch_jugaad(symbol, start, end):
    from jugaad_data.nse import stock_df
    return stock_df(symbol=symbol, from_date=start.date(), to_date=end.date(), series='EQ')


def fetch(symbol, days=400):
    end = datetime.now()
    start = end - timedelta(days=days)
    errors = []
    # Keep the source order deterministic. OpenChart is the primary source;
    # jugaad-data is the free NSE fallback when NSE blocks one client path.
    for name, fn in [('openchart', fetch_openchart), ('jugaad', fetch_jugaad)]:
        for attempt in range(2):
            try:
                df = normalize(fn(symbol, start, end))
                if len(df) >= 220:
                    # Small pacing delay avoids hammering NSE endpoints.
                    time.sleep(0.35)
                    return df, name
                errors.append(f'{name}: only {len(df)} rows; need >=220')
                break
            except Exception as exc:
                errors.append(f'{name} attempt {attempt + 1}: {type(exc).__name__}: {exc}')
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(' | '.join(errors))
