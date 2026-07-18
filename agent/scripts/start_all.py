#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
start_all.py - Launcher เดียวสำหรับ Local Crypto Agent
รัน web UI + ช่วยตั้ง cron (market_watch + morning_brief)

รัน:  python start_all.py
  -> เปิด Flask webui ที่ http://localhost:5566 (background)
  -> พรินท์คำสั่งตั้ง cron ให้พร้อม (หรือตั้งอัตโนมัติถ้ามี hermes cli)

หมายเหตุ: cron จริงต้องตั้งผ่าน Hermes (cronjob tool) หรือ Windows Task Scheduler
สคริปต์นี้เน้นรัน webui + แสดงคำสั่งตั้งเวลา
"""
import os, sys, subprocess, webbrowser, time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def start_webui():
    print("🚀 เริ่ม Web UI (Flask)...")
    proc = subprocess.Popen(
        [sys.executable, os.path.join(SCRIPT_DIR, "webui.py")],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    time.sleep(2)
    try:
        webbrowser.open("http://localhost:5566")
        print("   เปิด browser: http://localhost:5566")
    except Exception:
        print("   (เปิด browser มือเอง: http://localhost:5566)")
    return proc


def print_cron_help():
    print("\n📅 ตั้งเวลาอัตโนมัติ (cron) แนะนำ:")
    print("   1) เฝ้าราคาทุก 15 นาที:")
    print(f'      python "{os.path.join(SCRIPT_DIR, "market_watch.py")}" --symbol BTCUSDT --drop 2 --rsi-over 70 --rsi-under 30')
    print("      → ตั้งเป็น cron '*/15 * * * *' (Hermes cronjob หรือ Task Scheduler)")
    print("   2) สรุปกราฟเช้า 07:00:")
    print(f'      python "{os.path.join(SCRIPT_DIR, "morning_brief.py")}"')
    print("      → ตั้งเป็น cron '0 7 * * *'")
    print("\n   ถ้าต้องการให้ Hermes จัดการ: ใช้คำสั่ง cronjob ในแชท Hermes")
    print("   หรือ Windows: Task Scheduler โ Calling python + สคริปต์ข้างต้น")


def main():
    print("=" * 55)
    print("  LOCAL CRYPTO AGENT — START ALL")
    print("  Ollama + Binance | ฟรี 100% | local")
    print("=" * 55)
    # ตรวจ Ollama
    try:
        import urllib.request
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5) as r:
            if r.status == 200:
                print("✅ Ollama พร้อม")
            else:
                print("⚠️ Ollama ตอบผิดปกติ")
    except Exception:
        print("❌ Ollama ไม่ทำงาน — รัน 'ollama serve' ก่อน")
        return
    proc = start_webui()
    print_cron_help()
    print("\nกด Ctrl+C เพื่อหยุด Web UI")
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        print("\nหยุด Web UI แล้ว")


if __name__ == "__main__":
    main()
