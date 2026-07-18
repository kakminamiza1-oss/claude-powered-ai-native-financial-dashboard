#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
agent.py - Local AI Agent แบบ ReAct (Reason + Act)
โมเดลคิด -> เลือก tool -> รัน tool -> ได้ข้อมูล -> คิดรอบ 2 -> ตอบ

จุดเด่น:
  - รัน local 100% (Ollama) ฟรี ไม่需 token
  - โมเดลเรียกเครื่องมือเองได้ (function calling)
  - วนลูปได้หลายรอบจนครบข้อมูล (max_steps ป้องกันหลุด)
  - ใช้ tools.py เป็น "มือ" ดึง Binance / คำนวณ R:R / RSI / วิเคราะห์กราฟ
  - โหมด --vision: ส่งกราฟที่วาดให้โมเดลวิสัยทัศน์ (qwen2.5vl) อ่านสรุป

รัน:  python agent.py "ราคา BTC เท่าไหร่ แล้ว RSI 1h เป็นไง"
      python agent.py --vision "วิเคราะห์กราฟ ETH 4h หน่อย หาจุด dip-buy"
"""
import sys, json, os, urllib.request, argparse, base64
from tools import TOOL_SPECS, dispatch

OLLAMA_API = "http://localhost:11434/api/chat"
MODEL = "qwen2.5:7b"
VISION_MODEL = "qwen2.5vl:7b-64k"

SYS = (
    "คุณคือผู้ช่วยเทรด crypto ภาษาไทย ที่มีเครื่องมือเรียกได้เอง "
    "(function calling) เมื่อต้องการข้อมูลสด หรือคำนวณ ให้เรียก tool ที่เหมาะสม "
    "อย่าคิดเลขหรือเดาราคาเอง ให้ดึงจาก tool เสมอ ตอบสั้น กระชับ เป็นภาษาไทย "
    "และจัดเป็นตารางเมื่อมีตัวเลขหลายค่า"
)


def _chat(model, messages, tools=None, timeout=180):
    payload = {"model": model, "messages": messages, "stream": False}
    if tools:
        payload["tools"] = tools
    req = urllib.request.Request(
        OLLAMA_API, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())["message"]


def _vision_read(image_path, question, model=VISION_MODEL, timeout=200):
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": question, "images": [b64]}],
        "stream": False,
    }
    req = urllib.request.Request(
        OLLAMA_API, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())["message"]["content"]


def run(prompt, model=MODEL, max_steps=5):
    messages = [
        {"role": "system", "content": SYS},
        {"role": "user", "content": prompt},
    ]
    steps_log = []
    for step in range(1, max_steps + 1):
        msg = _chat(model, messages, TOOL_SPECS)
        if msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                fn = tc["function"]
                name = fn["name"]
                args = fn.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {}
                result = dispatch(name, args)
                steps_log.append({"step": step, "tool": name, "args": args, "result": result})
                messages.append({"role": "assistant", "content": msg.get("content", ""), "tool_calls": msg["tool_calls"]})
                messages.append({"role": "tool", "content": json.dumps(result, ensure_ascii=False)})
            continue
        else:
            return {"answer": msg.get("content", ""), "steps": steps_log}
    return {"answer": "(ถึงขีดจำกัดรอบคิด) " + msg.get("content", ""), "steps": steps_log}


def run_vision(prompt, model=MODEL, vision_model=VISION_MODEL, max_steps=5):
    """แบบมีตา: agent วิเคราะห์กราฟด้วย text model แล้วส่งรูปให้ vision model อ่านสรุป แล้วรวมคำตอบ"""
    out = run(prompt, model, max_steps)
    chart_path = None
    for s in out["steps"]:
        r = s.get("result", {})
        if isinstance(r, dict) and "chart" in r and r["chart"].get("chart_path"):
            chart_path = r["chart"]["chart_path"]
    if chart_path and os.path.exists(chart_path):
        try:
            vision_txt = _vision_read(
                chart_path,
                "อ่านกราฟคริปโตนี้: บอกเทรนด์โดยรวม (ขึ้น/ลง/sideway), "
                "ตำแหน่งราคาเทียบ EMA, สถานะ SuperTrend, MACD, RSI และจุดที่น่าสนใจ "
                "สำหรับการเข้าเทรดแบบ dip-buy ตอบภาษาไทยสั้นๆ",
                vision_model,
            )
            out["vision_summary"] = vision_txt
            out["answer"] = out["answer"] + "\n\n[วิเคราะห์จากกราฟโดยโมเดลวิสัยทัศน์]\n" + vision_txt
        except Exception as e:
            out["vision_error"] = str(e)
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("prompt", nargs="*")
    p.add_argument("--model", default=MODEL)
    p.add_argument("--steps", type=int, default=5)
    p.add_argument("--vision", action="store_true",
                   help="โหมดมีตา: วิเคราะห์กราฟแล้วส่งรูปให้ qwen2.5vl อ่านสรุป")
    p.add_argument("--json", action="store_true", help="คืน JSON (steps ด้วย)")
    args = p.parse_args()
    prompt = " ".join(args.prompt)
    if not prompt:
        print("Usage: python agent.py \"คำถาม\" [--model qwen2.5:7b] [--vision]")
        return
    out = run_vision(prompt, args.model, max_steps=args.steps) if args.vision else run(prompt, args.model, args.steps)
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(out["answer"])
        if out["steps"]:
            print("\n--- ขั้นตอนที่ agent ทำ (tool calls) ---")
            for s in out["steps"]:
                print(f"  รอบ {s['step']}: {s['tool']}({s['args']}) -> {json.dumps(s['result'], ensure_ascii=False)[:200]}")


if __name__ == "__main__":
    main()
