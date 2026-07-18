#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools.py - เครื่องมือสำหรับ Local AI Agent (ฟรี, local, ไม่需 API key)
รันบนเครื่องคุณเอง 100%  ใช้คู่กับ agent.py / local_chat.py

เครื่องมือที่มี:
  - get_price(symbol)          ดึงราคาล่าสุด + 24h change จาก Binance
  - get_klines(symbol, interval, limit)  ดึงแท่งเทียน (kline)
  - calc_rsi(symbol, interval, period)   คำนวณ RSI จากข้อมูลจริง
  - calc_position(budget, leverage, entry, sl, tp)  คำนวณ position size + R:R
  - web_get(url)               ดึงข้อความจากเว็บ (สกัดด้วย trafilatura ถามี)
ทุกฟังก์ชันคืน dict (JSON-serializable) เพื่อให้โมเดลเอาไปใช้ต่อได้
"""
import json
import urllib.request
from datetime import datetime

BINANCE = "https://api.binance.com/api/v3"


def _get_json(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def get_price(symbol="BTCUSDT"):
    """ดึงราคาล่าสุด + เปลี่ยนแปลง 24h จาก Binance (ฟรี ไม่需 key)"""
    try:
        d = _get_json(f"{BINANCE}/ticker/24hr?symbol={symbol.upper()}")
        return {
            "symbol": symbol.upper(),
            "last": float(d["lastPrice"]),
            "change_24h_pct": float(d["priceChangePercent"]),
            "high_24h": float(d["highPrice"]),
            "low_24h": float(d["lowPrice"]),
            "quote_volume_24h": float(d["quoteVolume"]),
            "time": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        }
    except Exception as e:
        return {"error": str(e)}


def get_klines(symbol="BTCUSDT", interval="1h", limit=50):
    """ดึงแท่งเทียน (open/high/low/close) ล่าสุด"""
    try:
        url = f"{BINANCE}/klines?symbol={symbol.upper()}&interval={interval}&limit={limit}"
        rows = _get_json(url)
        closes = [float(r[4]) for r in rows]
        return {
            "symbol": symbol.upper(),
            "interval": interval,
            "count": len(closes),
            "closes": closes,
            "last_close": closes[-1],
        }
    except Exception as e:
        return {"error": str(e)}


def calc_rsi(symbol="BTCUSDT", interval="1h", period=14):
    """คำนวณ RSI จากข้อมูล kline จริง (Wilder's smoothing)"""
    try:
        k = get_klines(symbol, interval, limit=period + 50)
        if "error" in k:
            return k
        closes = k["closes"]
        gains, losses = [], []
        for i in range(1, len(closes)):
            d = closes[i] - closes[i - 1]
            gains.append(max(d, 0.0))
            losses.append(max(-d, 0.0))
        # เฉลี่ย period สดแรก แล้ว Wilder smoothing
        avg_g = sum(gains[:period]) / period
        avg_l = sum(losses[:period]) / period
        for i in range(period, len(gains)):
            avg_g = (avg_g * (period - 1) + gains[i]) / period
            avg_l = (avg_l * (period - 1) + losses[i]) / period
        rs = (avg_g / avg_l) if avg_l != 0 else 999.0
        rsi = 100 - (100 / (1 + rs))
        return {
            "symbol": symbol.upper(),
            "interval": interval,
            "period": period,
            "rsi": round(rsi, 2),
            "signal": "overbought" if rsi > 70 else ("oversold" if rsi < 30 else "neutral"),
            "time": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        }
    except Exception as e:
        return {"error": str(e)}


def calc_position(budget=100.0, leverage=5.0, entry=None, sl=None, tp=None):
    """คำนวณ position size, liquidation, R:R จากงบ + leverage + จุดเข้า/SL/TP

    - budget    = เงินที่ยอมเสีย (margin) เป็น USDT
    - leverage  = เลเวอเรจ (เช่น 5 = 5x)
    - entry/sl/tp = ราคา (ถ้าไม่ใส่ จะคืนเฉพาะโครงสร้างพื้นฐาน)
    คืน dict พร้อมตาราง Entry/TP/SL + R:R
    """
    try:
        budget = float(budget)
        leverage = float(leverage)
        position = budget * leverage  # notional
        liq = None
        if entry:
            entry = float(entry)
            liq = entry * (1 - 1 / leverage) if leverage > 0 else None
        rr = None
        if entry and sl and tp:
            entry, sl, tp = float(entry), float(sl), float(tp)
            risk = abs(entry - sl)
            reward = abs(tp - entry)
            rr = round(reward / risk, 2) if risk > 0 else None
        return {
            "budget_usdt": budget,
            "leverage": leverage,
            "position_notional": round(position, 2),
            "liquidation_price": round(liq, 4) if liq else None,
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "risk_per_unit": abs(entry - sl) if (entry and sl) else None,
            "reward_per_unit": abs(tp - entry) if (entry and tp) else None,
            "R_R": rr,
            "pnl_if_tp": round(budget * rr, 2) if rr else None,
            "pnl_if_sl": -round(budget, 2) if sl else None,
        }
    except Exception as e:
        return {"error": str(e)}


def calc_position_pct(budget=100.0, leverage=5.0, symbol="BTCUSDT", sl_pct=2.0, tp_pct=4.0):
    """คำนวณ position จาก 'เปอร์เซ็นต์' โดยดึงราคาจริงเอง (ไม่ให้โมเดลคิดเลข)

    - symbol   = คู่เทรด (ดึงราคาจาก Binance)
    - sl_pct   = ห่างลงกี่ % จากราคาเข้า (เช่น 2 = -2%)
    - tp_pct   = ห่างขึ้นกี่ % จากราคาเข้า (เช่น 4 = +4%)
    โมเดลแค่บอก %  เครื่องมือจัดการดึงราคา+คำนวณให้ -> ไม่มีเดาเลข
    """
    try:
        p = get_price(symbol)
        if "error" in p:
            return p
        entry = float(p["last"])
        sl = round(entry * (1 - sl_pct / 100.0), 4)
        tp = round(entry * (1 + tp_pct / 100.0), 4)
        return calc_position(budget, leverage, entry, sl, tp)
    except Exception as e:
        return {"error": str(e)}


def web_get(url):
    """ดึงข้อความจากเว็บ (ใช้ trafilatura ถามี มิฉะนั้น fallback หา <p>)"""
    try:
        import subprocess, sys, importlib.util
        html = None
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=25) as r:
            html = r.read().decode("utf-8", "ignore")
        if importlib.util.find_spec("trafilatura"):
            import trafilatura
            text = trafilatura.extract(html) or ""
        else:
            # fallback: เก็บข้อความใน <p> แบบหยาบ
            import re
            text = " ".join(re.findall(r"<p[^>]*>(.*?)</p>", html, re.S))[:2000]
            text = re.sub(r"<[^>]+>", "", text)
        return {"url": url, "chars": len(text), "text": text[:2000]}
    except Exception as e:
        return {"error": str(e)}


