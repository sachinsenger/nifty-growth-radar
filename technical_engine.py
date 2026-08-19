import numpy as np
import pandas as pd

def ema(s,n): return s.ewm(span=n,adjust=False).mean()
def rsi(c,n=14):
    d=c.diff(); up=d.clip(lower=0); dn=-d.clip(upper=0)
    rs=up.ewm(alpha=1/n,adjust=False).mean()/dn.ewm(alpha=1/n,adjust=False).mean().replace(0,np.nan)
    return 100-100/(1+rs)
def atr(df,n=14):
    pc=df.Close.shift(1)
    tr=pd.concat([(df.High-df.Low).abs(),(df.High-pc).abs(),(df.Low-pc).abs()],axis=1).max(axis=1)
    return tr.ewm(alpha=1/n,adjust=False).mean()
def adx(df,n=14):
    up=df.High.diff(); dn=-df.Low.diff()
    plus=up.where((up>dn)&(up>0),0); minus=dn.where((dn>up)&(dn>0),0)
    pc=df.Close.shift(1); tr=pd.concat([(df.High-df.Low).abs(),(df.High-pc).abs(),(df.Low-pc).abs()],axis=1).max(axis=1)
    a=tr.ewm(alpha=1/n,adjust=False).mean(); p=100*plus.ewm(alpha=1/n,adjust=False).mean()/a; m=100*minus.ewm(alpha=1/n,adjust=False).mean()/a
    dx=100*(p-m).abs()/(p+m).replace(0,np.nan)
    return dx.ewm(alpha=1/n,adjust=False).mean()
def calculate(df):
    df=df.copy().sort_index().dropna(subset=['Close'])
    if len(df)<220: raise ValueError(f'Only {len(df)} candles; need at least 220')
    c,h,l,v=df.Close,df.High,df.Low,df.Volume
    for n in (20,50,200): df[f'EMA{n}']=ema(c,n)
    df['RSI14']=rsi(c); e12,e26=ema(c,12),ema(c,26); df['MACD']=e12-e26; df['MACDSignal']=ema(df.MACD,9); df['MACDHist']=df.MACD-df.MACDSignal
    df['ATR14']=atr(df); df['ATRpct']=100*df.ATR14/c; df['ADX14']=adx(df)
    mid=c.rolling(20).mean(); sd=c.rolling(20).std(); df['BBUpper']=mid+2*sd; df['BBLower']=mid-2*sd; df['BBPos']=(c-df.BBLower)/(df.BBUpper-df.BBLower)
    df['Vol20']=v.rolling(20).mean(); df['VolRatio']=v/df.Vol20; df['High52']=h.rolling(252).max(); df['Low52']=l.rolling(252).min()
    df['High20']=h.rolling(20).max().shift(1); df['High50']=h.rolling(50).max().shift(1)
    for n in (1,5,21,63,126,252): df[f'Ret{n}D']=c.pct_change(n)*100
    x=df.iloc[-1]; r=float(x.RSI14)
    rs='Oversold' if r<30 else 'Weak' if r<40 else 'Neutral' if r<55 else 'Strong' if r<70 else 'Overbought'
    trend='Bullish alignment' if x.Close>x.EMA20>x.EMA50>x.EMA200 else 'Improving' if x.Close>x.EMA50>x.EMA200 else 'Bearish alignment' if x.Close<x.EMA20<x.EMA50<x.EMA200 else 'Mixed'
    w52='Near 52W high' if x.Close>=.98*x.High52 else 'Near 52W low' if x.Close<=1.02*x.Low52 else 'Middle range'
    adx_now=float(x.ADX14); adx_prev=float(df.iloc[-6].ADX14) if len(df)>=6 else adx_now
    return {'date':str(df.index[-1].date()),'close':float(x.Close),'rsi':r,'rsi_status':rs,'ema20':float(x.EMA20),'ema50':float(x.EMA50),'ema200':float(x.EMA200),'trend':trend,'macd_hist':float(x.MACDHist),'macd_status':'Bullish' if x.MACD>x.MACDSignal else 'Bearish','macd_hist_rising':bool(x.MACDHist>df.iloc[-2].MACDHist),'atr':float(x.ATR14),'atr_pct':float(x.ATRpct),'adx':adx_now,'adx_rising':adx_now>adx_prev,'vol_ratio':float(x.VolRatio),'high52':float(x.High52),'low52':float(x.Low52),'high20':float(x.High20),'high50':float(x.High50),'dist_high':float(x.Close/x.High52*100-100),'dist_low':float(x.Close/x.Low52*100-100),'w52':w52,'ret1d':float(x.Ret1D),'ret1w':float(x.Ret5D),'ret1m':float(x.Ret21D),'ret3m':float(x.Ret63D),'ret6m':float(x.Ret126D),'ret1y':float(x.Ret252D),'support':float(df.Low.tail(20).min()),'resistance':float(df.High.tail(20).max()),'breakout20':bool(x.Close>x.High20),'breakout50':bool(x.Close>x.High50)}
