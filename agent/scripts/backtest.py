#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backtest.py - ทดสอบสัญญาณย้อนหลังเพื่อดู win rate จริง (Decision Support เท่านั้น)
ไม่ใช้เงินจริง ไม่วางออเดอร์ วิ่งบนข้อมูล Binance ย้อนหลังのみ

กลยุทธ์ทดสอบ (ให้ตรงสไตล์คุณ: dip-buyer, R:R 2:1):
  - LONG เมื่อ: SuperTrend=UP + MACD bullish + ราคาตรง/ใกล้ Support หรือ Fibonacci 61.8%
  - SHORT เมื่อ: SuperTrend=DOWN + MACD bearish + ราคาใกล้ Resistance
  - SL = 2% จาก entry, TP = 4% จาก entry (R:R 2:1 ตามสไตล์คุณ)
  - ถือไม่เกิน N แท่ง (exit เมื่อถึง SL/TP หรือครบกำหนด)

รัน:  python backtest.py --symbol BTCUSDT --interval 4h --days 30
"""
import argparse, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from indicators import fetch_klines, supertrend, macd, rsi, ema, support_resistance, fib_retracement


def gen_signals(df):
    """คืน list สัญญาณเข้า (long/short) ตามกฎข้างต้น พร้อมราคา entry/SL/TP"""
    c = df["close"]
    st, trend = supertrend(df)
    line, sig, hist = macd(c)
    r = rsi(c, 14)
    sr = support_resistance(df)
    fib = fib_retracement(df)
    supp = sr.get("support", [])
    res = sr.get("resistance", [])
    fib618 = fib.get("levels", {}).get("61.8%")
    rows = []
    for i in range(50, len(df)):
        price = float(c.iloc[i])
        # เงื่อนไข long
        if trend.iloc[i] == 1 and line.iloc[i] > sig.iloc[i]:
            # ใกล้ support หรือ fib618
            near_supp = any(abs(price - s) / price < 0.01 for s in supp) if supp else False
            near_fib = abs(price - fib618) / price < 0.01 if fib618 else False
            if near_supp or near_fib:
                rows.append({"i": i, "side": "long", "entry": price})
        # เงื่อนไข short
        elif trend.iloc[i] == -1 and line.iloc[i] < sig.iloc[i]:
            near_res = any(abs(price - s) / price < 0.01 for s in res) if res else False
            if near_res:
                rows.append({"i": i, "side": "short", "entry": price})
    return rows


def simulate(df, signals, sl_pct=2.0, tp_pct=4.0, max_bars=20):
    """จำลองแต่ละสัญญาณ: เข้าแล้วรอถึง SL/TP หรือครบ max_bars"""
    c = df["close"].values
    n = len(c)
    trades = []
    for s in signals:
        i = s["i"]
        entry = s["entry"]
        side = s["side"]
        sl = entry * (1 - sl_pct / 100) if side == "long" else entry * (1 + sl_pct / 100)
        tp = entry * (1 + tp_pct / 100) if side == "long" else entry * (1 - tp_pct / 100)
        exit_price = None
        exit_reason = None
        for j in range(i + 1, min(i + 1 + max_bars, n)):
            low = float(df["low"].iloc[j]); high = float(df["high"].iloc[j])
            if side == "long":
                if low <= sl: exit_price, exit_reason = sl, "SL"; break
                if high >= tp: exit_price, exit_reason = tp, "TP"; break
            else:
                if high >= sl: exit_price, exit_reason = sl, "SL"; break
                if low <= tp: exit_price, exit_reason = tp, "TP"; break
        if exit_price is None:
            exit_price = float(c[min(i + max_bars, n - 1)])
            exit_reason = "timeout"
        pnl_pct = (exit_price - entry) / entry * 100 * (1 if side == "long" else -1)
        trades.append({"side": side, "entry": entry, "exit": exit_price,
                       "reason": exit_reason, "pnl_pct": pnl_pct})
    return trades


def summarize(trades):
    if not trades:
        return {"trades": 0}
    wins = [t for t in trades if t["pnl_pct"] > 0]
    losses = [t for t in trades if t["pnl_pct"] <= 0]
    win_rate = len(wins) / len(trades) * 100
    avg_win = sum(t["pnl_pct"] for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t["pnl_pct"] for t in losses) / len(losses) if losses else 0
    expectancy = (len(wins) * avg_win + len(losses) * avg_loss) / len(trades)
    tp_hits = sum(1 for t in trades if t["reason"] == "TP")
    sl_hits = sum(1 for t in trades if t["reason"] == "SL")
    return {
        "trades": len(trades),
        "win_rate": round(win_rate, 1),
        "avg_win_pct": round(avg_win, 2),
        "avg_loss_pct": round(avg_loss, 2),
        "expectancy_pct": round(expectancy, 2),
        "tp_hits": tp_hits, "sl_hits": sl_hits,
        "net_pct": round(sum(t["pnl_pct"] for t in trades), 2),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--interval", default="4h")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--sl", type=float, default=2.0)
    ap.add_argument("--tp", type=float, default=4.0)
    a = ap.parse_args()
    # คำนวณจำนวนแท่ง: days * 24h / interval_hours
    ih = {"15m": 0.25, "1h": 1, "4h": 4, "1d": 24}[a.interval]
    limit = int(a.days * 24 / ih) + 60
    print(f"=== BACKTEST {a.symbol} {a.interval} ย้อนหลัง {a.days} วัน (limit={limit}) ===")
    df = fetch_klines(a.symbol, a.interval, limit)
    print(f"ดึงข้อมูลได้ {len(df)} แท่ง")
    sigs = gen_signals(df)
    print(f"สัญญาณที่เข้าเงื่อนไข: {len(sigs)}")
    trades = simulate(df, sigs, a.sl, a.tp)
    s = summarize(trades)
    print("\n--- ผลลัพธ์ ---")
    print(f"จำนวนเทรดจำลอง: {s.get('trades')}")
    if s.get("trades"):
        print(f"Win Rate: {s['win_rate']}%")
        print(f"TP hits: {s['tp_hits']} | SL hits: {s['sl_hits']}")
        print(f"Avg Win: +{s['avg_win_pct']}% | Avg Loss: {s['avg_loss_pct']}%")
        print(f"Expectancy ต่อเทรด: {s['expectancy_pct']}%")
        print(f"Net PnL (สมมติเทรดละเท่ากัน): {s['net_pct']}%")
        print("\nคำเตือน: นี้คือ backtest บนประวัติศาสตร์ ไม่รับประกันอนาคต")


if __name__ == "__main__":
    main()
