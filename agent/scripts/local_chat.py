#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Local AI assistant via Ollama - FREE forever, no tokens, runs on your GPU.
Features:
  - Text chat (fast / smart / think models)
  - Image analysis (vision model) - send chart screenshots for trading read
  - Interactive loop mode (chat multiple turns, like Hermes but lightweight)

Usage:
  python local_chat.py "คำถามเดียว"                 -> one-shot text (smart model)
  python local_chat.py "คำถาม" fast                 -> one-shot with fast model
  python local_chat.py --image chart.png "วิเคราะห์" -> analyze image (vision model)
  python local_chat.py --loop                       -> interactive multi-turn chat
  python local_chat.py --loop --image chart.png     -> start loop, first msg has image

Requires: ollama serve running (auto-starts app on login usually)
"""
import sys, json, urllib.request, argparse, os

TEXT_MODELS = {
    "fast": "qwen2.5:3b",
    "smart": "qwen2.5:7b-64k",
    "think": "qwq:64k",
}
VISION_MODEL = "qwen2.5vl:7b-64k"
DEFAULT_TEXT = "smart"
OLLAMA_API = "http://localhost:11434/api/chat"


def _load_sys():
    """โหลด system prompt จาก system_prompt.txt (แก้เองได้) ถ้าไม่มีใช้ fallback ภาษาไทย"""
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "system_prompt.txt")
    try:
        with open(p, "r", encoding="utf-8") as f:
            txt = f.read().strip()
            if txt:
                return {"role": "system", "content": txt}
    except Exception:
        pass
    return {"role": "system", "content": "คุณคือผู้ช่วย AI ภาษาไทย รันบนเครื่องตัวเอง ตอบภาษาไทยสั้นๆ กระชับ"}


SYS_MSG = _load_sys()

# ท้ายทุกข้อความผู้ใช้: บังคับ qwen2.5 ไม่ code-switch เป็นจีน
THAI_ONLY = "\n\n[บังคับ: ตอบภาษาไทย 100% ห้ามใช้ตัวอักษรจีน/ CJK ทุกชนิดเด็ดขาด ใช้ได้เฉพาะคำเทรดอังกฤษ (Long/Short/TP/SL/R:R/leverage/entry/funding)]"


def _post(payload, timeout=300):
    req = urllib.request.Request(
        OLLAMA_API,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())["message"]["content"]
    except Exception as e:
        return f"ERROR: {e}\n(ตรวจว่า 'ollama serve' ทำงานอยู่: tasklist | findstr ollama)"


def chat_text(prompt, model=DEFAULT_TEXT):
    model = TEXT_MODELS.get(model, model)
    return _post({
        "model": model,
        "messages": [SYS_MSG, {"role": "user", "content": prompt + THAI_ONLY}],
        "stream": False,
    })


def chat_with_image(prompt, image_path, model=VISION_MODEL):
    if not os.path.exists(image_path):
        return f"ERROR: ไม่พบไฟล์รูป {image_path}"
    with open(image_path, "rb") as f:
        import base64
        b64 = base64.b64encode(f.read()).decode()
    return _post({
        "model": model,
        "messages": [SYS_MSG, {
            "role": "user",
            "content": prompt + THAI_ONLY,
            "images": [b64],
        }],
        "stream": False,
    }, timeout=400)


def loop_mode(image_path=None):
    print("=" * 50)
    print(" LOCAL AI LOOP (free, no tokens)")
    print(" พิมพ์ 'exit' หรือ ' quit' เพื่อออก")
    print(" โมเดล text:", DEFAULT_TEXT, "| vision:", VISION_MODEL)
    print("=" * 50)
    history = []
    first = True
    while True:
        try:
            if first and image_path:
                user_in = input("คุณ (พร้อมรูป): ").strip()
            else:
                user_in = input("คุณ: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nออกแล้ว")
            break
        if user_in.lower() in ("exit", "quit", "ออก"):
            print("ออกแล้ว / Bye")
            break
        if not user_in:
            continue

        if first and image_path:
            resp = chat_with_image(user_in, image_path)
            first = False
        else:
            history.append({"role": "user", "content": user_in + THAI_ONLY})
            # keep last 10 turns to fit context
            msgs = [SYS_MSG] + history[-10:]
            resp = _post({
                "model": TEXT_MODELS[DEFAULT_TEXT],
                "messages": msgs,
                "stream": False,
            })
            history.append({"role": "assistant", "content": resp})

        print("\nAI:", resp, "\n")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("prompt", nargs="*", help="ข้อความคำถาม (ถ้าไม่ระบุใช้ --loop)")
    p.add_argument("--image", help="วิเคราะห์ไฟล์รูป (chart screenshot)")
    p.add_argument("--model", default=DEFAULT_TEXT, help="fast/smart/think")
    p.add_argument("--loop", action="store_true", help="โหมดแชทหลายรอบ")
    p.add_argument("--agent", action="store_true",
                   help="โหมด Agent: โมเดลเรียกเครื่องมือเอง (ดึงราคา/คำนวณ R:R/RSI)")
    args = p.parse_args()

    prompt = " ".join(args.prompt)

    if args.agent:
        # โหมด Agent - มีมือมีตา (เรียก tools.py เองได้)
        try:
            from agent import run as agent_run
        except ImportError:
            print("ERROR: ไม่พบ agent.py (ต้องอยู่โฟลเดอร์เดียวกัน)")
            return
        out = agent_run(prompt, model=TEXT_MODELS.get(args.model, args.model))
        print(out["answer"])
        if out["steps"]:
            print("\n--- ขั้นตอนที่ agent ทำ ---")
            for s in out["steps"]:
                print(f"  รอบ {s['step']}: {s['tool']}({s['args']})")
        return

    if args.loop:
        loop_mode(args.image)
        return

    if args.image:
        if not prompt:
            prompt = "วิเคราะห์รูปนี้และบอกจุดสำคัญ"
        print(chat_with_image(prompt, args.image))
        return

    if not prompt:
        print("Usage: python local_chat.py \"คำถาม\" [fast|smart|think]")
        print("       python local_chat.py --image chart.png \"วิเคราะห์\"")
        print("       python local_chat.py --loop")
        print("       python local_chat.py --agent \"ราคา BTC + RSI 1h\"   # โหมดมีมือมีตา")
        return

    print(chat_text(prompt, args.model))


if __name__ == "__main__":
    main()
