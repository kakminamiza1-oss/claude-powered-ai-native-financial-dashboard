#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
market_watch.py - เฝ้าราคาคริปโต + แจ้งเตือน (local 100% ฟรี)
รันผ่าน cron ของ Hermes ทุก x นาที ไม่需 token

ทำอะไร:
  1. ดึงราคาล่าสุดของ symbol ที่กำหนด
  2. เช็คเงื่อนไข (ตก x% จาก high 24h / ทะลุแนวรับ-ต้าน / RSI เข้าโซน)
  3. ถ้าเข้าเงื่อนไข -> พิมพ์ข้อความแจ้งเตือน (Hermes นำไปส่งได้)
     ถ้าไม่เข้า -> เงียบ (stdout ว่าง) เพื่อไม่ spam

รันมือเอง:  python market_watch.py --symbol BTCUSDT --drop 3
รันกับ cron: ให้ Hermes เรียกสคริปต์นี้ทุก 15 นาที (no_agent=True)

เงื่อนไขที่รองรับ:
  --drop PCT     แจ้งเตือนเมื่อราคาต่ำกว่า high 24h เกิน PCT%
  --rsi-over N   แจ้งเตือนเมื่อ RSI(1h) > N (overbought)
  --rsi-under N  แจ้งเตือนเมื่อ RSI(1h) < N (oversold)
"""
import argparse, sys
from tools import get_price, calc_rsi


def watch(symbol, drop=None, rsi_over=None, rsi_under=None):
    p = get_price(symbol)
    if "error" in p:
        return f"ERROR เช็ค {symbol}: {p['error']}"
    msgs = []
    last = p["last"]
    if drop is not None:
        hi = p["high_24h"]
        fall = (hi - last) / hi * 100 if hi else 0
        if fall >= drop:
            msgs.append(f"⚠️ {symbol} ตก {fall:.2f}% จาก high 24h ({hi} -> {last})")
    if rsi_over is not None or rsi_under is not None:
        r = calc_rsi(symbol, "1h", 14)
        if "error" not in r:
            rsi = r["rsi"]
            if rsi_over is not None and rsi >= rsi_over:
                msgs.append(f"📈 {symbol} RSI 1h = {rsi} (overbought >= {rsi_over})")
            if rsi_under is not None and rsi <= rsi_under:
                msgs.append(f"📉 {symbol} RSI 1h = {rsi} (oversold <= {rsi_under})")
    if not msgs:
        return ""  # เงียบ = ไม่มีอะไร
    head = f"[market_watch {symbol} @ {p['time']}]"
    return head + "\n" + "\n".join(msgs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--drop", type=float, default=2.0, help="แจ้งเมื่อตก x%% จาก high 24h (ค่าตั้งต้น 2)")
    ap.add_argument("--rsi-over", type=float, default=70, help="แจ้งเมื่อ RSI 1h > ค่านี้ (ค่าตั้งต้น 70)")
    ap.add_argument("--rsi-under", type=float, default=30, help="แจ้งเมื่อ RSI 1h < ค่านี้ (ค่าตั้งต้น 30)")
    a = ap.parse_args()
    out = watch(a.symbol, a.drop, a.rsi_over, a.rsi_under)
    if out:
        print(out)  # Hermes จะเอาส่วนนี้ไปส่งแจ้งเตือน
    # ถ้าว่าง = ไม่เตือน (cron watchdog pattern)


if __name__ == "__main__":
    main()
