#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
futures_testnet.py - วางออเดอร์จำลองบน Binance USD-M Futures TESTNET (ไม่ใช้เงินจริง)
Testnet = sandbox ของ Binance ต้องสมัครแยกต่างหากที่ https://testnet.binancefuture.com
แล้วเอา API Key/Secret มาตั้ง env:

  BINANCE_TESTNET_KEY    = "key จาก testnet"
  BINANCE_TESTNET_SECRET = "secret จาก testnet"

ฟังก์ชัน:
  place_market(symbol, side, qty)        -> วาง market order จำลอง
  place_limit(symbol, side, qty, price)  -> วาง limit order จำลอง
  set_tp_sl(symbol, position_side, tp, sl) -> ตั้ง TP/SL (ใช้ ORDER command)
  get_balance()                          -> ดูยอดจำลอง
  get_positions()                        -> ดูโพซิชันที่เปิดอยู่

หมายเหตุ: ทุกออเดอร์เป็นบน TESTNET เท่านั้น ไม่มีผลกับบัญชีจริง
"""
import os, time, hmac, hashlib, urllib.request, urllib.parse, json


BASE = "https://testnet.binancefuture.com"


def _headers():
    key = os.environ.get("BINANCE_TESTNET_KEY")
    secret = os.environ.get("BINANCE_TESTNET_SECRET")
    if not key or not secret:
        raise RuntimeError("ขาด BINANCE_TESTNET_KEY / BINANCE_TESTNET_SECRET ใน env")
    return key, secret


def _sign(query_string, secret):
    return hmac.new(secret.encode(), query_string.encode(), hashlib.sha256).hexdigest()


def _req(method, path, params=None):
    key, secret = _headers()
    params = params or {}
    params["timestamp"] = int(time.time() * 1000)
    params["recvWindow"] = 60000
    qs = urllib.parse.urlencode(params)
    sig = _sign(qs, secret)
    qs += f"&signature={sig}"
    url = f"{BASE}{path}?{qs}"
    req = urllib.request.Request(url, headers={"X-MBX-APIKEY": key}, method=method)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def place_market(symbol="BTCUSDT", side="BUY", qty=0.001):
    """วาง market order บน testnet (side=BUY=long, SELL=short)"""
    return _req("POST", "/fapi/v1/order", {
        "symbol": symbol.upper(), "side": side.upper(),
        "type": "MARKET", "quantity": qty, "newOrderRespType": "RESULT",
    })


def place_limit(symbol="BTCUSDT", side="BUY", qty=0.001, price=None):
    if price is None:
        raise ValueError("limit order ต้องระบุ price")
    return _req("POST", "/fapi/v1/order", {
        "symbol": symbol.upper(), "side": side.upper(),
        "type": "LIMIT", "quantity": qty, "price": price,
        "timeInForce": "GTC", "newOrderRespType": "RESULT",
    })


def set_tp_sl(symbol="BTCUSDT", position_side="LONG", tp=None, sl=None):
    """ตั้ง TP/SL แบบแยก (ใช้ ORDER command BOTH สำหรับ testnet)"""
    out = {}
    if tp:
        out["tp"] = _req("POST", "/fapi/v1/order", {
            "symbol": symbol.upper(), "side": "SELL" if position_side == "LONG" else "BUY",
            "type": "TAKE_PROFIT_MARKET", "quantity": 0,  # จัดการแยกต่างหาก
            "stopPrice": tp, "positionSide": position_side, "reduceOnly": True,
        })
    if sl:
        out["sl"] = _req("POST", "/fapi/v1/order", {
            "symbol": symbol.upper(), "side": "SELL" if position_side == "LONG" else "BUY",
            "type": "STOP_MARKET", "quantity": 0,
            "stopPrice": sl, "positionSide": position_side, "reduceOnly": True,
        })
    return out


def get_balance():
    return _req("GET", "/fapi/v2/balance")


def get_positions():
    return _req("GET", "/fapi/v2/positionRisk")


if __name__ == "__main__":
    import sys
    try:
        print("== Balance (testnet) ==")
        print(json.dumps(get_balance(), ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"ERROR: {e}")
        print("ต้องตั้ง env BINANCE_TESTNET_KEY + BINANCE_TESTNET_SECRET")