def analyze_chart(symbol="BTCUSDT", interval="4h", limit=200):
    """ดึง kline + คำนวณ EMA/SuperTrend/MACD/TEMA/RSI จาก Binance จริง แล้ววาดกราฟ PNG

    คืนตัวเลขอินดิเคเตอร์ทุกตัว + เส้นทางไฟล์รูป (ส่งให้โมเดลวิสัยทัศน์อ่านต่อได้)
    ใช้เมื่อผู้ใช้ถามกราฟ/เทรนด์/จุดเข้า-ออก หรืออยากเห็นภาพ
    """
    try:
        from indicators import run as ind_run
        res = ind_run(symbol, interval, limit, draw=True)
        return res
    except Exception as e:
        return {"error": str(e)}


def analyze_chart_multi(symbol="BTCUSDT", timeframes="1h,4h,1d", limit=200):
    """วิเคราะห์หลายไทม์เฟรมพร้อมกัน (เรียกเมื่อผู้ใช้อยากเห็นภาพใหญ่/หลาย TF)"""
    try:
        from indicators import run_multi_tf
        tfs = [t.strip() for t in timeframes.split(",") if t.strip()]
        res = run_multi_tf(symbol, tuple(tfs), limit)
        return res
    except Exception as e:
        return {"error": str(e)}


