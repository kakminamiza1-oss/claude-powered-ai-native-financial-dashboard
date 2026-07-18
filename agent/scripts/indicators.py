#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
indicators.py - ดึง kline จาก Binance + คำนวณอินดิเคเตอร์ตามสไตล์เทรด
  - EMA(20/50/100/200)
  - SuperTrend(10,3)
  - MACD(12,26,9)
  - TEMA(ประยุกต์ EMA 3 ชั้น)
  - RSI (มีแล้วใน tools.py แต่คำนวณตรงนี้เพื่อรวมในกราฟ)
แล้ววาดกราฟ PNG (แท่ง + EMA + SuperTrend + pane MACD/RSI ด้านล่าง)
ใช้คู่กับ tools.py / agent.py / qwen2.5vl (อ่านรูป)

รันมือเอง:
  python indicators.py --symbol BTCUSDT --interval 4h --limit 200
คืน dict + เส้นทางไฟล์ PNG
"""
import argparse, json, os
from datetime import datetime

import numpy as np
import pandas as pd

try:
    import matplotlib
    matplotlib.use("Agg")  # ไม่ต้องเปิดหน้าจอ
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    _HAS_MPL = True
except Exception as e:
    _HAS_MPL = False
    _MPL_ERR = str(e)

# ===== เชื่อมต่อ Binance (ดึง kline ตรง) =====
import urllib.request

BINANCE = "https://api.binance.com/api/v3"


def _get_json(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def fetch_klines(symbol="BTCUSDT", interval="4h", limit=200):
    url = f"{BINANCE}/klines?symbol={symbol.upper()}&interval={interval}&limit={limit}"
    rows = _get_json(url)
    df = pd.DataFrame(rows, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "qav", "trades", "tbav", "tqav", "ignore"])
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    return df


# ===== ตัวคำนวณอินดิเคเตอร์ =====
def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()


def tema(series, period=20):
    e1 = ema(series, period)
    e2 = ema(e1, period)
    e3 = ema(e2, period)
    return 3 * e1 - 3 * e2 + e3


def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    ag = gain.ewm(alpha=1 / period, adjust=False).mean()
    al = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = ag / al
    return 100 - (100 / (1 + rs))


def macd(series, fast=12, slow=26, signal=9):
    ef = ema(series, fast)
    es = ema(series, slow)
    line = ef - es
    sig = ema(line, signal)
    hist = line - sig
    return line, sig, hist


def supertrend(df, period=10, multiplier=3.0):
    """คืน Series trend (เท่ากับราคาเมื่ออยู่เหนือ, หรือลบออกเมื่ออยู่ใต้) + สถานะ up/down"""
    high, low, close = df["high"], df["low"], df["close"]
    atr = (high - low).rolling(period).mean()  # ATR แบบง่าย (SMA)
    mid = (high + low) / 2
    upper = mid + multiplier * atr
    lower = mid - multiplier * atr
    st = close.copy()
    trend = pd.Series(index=df.index, dtype=float)  # +1 up, -1 down
    prev_upper = prev_lower = prev_trend = 0.0
    for i in range(len(df)):
        if i == 0:
            st.iloc[i] = lower.iloc[i]
            trend.iloc[i] = 1
            prev_upper, prev_lower, prev_trend = upper.iloc[i], lower.iloc[i], 1
            continue
        # final upper/lower ปรับตามเทรนด์ก่อนหน้า
        fu = upper.iloc[i] if upper.iloc[i] < prev_upper or prev_trend == -1 else prev_upper
        fl = lower.iloc[i] if lower.iloc[i] > prev_lower or prev_trend == 1 else prev_lower
        if close.iloc[i] > prev_upper:
            tr = 1
        elif close.iloc[i] < prev_lower:
            tr = -1
        else:
            tr = prev_trend
            if tr == 1 and close.iloc[i] <= fl:
                tr = -1
            elif tr == -1 and close.iloc[i] >= fu:
                tr = 1
        st.iloc[i] = fl if tr == 1 else fu
        trend.iloc[i] = tr
        prev_upper, prev_lower, prev_trend = fu, fl, tr
    return st, trend


def fib_retracement(df, lookback=120):
    """หาจุดสูงสุด/ต่ำสุดในหน้าต่างหลังสุด คืนระดับ Fibonacci 0/0.236/0.382/0.5/0.618/0.786/1"""
    sub = df.iloc[-lookback:]
    hi = float(sub["high"].max())
    lo = float(sub["low"].min())
    diff = hi - lo
    levels = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
    fib = {f"{int(l*1000)/10:.1f}%": round(lo + diff * l, 4) for l in levels}
    return {"swing_high": hi, "swing_low": lo, "levels": fib}


def support_resistance(df, lookback=120, min_touches=2, tol_pct=0.3):
    """หา S/R แบบง่าย: หาจุดที่แท่งเทียนแตะราคาเดิมซ้ำๆ (ใกล้เคียงกันใน tol%)"""
    sub = df.iloc[-lookback:]
    pivots = sorted(list(sub["high"]) + list(sub["low"]))
    clusters = []
    cur = [pivots[0]]
    for p in pivots[1:]:
        if abs(p - cur[-1]) / cur[-1] * 100 <= tol_pct:
            cur.append(p)
        else:
            if len(cur) >= min_touches:
                clusters.append(sum(cur) / len(cur))
            cur = [p]
    if len(cur) >= min_touches:
        clusters.append(sum(cur) / len(cur))
    clusters = sorted(set(round(c, 4) for c in clusters))
    last = float(df["close"].iloc[-1])
    sup = [c for c in clusters if c < last]
    res = [c for c in clusters if c > last]
    return {"support": sup[-3:] if sup else [], "resistance": res[:3] if res else []}


def vwap(df):
    """คำนวณ VWAP แบบสะสมตลอดหน้าต่าง (rolling cumulative)"""
    tp = (df["high"] + df["low"] + df["close"]) / 3
    vol = df["volume"]
    pv = (tp * vol).cumsum()
    cumvol = vol.cumsum()
    return pv / cumvol


def volume_profile(df, bins=20):
    """หาโซนราคาที่มีปริมาณซื้อขายหนาแน่นที่สุด (Value Area คร่าวๆ)"""
    low, high = df["low"].min(), df["high"].max()
    edges = np.linspace(low, high, bins + 1)
    centers = (edges[:-1] + edges[1:]) / 2
    vol = np.zeros(bins)
    for i in range(len(df)):
        # เทียบราคาปิดเข้า bin
        idx = int((df["close"].iloc[i] - low) / (high - low) * bins)
        idx = min(max(idx, 0), bins - 1)
        vol[idx] += df["volume"].iloc[i]
    # หา POC (Point of Control = bin ปริมาณสูงสุด)
    poc_idx = int(np.argmax(vol))
    # Value Area ~ bins ที่ปริมาณรวม 70% จาก POC ออกมาทั้งสองข้าง
    total = vol.sum()
    included = [poc_idx]
    lo_i, hi_i = poc_idx, poc_idx
    acc = vol[poc_idx]
    while acc < total * 0.7 and (lo_i > 0 or hi_i < bins - 1):
        nxt_lo = vol[lo_i - 1] if lo_i > 0 else -1
        nxt_hi = vol[hi_i + 1] if hi_i < bins - 1 else -1
        if nxt_lo >= nxt_hi:
            lo_i -= 1
            acc += max(nxt_lo, 0)
        else:
            hi_i += 1
            acc += max(nxt_hi, 0)
    va_low = float(centers[lo_i])
    va_high = float(centers[hi_i])
    return {
        "poc": round(float(centers[poc_idx]), 4),
        "va_low": round(va_low, 4),
        "va_high": round(va_high, 4),
        "profile": [round(float(v), 2) for v in vol],
        "centers": [round(float(c), 4) for c in centers],
    }


def find_signals(df):
    """หาจุดสัญญาณบนกราฟ: MACD cross, RSI เข้าโซน, ราคาตัด EMA20
    คืน list ของ dict: {type, x(index), price, label, color}"""
    c = df["close"]
    x = np.arange(len(df))
    signals = []
    line, sig, _ = macd(c)
    r = rsi(c, 14)
    e20 = ema(c, 20)
    # MACD cross (bullish: line ตัด signal ขึ้น, bearish: ลง)
    for i in range(1, len(df)):
        if line.iloc[i - 1] <= sig.iloc[i - 1] and line.iloc[i] > sig.iloc[i]:
            signals.append({"type": "MACD↑", "x": int(x[i]), "price": float(c.iloc[i]),
                            "label": "MACD bull", "color": "#26a69a"})
        elif line.iloc[i - 1] >= sig.iloc[i - 1] and line.iloc[i] < sig.iloc[i]:
            signals.append({"type": "MACD↓", "x": int(x[i]), "price": float(c.iloc[i]),
                            "label": "MACD bear", "color": "#ef5350"})
    # RSI เข้าโซน (แค่ช่วงหลังสุด ไม่เกิน 3 จุด)
    for i in range(len(df)):
        if r.iloc[i] > 70:
            signals.append({"type": "RSI OB", "x": int(x[i]), "price": float(c.iloc[i]),
                            "label": "RSI>70", "color": "#d62728"})
        elif r.iloc[i] < 30:
            signals.append({"type": "RSI OS", "x": int(x[i]), "price": float(c.iloc[i]),
                            "label": "RSI<30", "color": "#2ca02c"})
    # ราคาตัด EMA20 (cross up/down)
    for i in range(1, len(df)):
        if c.iloc[i - 1] <= e20.iloc[i - 1] and c.iloc[i] > e20.iloc[i]:
            signals.append({"type": "EMA20↑", "x": int(x[i]), "price": float(c.iloc[i]),
                            "label": "cross EMA20 up", "color": "#1f77b4"})
        elif c.iloc[i - 1] >= e20.iloc[i - 1] and c.iloc[i] < e20.iloc[i]:
            signals.append({"type": "EMA20↓", "x": int(x[i]), "price": float(c.iloc[i]),
                            "label": "cross EMA20 down", "color": "#ff7f0e"})
    # ตัดให้เหลือไม่เกิน 12 จุดหลังสุดเพื่อไม่ให้รก
    return signals[-12:] if len(signals) > 12 else signals


def analyze(symbol="BTCUSDT", interval="4h", limit=200):
    df = fetch_klines(symbol, interval, limit)
    c = df["close"]
    out = {
        "symbol": symbol.upper(),
        "interval": interval,
        "candles": len(df),
        "last_close": round(float(c.iloc[-1]), 4),
        "ema": {},
        "supertrend": {},
        "macd": {},
        "rsi": {},
        "tema": {},
        "fib": {},
        "sr": {},
        "vwap": {},
        "vp": {},
        "signals": [],
    }
    for p in (20, 50, 100, 200):
        e = ema(c, p)
        out["ema"][f"ema{p}"] = round(float(e.iloc[-1]), 4)
    st, trend = supertrend(df)
    out["supertrend"] = {
        "value": round(float(st.iloc[-1]), 4),
        "trend": "UP" if trend.iloc[-1] == 1 else "DOWN",
    }
    line, sig, hist = macd(c)
    out["macd"] = {
        "line": round(float(line.iloc[-1]), 4),
        "signal": round(float(sig.iloc[-1]), 4),
        "hist": round(float(hist.iloc[-1]), 4),
        "cross": "bullish" if line.iloc[-1] > sig.iloc[-1] else "bearish",
    }
    r = rsi(c, 14)
    out["rsi"] = {"value": round(float(r.iloc[-1]), 2),
                  "signal": "overbought" if r.iloc[-1] > 70 else ("oversold" if r.iloc[-1] < 30 else "neutral")}
    t = tema(c, 20)
    out["tema"] = {"tema20": round(float(t.iloc[-1]), 4),
                   "trend": "UP" if c.iloc[-1] > t.iloc[-1] else "DOWN"}
    out["fib"] = fib_retracement(df)
    out["sr"] = support_resistance(df)
    vw = vwap(df)
    out["vwap"] = {"value": round(float(vw.iloc[-1]), 4),
                   "trend": "UP" if c.iloc[-1] > vw.iloc[-1] else "DOWN"}
    out["vp"] = volume_profile(df)
    out["signals"] = find_signals(df)
    return df, out


def draw_chart(df, out, path=None):
    if not _HAS_MPL:
        return {"error": f"matplotlib ไม่พร้อม: {_MPL_ERR}"}
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            f"chart_{out['symbol']}_{out['interval']}.png")
    c = df["close"]
    fig, (ax, axm, axr) = plt.subplots(3, 1, figsize=(13, 9), sharex=True,
                                       gridspec_kw={"height_ratios": [3, 1, 1]})

    # ===== แท่งเทียน (Candlestick) =====
    x = np.arange(len(df))
    up = df["close"] >= df["open"]
    color_up, color_dn = "#26a69a", "#ef5350"
    # ไส้เทียน (wick)
    for i in range(len(df)):
        ax.plot([x[i], x[i]], [df["low"].iloc[i], df["high"].iloc[i]],
                color=color_up if up.iloc[i] else color_dn, lw=0.6)
    # ตัวแท่ง (body)
    for i in range(len(df)):
        o, cl = df["open"].iloc[i], df["close"].iloc[i]
        body_h = abs(cl - o)
        y0 = min(o, cl)
        ax.add_patch(plt.Rectangle((x[i] - 0.4, y0), 0.8, max(body_h, 1e-6),
                                   facecolor=color_up if up.iloc[i] else color_dn,
                                   edgecolor=color_up if up.iloc[i] else color_dn))
    ax.set_xticks([])  # ซ่อน tick แกน x บน (ใช้ของ pane ล่าง)
    # EMA
    for p in (20, 50, 100, 200):
        e = ema(c, p)
        ax.plot(x, e, lw=0.8, label=f"EMA{p}")
    # SuperTrend
    st, trend = supertrend(df)
    ax.plot(x, st, color="#ff7f0e", lw=1.3, label="SuperTrend")
    # TEMA
    t = tema(c, 20)
    ax.plot(x, t, color="#9467bd", lw=0.9, ls="--", label="TEMA20")
    # VWAP
    vw = vwap(df)
    ax.plot(x, vw, color="#000000", lw=0.9, ls=":", label="VWAP")

    # ===== Support / Resistance (เส้นแนวนอน) =====
    sr = out.get("sr", {})
    for s in sr.get("support", []):
        ax.axhline(s, color="#2ca02c", lw=0.7, ls=":", alpha=0.8)
        ax.text(x[0], s, f" S {s:g}", color="#2ca02c", fontsize=6, va="bottom")
    for r in sr.get("resistance", []):
        ax.axhline(r, color="#d62728", lw=0.7, ls=":", alpha=0.8)
        ax.text(x[0], r, f" R {r:g}", color="#d62728", fontsize=6, va="bottom")

    # ===== Volume Profile (แท่งแนวตั้งด้านขวาของราคา) =====
    vp = out.get("vp", {})
    if vp.get("profile") and vp.get("centers"):
        prof = vp["profile"]
        ctrs = vp["centers"]
        pmax = max(prof) if max(prof) > 0 else 1
        # แผนที่แกน x ของ profile ไปทางขวาสุดของกราฟ (x[-1] .. x[-1]+กว้าง)
        x0 = len(df)
        xw = max(8, len(df) * 0.12)
        for i, v in enumerate(prof):
            if v <= 0:
                continue
            w = (v / pmax) * xw
            ax.barh(ctrs[i], w, left=x0, height=(ctrs[1] - ctrs[0]) * 0.9,
                    color="#1f77b4", alpha=0.25)
        # POC เส้นแดง
        ax.axhline(vp["poc"], color="#d62728", lw=0.8, alpha=0.6)
        ax.text(x0, vp["poc"], f" POC {vp['poc']:g}", color="#d62728", fontsize=5.5, va="bottom")
        # Value Area
        ax.axhspan(vp["va_low"], vp["va_high"], color="#1f77b4", alpha=0.05)

    # ===== Fibonacci retracement (โซนสีอ่อน) =====
    fib = out.get("fib", {})
    fib_levels = fib.get("levels", {})
    if fib_levels:
        lo = fib["swing_low"]
        hi = fib["swing_high"]
        # แถบไล่สีจาก low->high
        ax.axhspan(lo, hi, color="#ffeb3b", alpha=0.06)
        fib_colors = {"0.0%": "#888", "23.6%": "#6a5acd", "38.2%": "#20b2aa",
                      "50.0%": "#ff8c00", "61.8%": "#20b2aa", "78.6%": "#6a5acd", "100.0%": "#888"}
        for lbl, lvl in fib_levels.items():
            ax.axhline(lvl, color=fib_colors.get(lbl, "#999"), lw=0.5, ls="-.", alpha=0.7)
            ax.text(x[-1], lvl, f" F{lbl}:{lvl:g}", color="#555", fontsize=5.5, va="center")

    # ===== สัญญาณ (markers วงกลมบนกราฟ) =====
    sigs = out.get("signals", [])
    for s in sigs:
        ax.scatter(s["x"], s["price"], s=60, facecolors="none",
                   edgecolors=s["color"], linewidths=1.6, zorder=5)
        ax.annotate(s["type"], (s["x"], s["price"]),
                    textcoords="offset points", xytext=(0, 8),
                    color=s["color"], fontsize=5.5, ha="center")

    ax.set_title(f"{out['symbol']} {out['interval']}  |  ST:{out['supertrend']['trend']}  "
                 f"MACD:{out['macd']['cross']}  RSI:{out['rsi']['value']}  VWAP:{out['vwap']['trend']}")
    ax.legend(loc="upper left", fontsize=7, ncol=4)
    ax.grid(alpha=0.2)

    # ===== MACD pane =====
    line, sig, hist = macd(c)
    axm.plot(x, line, color="blue", lw=0.8, label="MACD")
    axm.plot(x, sig, color="red", lw=0.8, label="Signal")
    axm.bar(x, hist, color=np.where(hist >= 0, "green", "red"), width=0.8)
    axm.axhline(0, color="#666", lw=0.5)
    axm.legend(loc="upper left", fontsize=7)
    axm.grid(alpha=0.2)

    # ===== RSI pane =====
    r = rsi(c, 14)
    axr.plot(x, r, color="purple", lw=0.9)
    axr.axhline(70, color="red", lw=0.6, ls="--")
    axr.axhline(30, color="green", lw=0.6, ls="--")
    axr.set_ylim(0, 100)
    axr.set_ylabel("RSI", fontsize=7)
    axr.set_xticks(x[::max(1, len(x)//8)])
    axr.set_xticklabels([d.strftime("%m-%d %Hh") for d in df["open_time"].iloc[::max(1, len(x)//8)]],
                        rotation=30, fontsize=6)
    axr.grid(alpha=0.2)

    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return {"chart_path": path, "size_kb": round(os.path.getsize(path) / 1024, 1)}


def draw_plan_chart(df, out, entry, sl, tp, path=None):
    """วาดกราฟพร้อมเส้น Entry/SL/TP โอเวอร์เลย์ (สำหรับบันทึกแผน PNG)"""
    if not _HAS_MPL:
        return {"error": f"matplotlib ไม่พร้อม: {_MPL_ERR}"}
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            f"plan_{out['symbol']}_{out['interval']}.png")
    c = df["close"]
    fig, (ax, axm, axr) = plt.subplots(3, 1, figsize=(13, 9), sharex=True,
                                       gridspec_kw={"height_ratios": [3, 1, 1]})
    # แท่งเทียน
    x = np.arange(len(df))
    up = df["close"] >= df["open"]
    cu, cd = "#26a69a", "#ef5350"
    for i in range(len(df)):
        ax.plot([x[i], x[i]], [df["low"].iloc[i], df["high"].iloc[i]],
                color=cu if up.iloc[i] else cd, lw=0.6)
    for i in range(len(df)):
        o, cl = df["open"].iloc[i], df["close"].iloc[i]
        ax.add_patch(plt.Rectangle((x[i] - 0.4, min(o, cl)), 0.8, max(abs(cl - o), 1e-6),
                                   facecolor=cu if up.iloc[i] else cd,
                                   edgecolor=cu if up.iloc[i] else cd))
    for p in (20, 50, 100, 200):
        ax.plot(x, ema(c, p), lw=0.8, label=f"EMA{p}")
    st, trend = supertrend(df)
    ax.plot(x, st, color="#ff7f0e", lw=1.3, label="SuperTrend")
    ax.plot(x, tema(c, 20), color="#9467bd", lw=0.9, ls="--", label="TEMA20")
    # ===== เส้นแผน Entry/SL/TP =====
    ax.axhline(entry, color="#1f77b4", lw=1.4, ls="-", label=f"Entry {entry:g}")
    ax.axhline(sl, color="#d62728", lw=1.4, ls="--", label=f"SL {sl:g}")
    ax.axhline(tp, color="#2ca02c", lw=1.4, ls="--", label=f"TP {tp:g}")
    # จุด Entry บนแท่งสุดท้าย
    ax.scatter([x[-1]], [entry], s=80, color="#1f77b4", zorder=6)
    ax.set_title(f"{out['symbol']} {out['interval']}  |  PLAN  Entry:{entry:g}  SL:{sl:g}  TP:{tp:g}")
    ax.legend(loc="upper left", fontsize=7, ncol=4)
    ax.grid(alpha=0.2)
    # MACD / RSI panes (ย่อ)
    line, sig, hist = macd(c)
    axm.plot(x, line, color="blue", lw=0.8)
    axm.plot(x, sig, color="red", lw=0.8)
    axm.bar(x, hist, color=np.where(hist >= 0, "green", "red"), width=0.8)
    axm.axhline(0, color="#666", lw=0.5)
    r = rsi(c, 14)
    axr.plot(x, r, color="purple", lw=0.9)
    axr.axhline(70, color="red", lw=0.6, ls="--")
    axr.axhline(30, color="green", lw=0.6, ls="--")
    axr.set_ylim(0, 100)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return {"chart_path": path, "size_kb": round(os.path.getsize(path) / 1024, 1)}


def price_pane_bbox(out, df):
    """คืน bbox จริงของ pane ราคา (พิกัด pixel ในภาพ) เพื่อแปลงคลิก→ราคาแม่นยำ
    วาดกราฟแล้วดึง ax.get_position() จากกราฟนั้นจริงๆ (ไม่ประมาณ)"""
    if not _HAS_MPL:
        return None
    c = df["close"]
    fig, (ax, axm, axr) = plt.subplots(3, 1, figsize=(13, 9), sharex=True,
                                       gridspec_kw={"height_ratios": [3, 1, 1]})
    # วาดแค่แท่ง/EMA พอให้ subplot มีขนาดจริง (ไม่ต้องครบ ใช้แค่กำหนด ylim)
    lo = float(df["low"].min()); hi = float(df["high"].max())
    margin = (hi - lo) * 0.05
    ax.set_ylim(lo - margin, hi + margin)
    fig.tight_layout()
    pos = ax.get_position()
    W, H = fig.get_size_inches() * fig.dpi
    left = pos.x0 * W
    right = pos.x1 * W
    top = (1 - pos.y1) * H
    bottom = (1 - pos.y0) * H
    plt.close(fig)
    return {"left": left, "right": right, "top": top, "bottom": bottom,
            "ymin": lo - margin, "ymax": hi + margin,
            "img_w": W, "img_h": H, "last": out["last_close"]}


def run(symbol="BTCUSDT", interval="4h", limit=200, draw=True):
    df, out = analyze(symbol, interval, limit)
    if draw:
        out["chart"] = draw_chart(df, out)
    return out


def auto_plan(symbol="BTCUSDT", interval="4h", limit=200, sl_pct=2.0, tp_pct=4.0):
    """หาจุด Entry อัตโนมัติจาก S/R + Fibonacci + สัญญาณทิศทาง
    คืน dict: {side, entry, sl, tp, reason, sr_near, fib_near}
    (เครื่องมือช่วยเสนอ ผู้ใช้ปรุงแต่งตัดสินใจเอง)"""
    df, out = analyze(symbol, interval, limit)
    last = float(df["close"].iloc[-1])
    sr = out.get("sr", {})
    fib = out.get("fib", {}).get("levels", {})
    fib618 = fib.get("61.8%")
    fib786 = fib.get("78.6%")
    st = out["supertrend"]["trend"]
    macd = out["macd"]["cross"]
    # เลือกทิศทางจาก SuperTrend + MACD
    if st == "UP" and macd == "bullish":
        side = "long"
    elif st == "DOWN" and macd == "bearish":
        side = "short"
    else:
        side = "long" if st == "UP" else "short"
    # หา S/R ใกล้ราคาสุด
    supp = sr.get("support", [])
    res = sr.get("resistance", [])
    if side == "long":
        near = supp + [fib618, fib786] if fib618 else supp
        near = [x for x in near if x < last]
        entry = max(near) if near else last * 0.99  # ดีที่สุด=สูงสุดที่ต่ำกว่าราคา
        reason = "ใกล้ Support/Fib (dip-buy)"
    else:
        near = res + [fib618, fib786] if fib618 else res
        near = [x for x in near if x > last]
        entry = min(near) if near else last * 1.01
        reason = "ใกล้ Resistance (mean-revert)"
    sl = entry * (1 - sl_pct / 100) if side == "long" else entry * (1 + sl_pct / 100)
    tp = entry * (1 + tp_pct / 100) if side == "long" else entry * (1 - tp_pct / 100)
    return {
        "symbol": symbol.upper(), "interval": interval,
        "side": side, "entry": round(entry, 4),
        "sl": round(sl, 4), "tp": round(tp, 4),
        "last": round(last, 4), "reason": reason,
        "sr_support": supp, "sr_resistance": res,
        "fib618": fib618, "fib786": fib786,
    }


def run_multi_tf(symbol="BTCUSDT", timeframes=("1h", "4h", "1d"), limit=200):
    """วิเคราะห์หลายไทม์เฟรมพร้อมกัน -> ตารางเปรียบเทียบ + กราฟแต่ละ TF"""
    results = {}
    charts = []
    for tf in timeframes:
        try:
            df, out = analyze(symbol, tf, limit)
            out["chart"] = draw_chart(df, out)
            results[tf] = out
            charts.append(out["chart"]["chart_path"])
        except Exception as e:
            results[tf] = {"error": str(e)}
    # สรุปตารางเรียง TF
    summary = {"symbol": symbol.upper(), "timeframes": timeframes, "rows": []}
    for tf in timeframes:
        o = results.get(tf, {})
        if "error" in o:
            summary["rows"].append({"tf": tf, "error": o["error"]})
            continue
        summary["rows"].append({
            "tf": tf,
            "last": o["last_close"],
            "supertrend": o["supertrend"]["trend"],
            "macd": o["macd"]["cross"],
            "rsi": o["rsi"]["value"],
            "tema": o["tema"]["trend"],
            "ema20": o["ema"].get("ema20"),
            "ema200": o["ema"].get("ema200"),
        })
    return {"summary": summary, "charts": charts, "details": results}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--interval", default="4h")
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--no-chart", action="store_true")
    ap.add_argument("--multi", action="store_true", help="วิเคราะห์หลาย TF (1h/4h/1d)")
    a = ap.parse_args()
    if a.multi:
        res = run_multi_tf(a.symbol)
        print(json.dumps(res["summary"], ensure_ascii=False, indent=2))
        print("\ncharts:", res["charts"])
    else:
        res = run(a.symbol, a.interval, a.limit, draw=not a.no_chart)
        print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
