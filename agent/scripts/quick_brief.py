#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""quick_brief.py - สรุปตลาดเช้าเร็ว (<2 นาที) ดึงราคา+RSI จริงจาก Binance แล้วให้ local model สรุปไทย
รัน: python quick_brief.py  | env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (ถ้ามี=ส่ง TG)"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tools import get_price, calc_rsi
from local_chat import chat_text

SYMBOLS = [("BTCUSDT", "4h"), ("ETHUSDT", "4h"), ("SOLUSDT", "4h"), ("BNBUSDT", "4h")]


def snapshot():
    lines = ["📊 Quick Brief (Local AI · ฟรี 100%)"]
    for sym, iv in SYMBOLS:
        p, r = get_price(sym), calc_rsi(sym, iv, 14)
        if "error" in p or "error" in r:
            lines.append(f"\n=== {sym} {iv} ===\n[error] {p.get('error')} / {r.get('error')}")
            continue
        lines.append(f"\n=== {sym} {iv} ===\nราคา: {p['last']:,.2f} ({p['change_24h_pct']:+.2f}% 24h)\n"
                     f"RSI: {r['rsi']} -> {r['signal']}\nHigh/Low: {p['high_24h']:,.2f} / {p['low_24h']:,.2f}")
    return "\n".join(lines)


def main():
    raw = snapshot()
    prompt = ("จากข้อมูลนี้ สรุปสั้นๆ ภาษาไทย ต่อคู่: เทรนด์ (ขึ้น/ลง/sideway จาก change24h+RSI), "
              "ถ้า RSI oversold/overbought ชี้ 'น่าสนใจ dip-buy' หรือ 'ระวัง chase' ห้ามจีน:\n\n" + raw)
    try:
        summary = chat_text(prompt, "smart")
    except Exception as e:
        summary = f"(model error: {e})\n\n{raw}"
    out = raw + "\n\n--- สรุปโดย AI ---\n" + summary
    _tok = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    _cid = os.environ.get("TELEGRAM_CHAT_ID", "")
    if _tok and _cid and "YOUR_" not in _tok and "YOUR_" not in _cid:
        try:
            import notify_telegram
            notify_telegram.send(out)
            print("[sent to telegram]")
        except Exception as e:
            print(f"[telegram error: {e}]")
    print(out)


if __name__ == "__main__":
    main()