# ===== รายการเครื่องมือสำหรับลงทะเบียนให้โมเดลเรียก (OpenAI-style tools) =====
TOOL_SPECS = [
    {
        "type": "function",
        "function": {
            "name": "get_price",
            "description": "ดึงราคาคริปโตล่าสุด + เปลี่ยนแปลง 24 ชั่วโมงจาก Binance (ฟรี ไม่需 API key)",
            "parameters": {
                "type": "object",
                "properties": {"symbol": {"type": "string", "description": "เช่น BTCUSDT, ETHUSDT, SOLUSDT"}},
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calc_rsi",
            "description": "คำนวณ RSI ล่าสุดจากข้อมูลแท่งเทียนจริงของ Binance",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "เช่น BTCUSDT"},
                    "interval": {"type": "string", "description": "เช่น 1h, 4h, 1d"},
                    "period": {"type": "integer", "description": "ค่ามาตรฐาน 14"},
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calc_position_pct",
            "description": "คำนวณ position (entry/SL/TP/R:R/liquidation) จากงบ+เลเวอเรจ+คู่เทรด โดยดึงราคาจริงเองและหา SL/TP จากเปอร์เซ็นต์ ไม่ต้องใส่ราคาเอง",
            "parameters": {
                "type": "object",
                "properties": {
                    "budget": {"type": "number", "description": "เงินที่ยอมเสีย (USDT)"},
                    "leverage": {"type": "number", "description": "เลเวอเรจ เช่น 5"},
                    "symbol": {"type": "string", "description": "คู่เทรด เช่น BTCUSDT"},
                    "sl_pct": {"type": "number", "description": "ห่างลงกี่ % จากราคาเข้า เช่น 2"},
                    "tp_pct": {"type": "number", "description": "ห่างขึ้นกี่ % จากราคาเข้า เช่น 4"},
                },
                "required": ["budget", "leverage"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_chart",
            "description": "วิเคราะห์กราฟคริปโต 1 ไทม์เฟรม: ดึงแท่งเทียนจริงจาก Binance คำนวณ EMA(20/50/100/200), SuperTrend(10,3), MACD(12,26,9), TEMA, RSI, Fibonacci, Support/Resistance แล้ววาดกราฟ PNG ให้เส้นทางไฟล์ คืนตัวเลขทุกอินดิเคเตอร์",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "คู่เทรด เช่น BTCUSDT"},
                    "interval": {"type": "string", "description": "ไทม์เฟรม เช่น 1h, 4h, 1d"},
                    "limit": {"type": "integer", "description": "จำนวนแท่งเทียน (ค่าตั้งต้น 200)"},
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_chart_multi",
            "description": "วิเคราะห์กราฟหลายไทม์เฟรมพร้อมกัน (1h/4h/1d) ของคู่เทรดเดียว: คืนตารางเปรียบเทียบ SuperTrend/MACD/RSI/TEMA/EMA ทุก TF + เส้นทางไฟล์กราฟแต่ละ TF ใช้เมื่อผู้ใช้อยากเห็นภาพรวมหลาย timeframe",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "คู่เทรด เช่น BTCUSDT"},
                    "timeframes": {"type": "string", "description": "คอมมาแยก เช่น '1h,4h,1d'"},
                    "limit": {"type": "integer", "description": "จำนวนแท่งเทียน (ค่าตั้งต้น 200)"},
                },
                "required": ["symbol"],
            },
        },
    },
]


def dispatch(name, args):
    """เรียกฟังก์ชันตามชื่อ (ใช้โดย agent.py)"""
    args = args or {}
    fn = {
        "get_price": get_price,
        "calc_rsi": calc_rsi,
        "calc_position": calc_position,
        "calc_position_pct": calc_position_pct,
        "analyze_chart": analyze_chart,
        "analyze_chart_multi": analyze_chart_multi,
        "web_get": web_get,
    }.get(name)
    if not fn:
        return {"error": f"unknown tool {name}"}
    return fn(**args)


if __name__ == "__main__":
    # ทดสอบไว้ดูด้วยตัวเอง
    import pprint
    print("== get_price BTCUSDT ==")
    pprint.pprint(get_price("BTCUSDT"))
    print("== calc_rsi BTCUSDT 1h ==")
    pprint.pprint(calc_rsi("BTCUSDT", "1h", 14))
    print("== calc_position 100/5x entry=60000 sl=58500 tp=63000 ==")
    pprint.pprint(calc_position(100, 5, 60000, 58500, 63000))
