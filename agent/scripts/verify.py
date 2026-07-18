#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify.py - ตรวจสอบระบบ Local Crypto Agent (17 จุด)
รัน:  python verify.py   (จาก scripts/)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ok = 0
total = 0
def t(name, fn):
    global ok, total
    total += 1
    try:
        r = fn()
        ok += 1
        print(f"  [OK] {name}")
    except Exception as e:
        print(f"  [FAIL] {name}: {type(e).__name__}: {e}")

print("=== VERIFY: Local Crypto Agent (17 points) ===")
import tools, indicators, notify_telegram, agent, webui, morning_brief, futures_testnet

t("get_price.last", lambda: tools.get_price("BTCUSDT")["last"] > 0)
t("calc_rsi range", lambda: 0 <= tools.calc_rsi("BTCUSDT", "1h")["rsi"] <= 100)
t("calc_position R:R", lambda: tools.calc_position(100, 5, 64000, 62500, 67000)["R_R"] == 2.0)
t("calc_position_pct", lambda: "R_R" in tools.calc_position_pct(100, 5, "BTCUSDT", 2, 4))
t("analyze_chart draw", lambda: tools.analyze_chart("BTCUSDT", "4h")["chart"]["size_kb"] > 0)
t("analyze_chart_multi", lambda: len(tools.analyze_chart_multi("ETHUSDT")["summary"]["rows"]) == 3)
t("fetch_klines", lambda: len(indicators.fetch_klines("BTCUSDT", "4h", 50)) == 50)
t("supertrend", lambda: len(indicators.supertrend(indicators.fetch_klines("BTCUSDT", "4h", 100))[0]) == 100)
t("find_signals", lambda: len(indicators.find_signals(indicators.fetch_klines("BTCUSDT", "4h", 200))) > 0)
t("vwap", lambda: len(indicators.vwap(indicators.fetch_klines("BTCUSDT", "4h", 100))) > 0)
t("volume_profile", lambda: "poc" in indicators.volume_profile(indicators.fetch_klines("BTCUSDT", "4h", 100)))
t("analyze signals", lambda: len(indicators.analyze("BTCUSDT", "4h", 200)[1]["signals"]) > 0)
t("run_multi_tf", lambda: len(indicators.run_multi_tf("BTCUSDT")["charts"]) == 3)
t("notify no-token", lambda: notify_telegram.send("x") is False)
t("agent.run_vision", lambda: hasattr(agent, "run_vision"))
t("webui routes", lambda: all(rt in str(webui.app.url_map) for rt in ["/chart_meta", "/calc_plan", "/plan_chart", "/place_testnet"]))
t("morning_brief 4sym", lambda: len(morning_brief.SYMBOLS) == 4)

print(f"\n=== RESULT: {ok}/{total} PASS ===")
sys.exit(0 if ok == total else 1)
