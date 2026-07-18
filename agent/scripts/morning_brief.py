#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
morning_brief.py - สรุปกราฟ crypto เช้า (รันด้วย cron)
วิเคราะห์ BTCUSDT + ETHUSDT ไทม์เฟรม 4h แบบมีตา (agent --vision)
+ คำนวณ position จริง (calc_position_pct) ให้ตาราง Entry/TP/SL/R:R
พิมพ์สรุป stdout + (ถ้ามี Token) ส่งเข้า Telegram ผ่าน notify_telegram.py

รัน:  python morning_brief.py
env:  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID  (ไม่ใส่ = ส่งแค่ stdout)
"""
import subprocess, sys, os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SYMBOLS = [("BTCUSDT", "4h"), ("ETHUSDT", "4h"), ("SOLUSDT", "4h"), ("BNBUSDT", "4h")]


def run_agent(args):
    return subprocess.run(
        [sys.executable, os.path.join(SCRIPT_DIR, "agent.py"), *args],
        capture_output=True, text=True, timeout=400,
    ).stdout.strip()


def main():
    lines = ["📊 Morning Brief (Local AI, ฟรี 100%)"]
    briefs = []
    for sym, interval in SYMBOLS:
        # 1) วิเคราะห์กราฟแบบมีตา
        ta = run_agent(["--vision",
                        f"วิเคราะห์กราฟ {sym} ไทม์เฟรม {interval}: บอกเทรนด์, สถานะ SuperTrend/MACD/RSI, "
                        f"และจุด dip-buy ที่น่าสนใจ (อิงแนวรับ/EMA/Fib) สั้นๆ ภาษาไทย", "smart"])
        # 2) คำนวณ position จริง (งบ 100, lev 5, SL 2% TP 4%) -> ไม่ให้โมเดลเดาเลข
        pos = run_agent(["คำนวณ position งบ 100 leverage 5 คู่ " + sym +
                         " โดยให้ SL ห่างลง 2% TP ห่างขึ้น 4% จากราคาปัจจุบัน", "smart"])
        block = f"\n=== {sym} {interval} ===\n[TA]\n{ta}\n\n[Position Plan]\n{pos}"
        lines.append(block)
        briefs.append(block)

    summary = "\n".join(lines)

    # ส่ง Telegram ถ้ามี token
    if os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"):
        try:
            import notify_telegram
            notify_telegram.send(summary)
            print("[sent to telegram]")
        except Exception as e:
            print(f"[telegram error: {e}]")
    print(summary)


if __name__ == "__main__":
    main()
