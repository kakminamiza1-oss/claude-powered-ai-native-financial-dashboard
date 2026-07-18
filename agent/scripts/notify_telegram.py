#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
notify_telegram.py - ส่งข้อความเข้า Telegram ผ่าน Bot API (ไม่需 Hermes gateway)
ต้องตั้ง env:
  TELEGRAM_BOT_TOKEN = "123456:ABC-DEF..."   (จาก @BotFather)
  TELEGRAM_CHAT_ID   = "987654321"           (จาก @userinfobot)

รันมือเอง:  python notify_telegram.py "ข้อความ"
หรือ import: from notify_telegram import send; send("ข้อความ")
ข้อความยาวเกิน 4096 จะแบ่งส่งอัตโนมัติ
"""
import os, sys, urllib.request, json, urllib.parse


def send(text, token=None, chat_id=None, disable_web_page_preview=True):
    token = token or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        # ไม่มี token = ยังไม่ได้ตั้งค่า -> คืน False (ไม่พัง cron)
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    # แบ่งส่งทีละไม่เกิน 4096 ตัวอักษร
    chunks = [text[i:i + 4000] for i in range(0, len(text), 4000)]
    for ch in chunks:
        data = urllib.parse.urlencode({
            "chat_id": chat_id,
            "text": ch,
            "parse_mode": "Markdown",
            "disable_web_page_preview": "true" if disable_web_page_preview else "false",
        }).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=30) as r:
            resp = json.loads(r.read().decode())
        if not resp.get("ok"):
            raise RuntimeError(f"Telegram API error: {resp}")
    return f"sent {len(chunks)} chunk(s)"


if __name__ == "__main__":
    msg = " ".join(sys.argv[1:])
    if not msg:
        msg = "ทดสอบ notify_telegram.py"
    try:
        print(send(msg))
    except Exception as e:
        print(f"ERROR: {e}")
        print("ต้องตั้ง env TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID ก่อน")
