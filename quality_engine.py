import json, math
from pathlib import Path
import pandas as pd
DOCS=Path(__file__).parent/'docs'
def freshness(asof,max_hours=30):
    try:
        dt=pd.to_datetime(asof,utc=True); age=(pd.Timestamp.now(tz='UTC')-dt).total_seconds()/3600
        return ('FRESH' if age<=max_hours else 'STALE',round(age,1))
    except Exception:return ('UNKNOWN',None)
def signal_state(today,previous):
    if previous is None:return 'NEW'
    d=today-previous
    return 'IMPROVED' if d>=5 else 'WEAKENED' if d<=-5 else 'STABLE'
def risk_position(capital,risk_pct,entry,stop):
    cash=capital*risk_pct/100; per=abs(entry-stop); qty=math.floor(cash/per) if per else 0
    return {'risk_cash':cash,'qty':qty,'position_value':qty*entry,'actual_risk_pct':qty*per/capital*100 if capital else 0}
def trade_setup(entry,support,atr,score):
    stop=min(support,entry-1.5*atr); rr=2.0 if score>=85 else 1.8 if score>=75 else 1.5
    return {'entry_low':entry*.99,'entry_high':entry*1.01,'stop':stop,'target1':entry+(entry-stop)*rr,'rr':rr}
def load_history():
    out=[]
    for p in sorted(DOCS.glob('data-*.json')):
        try:
            d=json.loads(p.read_text()); d['_file']=p.name; out.append(d)
        except Exception: pass
    return out
def compare_history(current):
    hist=load_history(); prev=hist[-1] if hist and hist[-1].get('date')!=current.get('date') else (hist[-2] if len(hist)>1 else None)
    pm={x.get('nse_symbol'):x for x in (prev or {}).get('stocks',[])}
    for x in current.get('stocks',[]):
        old=pm.get(x.get('nse_symbol')); x['signal_change']=signal_state(x.get('score',0),old.get('score') if old else None); x['previous_score']=old.get('score') if old else None
    return current
def corporate_events(symbol): return {'status':'UNAVAILABLE','events':[],'symbol':symbol}
def backtest_signals(price_df,horizons=(5,10,20,40,60)):
    df=price_df.copy().sort_index(); c=df.Close; e20=c.ewm(span=20,adjust=False).mean(); e50=c.ewm(span=50,adjust=False).mean(); e200=c.ewm(span=200,adjust=False).mean(); vr=df.Volume/df.Volume.rolling(20).mean(); h20=df.High.rolling(20).max().shift(1)
    sig=(c>e20)&(e20>e50)&(e50>e200)&(c>h20)&(vr>=1.5); rows=[]; mx=max(horizons)
    for i in range(len(df)-mx):
        if bool(sig.iloc[i]): rows.append({f'ret_{h}d':float(c.iloc[i+h]/c.iloc[i]-1)*100 for h in horizons}|{'date':str(df.index[i].date())})
    if not rows:return {'n':0,'note':'No qualifying signals'}
    o=pd.DataFrame(rows); out={'n':len(o),'note':'Price-only; no point-in-time fundamentals'}
    for h in horizons:
        s=o[f'ret_{h}d']; out[f'{h}d']={'win_rate':round((s>0).mean()*100,1),'avg_return':round(s.mean(),2),'median_return':round(s.median(),2),'best':round(s.max(),2),'worst':round(s.min(),2)}
    return out
