#!/usr/bin/env python3
"""10-minute market watchdog for the 5 pairs.
Fetches Binance USD-M futures 15m klines, computes RSI(14)/MACD(12,26,9)/EMA,
and prints ONLY when an alert condition triggers. Silent otherwise (watchdog).
European butler mode: English output, CET timestamps.
"""
import urllib.request, json
from datetime import datetime, timezone, timedelta

CET = timezone(timedelta(hours=1))
PAIRS = [
    ("ETHFIUSDC", "ETHFI"),
    ("BEATUSDT",  "BEAT"),
    ("ETHUSDC",   "ETH"),
    ("CRVUSDC",   "CRV"),
    ("ORDIUSDC",  "ORDI"),
]
INTERVAL = "15m"
LIMIT = 300

def fetch_klines(symbol):
    url = (f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}"
           f"&interval={INTERVAL}&limit={LIMIT}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())

def closes(kl):
    return [float(k[4]) for k in kl]

def ema(vals, period):
    k = 2 / (period + 1)
    e = vals[0]; out = [e]
    for v in vals[1:]:
        e = v * k + e * (1 - k); out.append(e)
    return out

def rsi(vals, period=14):
    gains = []; losses = []
    for i in range(1, len(vals)):
        d = vals[i] - vals[i - 1]
        gains.append(max(d, 0)); losses.append(max(-d, 0))
    ag = sum(gains[:period]) / period
    al = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        ag = (ag * (period - 1) + gains[i]) / period
        al = (al * (period - 1) + losses[i]) / period
    if al == 0:
        return 100.0
    return 100 - 100 / (1 + ag / al)

def macd(vals):
    e12 = ema(vals, 12); e26 = ema(vals, 26)
    line = [a - b for a, b in zip(e12, e26)]
    sig = ema(line, 9)
    hist = [m - s for m, s in zip(line, sig)]
    return line[-1], sig[-1], hist[-1], hist[-2]

alerts = []
for sym, name in PAIRS:
    try:
        kl = fetch_klines(sym)
        c = closes(kl)
        price = c[-1]
        r = rsi(c)
        m, s_, h, h_prev = macd(c)
        e20 = ema(c, 20)[-1]; e50 = ema(c, 50)[-1]
        e100 = ema(c, 100)[-1]; e200 = ema(c, 200)[-1]
        window = kl[-96:]  # ~24h of 15m bars
        high24 = max(float(k[2]) for k in window)
        low24 = min(float(k[3]) for k in window)

        if r >= 70:
            alerts.append(f"{name}: RSI {r:.1f} OVERBOUGHT @ {price:.4f}")
        elif r <= 30:
            alerts.append(f"{name}: RSI {r:.1f} OVERSOLD @ {price:.4f}")
        if h_prev <= 0 < h:
            alerts.append(f"{name}: MACD bullish cross @ {price:.4f}")
        elif h_prev >= 0 > h:
            alerts.append(f"{name}: MACD bearish cross @ {price:.4f}")
        if price >= high24:
            alerts.append(f"{name}: NEW 24h HIGH {price:.4f} (prev R {high24:.4f})")
        if price <= low24:
            alerts.append(f"{name}: NEW 24h LOW {price:.4f} (prev S {low24:.4f})")
        # dip-buy setup flag (user style): price pulled back to EMA cluster after being above
        if e20 > e50 > e100 > e200 and abs(price - e50) / price < 0.01:
            alerts.append(f"{name}: price at EMA cluster {e50:.4f} (dip-buy zone) @ {price:.4f}")
    except Exception:
        pass  # swallow per-pair errors; stay silent

now = datetime.now(CET).strftime("%Y-%m-%d %H:%M CET")
if alerts:
    print(f"[{now}] MARKET ALERT (10m scan)\n" + "\n".join("• " + a for a in alerts)
          + "\n\n(Not investment advice — verify on chart before acting)")
