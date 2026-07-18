#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
webui.py - Web UI เล็กๆ สำหรับ Local Crypto Agent (Flask, local 100%)
เปิด browser -> ดูกราฟ + พิมพ์ถาม agent ได้โดยไม่ต้องพิมพ์ terminal

 Routes:
   /                -> หน้าแรก (ฟอร์มเลือก symbol/interval + กล่องถาม agent)
   /chart?sym=BTC&tf=4h&multi=0  -> คืนรูป PNG กราฟ
   /ask?q=...&vision=1 -> คืนข้อความตอบจาก agent (เรียก agent.py แบบ subprocess)

รัน:  python webui.py
แล้วเปิด:  http://localhost:5566
"""
import os, subprocess, sys, io, base64
from flask import Flask, request, render_template_string, send_file, Response

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)

INDEX = """
<!doctype html>
<html lang="th">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Local Crypto Agent</title>
<style>
  body{font-family:'Segoe UI',Tahoma,sans-serif;margin:0;background:#0d1117;color:#e6edf3}
  header{background:#161b22;padding:12px 20px;border-bottom:1px solid #30363d}
  h1{margin:0;font-size:18px;color:#58a6ff}
  .wrap{max-width:1100px;margin:20px auto;padding:0 16px}
  .bar{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px}
  input,select,button{background:#21262d;color:#e6edf3;border:1px solid #30363d;
    padding:8px 10px;border-radius:6px;font-size:14px}
  button{cursor:pointer;background:#238636;color:#fff;border:none}
  button:hover{background:#2ea043}
  .chk{display:flex;align-items:center;gap:4px}
  #chart{width:100%;border:1px solid #30363d;border-radius:8px;background:#fff;margin-bottom:16px}
  #answer{white-space:pre-wrap;background:#161b22;border:1px solid #30363d;
    border-radius:8px;padding:14px;min-height:60px;font-size:14px;line-height:1.5}
  .hint{color:#8b949e;font-size:12px;margin:4px 0 14px}
</style>
</head>
<body>
<header><h1>🤖 Local Crypto Agent (Ollama + Binance, ฟรี 100%)</h1></header>
<div class="wrap">
  <div class="bar">
    <input id="sym" value="BTCUSDT" size="10" title="คู่เทรด">
    <select id="tf">
      <option value="1h">1h</option>
      <option value="4h" selected>4h</option>
      <option value="1d">1d</option>
      <option value="15m">15m</option>
    </select>
    <label class="chk"><input type="checkbox" id="multi"> หลาย TF (1h/4h/1d)</label>
    <label class="chk"><input type="checkbox" id="vision" checked> โหมดมีตา ( vision)</label>
    <button onclick="loadChart()">📈 โหลดกราฟ</button>
  </div>
  <div class="hint">กราฟคำนวณจาก Binance จริง: EMA/SuperTrend/MACD/TEMA/RSI/Fib/SR/VWAP/VolumeProfile | วงกลม=สัญญาณ</div>
  <img id="chart" src="" alt="กราฟจะโผล่ที่นี่" usemap="#chartmap">

  <div class="bar" style="margin-top:10px">
    <span style="color:#8b949e;font-size:13px">คลิกบนกราฟ 3 จุด (Entry → SL → TP):</span>
    <button onclick="setMode('entry')" id="b_entry">📍 Entry</button>
    <button onclick="setMode('sl')" id="b_sl">🛑 SL</button>
    <button onclick="setMode('tp')" id="b_tp">🎯 TP</button>
    <input id="budget" value="100" size="5" title="งบ USDT"> USDT
    <input id="leverage" value="5" size="4" title="เลเวอเรจ"> x
    <button onclick="calcPlan()">⚖️ คำนวณ R:R</button>
    <button onclick="savePlan()">💾 บันทึกแผน PNG</button>
    <button onclick="autoPlan()">🤖 Auto Plan</button>
    <button onclick="openReport()">📄 รายงานโชว์ภรรยา</button>
    <button onclick="openPdf()">📑 บันทึก PDF</button>
    <button onclick="placeTestnet()">🧪 วางออเดอร์จำลอง (Testnet)</button>
    <button onclick="clearPts()">ล้าง</button>
  </div>
  <div id="pts" style="font-size:12px;color:#8b949e;margin:4px 0"></div>
  <div style="font-size:11px;color:#6e7681;margin:2px 0 10px;max-width:900px">
    🧪 <b>Testnet</b> คือของแถม (ไม่ใช้เงินจริง): ต้องสมัครฟรีที่ <code>testnet.binancefuture.com</code> แล้วตั้ง env <code>BINANCE_TESTNET_KEY</code> + <code>BINANCE_TESTNET_SECRET</code> ก่อนถึงใช้งานได้ &mdash; เครื่องมือวางแผนหลัก (กราฟ/R:R/รายงาน) ไม่ต้องตั้งอะไรใช้ได้เลย
  </div>

  <div class="bar">
    <input id="q" style="flex:1" placeholder="ถาม agent เช่น 'วิเคราะห์กราฟนี้ หาจุด dip-buy' หรือ 'คำนวณ position งบ 100 leverage 5 SL 2% TP 4%'">
    <button onclick="ask()">💬 ถาม</button>
  </div>
  <div id="answer">พิมพ์คำถามแล้วกดถาม...</div>
</div>

<script>
let mode='entry';
let pts={entry:null,sl:null,tp:null};
let chartMeta=null;  // {ymin,ymax,plotTop,plotBottom,imgW,imgH}

function setMode(m){mode=m;document.getElementById('pts').textContent='คลิกจุด: '+m+' (บนกราฟ)';}

function clearPts(){pts={entry:null,sl:null,tp:null};updatePts();}

function updatePts(){
  const f=v=>pts[v]?pts[v].toFixed(2):'-';
  document.getElementById('pts').textContent=
    `Entry: ${f('entry')}  |  SL: ${f('sl')}  |  TP: ${f('tp')}`;
}

// แปลง pixel y -> ราคา ด้วย bbox จริงของ pane ราคา (จาก matplotlib)
function pxToPrice(clientY, img){
  if(!chartMeta || !chartMeta.top) return null;
  const rect=img.getBoundingClientRect();
  const yInImg=(clientY-rect.top)*(img.naturalHeight/rect.height);
  const {ymin,ymax,top,bottom}=chartMeta;
  // สัดส่วนภายใน pane ราคา (top=บนสุด, bottom=ล่างสุด ของ pane)
  const frac=(yInImg-top)/(bottom-top);
  frac_clamped=Math.max(0,Math.min(1,frac));
  return ymin+(1-frac_clamped)*(ymax-ymin);
}

document.getElementById('chart').addEventListener('click',function(e){
  const price=pxToPrice(e.clientY,this);
  if(price===null){document.getElementById('pts').textContent='โหลดกราฟก่อน หรือกราฟไม่มี metadata';return;}
  pts[mode]=price; updatePts();
});

async function loadChart(){
  const sym=document.getElementById('sym').value;
  const tf=document.getElementById('tf').value;
  const multi=document.getElementById('multi').checked;
  let url='/chart?sym='+encodeURIComponent(sym)+'&tf='+tf;
  if(multi) url+='&multi=1';
  // ดึง metadata ราคา (ymin/ymax ของ pane บน) จาก API แยก
  try{
    const m=await fetch('/chart_meta?sym='+encodeURIComponent(sym)+'&tf='+tf).then(r=>r.json());
    chartMeta=m;
  }catch(e){chartMeta=null;}
  document.getElementById('chart').src=url+'&t='+Date.now();
  pts={entry:null,sl:null,tp:null}; updatePts();
}
function ask(){
  const q=document.getElementById('q').value;
  const sym=document.getElementById('sym').value;
  const vision=document.getElementById('vision').checked?1:0;
  const box=document.getElementById('answer');
  if(!q){box.textContent='พิมพ์คำถามก่อนนะ';return;}
  box.textContent='⏳ กำลังคิด...';
  fetch('/ask?q='+encodeURIComponent(q+' '+sym)+'&vision='+vision)
    .then(r=>r.text())
    .then(t=>box.textContent=t)
    .catch(e=>box.textContent='ERROR: '+e);
}
function calcPlan(){
  const box=document.getElementById('answer');
  if(!pts.entry||!pts.sl||!pts.tp){box.textContent='คลิกกำหนด Entry/SL/TP ครบ 3 จุดบนกราฟก่อน';return;}
  const budget=document.getElementById('budget').value;
  const lev=document.getElementById('leverage').value;
  const u='/calc_plan?entry='+pts.entry+'&sl='+pts.sl+'&tp='+pts.tp+'&budget='+budget+'&leverage='+lev;
  box.textContent='⏳ คำนวณ...';
  fetch(u).then(r=>r.text()).then(t=>box.textContent=t).catch(e=>box.textContent='ERROR: '+e);
}
function placeTestnet(){
  const box=document.getElementById('answer');
  const sym=document.getElementById('sym').value;
  const side=prompt('ด้านไหน? (BUY=long / SELL=short)','BUY');
  if(!side) return;
  const qty=prompt('จำนวน (เช่น 0.001 BTC)','0.001');
  if(!qty) return;
  const u='/place_testnet?sym='+encodeURIComponent(sym)+'&side='+side+'&qty='+qty;
  box.textContent='⏳ วางออเดอร์จำลอง (testnet)...';
  fetch(u).then(r=>r.text()).then(t=>{
    if(t.includes('BINANCE_TESTNET')){
      box.textContent='🧪 ฟีเจอร์เสริม: ต้องตั้ง BINANCE_TESTNET_KEY + BINANCE_TESTNET_SECRET ก่อน (ดูคู่มือใต้ปุ่ม)\nเครื่องมือวางแผนหลักใช้ได้เลยไม่ต้องตั้ง';
    } else {
      box.textContent=t;
    }
  }).catch(e=>box.textContent='ERROR: '+e);
}
function openReport(){
  const sym=document.getElementById('sym').value;
  const tf=document.getElementById('tf').value;
  let u='/report?sym='+encodeURIComponent(sym)+'&tf='+tf;
  if(pts.entry&&pts.sl&&pts.tp){
    u+='&entry='+pts.entry+'&sl='+pts.sl+'&tp='+pts.tp;
    u+='&budget='+document.getElementById('budget').value+'&leverage='+document.getElementById('leverage').value;
  }
  window.open(u,'_blank');
  document.getElementById('answer').textContent='📄 เปิดรายงานแล้ว (กด Ctrl+S บันทึกเป็น HTML ส่งภรรยาดูได้)';
}
function openPdf(){
  const sym=document.getElementById('sym').value;
  const tf=document.getElementById('tf').value;
  let u='/pdf_report?sym='+encodeURIComponent(sym)+'&tf='+tf;
  if(pts.entry&&pts.sl&&pts.tp){
    u+='&entry='+pts.entry+'&sl='+pts.sl+'&tp='+pts.tp;
  }
  window.open(u,'_blank');
}
function autoPlan(){
  const sym=document.getElementById('sym').value;
  const tf=document.getElementById('tf').value;
  const sl=document.getElementById('budget')?'2':'2';
  const box=document.getElementById('answer');
  box.textContent='🤖 หาจุด Entry อัตโนมัติ...';
  fetch('/auto_plan?sym='+encodeURIComponent(sym)+'&tf='+tf+'&sl=2&tp=4')
    .then(r=>{
      const hdr=r.headers.get('X-Plan')||'';
      return r.blob().then(b=>({b,hdr}));
    })
    .then(({b,hdr})=>{
      const url=URL.createObjectURL(b);
      document.getElementById('chart').src=url;
      if(hdr){
        const p=Object.fromEntries(hdr.split('|').map(s=>s.split('=')));
        box.textContent=`🤖 Auto Plan (เสนอเท่านั้น คุณปรุงแต่งเอง):\nด้าน: ${p.side}\nEntry: ${p.entry}\nSL: ${p.sl}\nTP: ${p.tp}\nเหตุผล: ${p.reason}`;
        // โหลดค่าลง pts ให้กดคำนวณ R:R ต่อได้
        pts.entry=parseFloat(p.entry); pts.sl=parseFloat(p.sl); pts.tp=parseFloat(p.tp); updatePts();
      }
    })
    .catch(e=>box.textContent='ERROR: '+e);
}
function savePlan(){
  if(!pts.entry||!pts.sl||!pts.tp){alert('คลิกกำหนด Entry/SL/TP ครบ 3 จุดบนกราฟก่อน');return;}
  const sym=document.getElementById('sym').value;
  const tf=document.getElementById('tf').value;
  const u='/plan_chart?sym='+encodeURIComponent(sym)+'&tf='+tf+'&entry='+pts.entry+'&sl='+pts.sl+'&tp='+pts.tp;
  window.open(u,'_blank');
  document.getElementById('answer').textContent='💾 เปิดแผน PNG แล้ว (คลิกขวาเดี้ยว save)';
}
// โหลดกราฟแรกตอนเปิดหน้า
loadChart();
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(INDEX)


@app.route("/chart")
def chart():
    sym = request.args.get("sym", "BTCUSDT")
    tf = request.args.get("tf", "4h")
    multi = request.args.get("multi", "0") == "1"
    try:
        if multi:
            from indicators import run_multi_tf
            res = run_multi_tf(sym, ("1h", "4h", "1d"))
            path = res["charts"][0]
        else:
            from indicators import run
            res = run(sym, tf, 200, draw=True)
            path = res["chart"]["chart_path"]
        with open(path, "rb") as f:
            data = f.read()
        return Response(data, mimetype="image/png")
    except Exception as e:
        return Response(f"chart error: {e}", mimetype="text/plain")


@app.route("/ask")
def ask():
    q = request.args.get("q", "")
    vision = request.args.get("vision", "0") == "1"
    try:
        args = ["--vision", q, "smart"] if vision else [q, "smart"]
        out = subprocess.run(
            [sys.executable, os.path.join(SCRIPT_DIR, "agent.py"), *args],
            capture_output=True, text=True, timeout=400,
        )
        txt = (out.stdout.strip() or out.stderr.strip())
        # ตัดส่วน log "--- ขั้นตอนที่ agent ทำ ---" ทิ้ง เหลือแค่คำตอบ
        if "--- ขั้นตอนที่ agent ทำ" in txt:
            txt = txt.split("--- ขั้นตอนที่ agent ทำ")[0].strip()
        return Response(txt, mimetype="text/plain; charset=utf-8")
    except Exception as e:
        return Response(f"ask error: {e}", mimetype="text/plain")


@app.route("/chart_meta")
def chart_meta():
    """คืน bbox จริงของ pane ราคา (จาก matplotlib) เพื่อแปลง pixel->ราคา แม่นยำ"""
    sym = request.args.get("sym", "BTCUSDT")
    tf = request.args.get("tf", "4h")
    try:
        from indicators import analyze, price_pane_bbox
        df, out = analyze(sym, tf, 200)
        bbox = price_pane_bbox(out, df)
        if bbox is None:
            return {"error": "matplotlib ไม่พร้อม"}
        return bbox
    except Exception as e:
        return {"error": str(e)}


@app.route("/plan_chart")
def plan_chart():
    """วาดกราฟโอเวอร์เลย์เส้น Entry/SL/TP แล้วคืน PNG (บันทึกแผน)"""
    try:
        from indicators import analyze, draw_plan_chart
        sym = request.args.get("sym", "BTCUSDT")
        tf = request.args.get("tf", "4h")
        entry = float(request.args.get("entry"))
        sl = float(request.args.get("sl"))
        tp = float(request.args.get("tp"))
        df, out = analyze(sym, tf, 200)
        res = draw_plan_chart(df, out, entry, sl, tp)
        if "error" in res:
            return Response(res["error"], mimetype="text/plain")
        with open(res["chart_path"], "rb") as f:
            data = f.read()
        return Response(data, mimetype="image/png")
    except Exception as e:
        return Response(f"plan_chart error: {e}", mimetype="text/plain")


@app.route("/place_testnet")
def place_testnet():
    """วางออเดอร์จำลองบน Binance Futures TESTNET (ไม่ใช้เงินจริง)"""
    try:
        from futures_testnet import place_market
        sym = request.args.get("sym", "BTCUSDT")
        side = request.args.get("side", "BUY")
        qty = float(request.args.get("qty", 0.001))
        res = place_market(sym, side, qty)
        return Response(json.dumps(res, ensure_ascii=False, indent=2),
                        mimetype="text/plain; charset=utf-8")
    except Exception as e:
        return Response(f"testnet error: {e}\n(ต้องตั้ง env BINANCE_TESTNET_KEY + BINANCE_TESTNET_SECRET)",
                        mimetype="text/plain")


@app.route("/calc_plan")
def calc_plan():
    """รับ entry/sl/tp + budget/leverage -> คืนตาราง position (เรียก calc_position จริง)"""
    try:
        from tools import calc_position
        entry = float(request.args.get("entry"))
        sl = float(request.args.get("sl"))
        tp = float(request.args.get("tp"))
        budget = float(request.args.get("budget", 100))
        leverage = float(request.args.get("leverage", 5))
        res = calc_position(budget, leverage, entry, sl, tp)
        # จัดเป็นตารางข้อความ
        lines = [
            f"💰 งบ {budget} USDT | Lev {leverage}x | Notional {res.get('position_notional')} USDT",
            f"📍 Entry: {entry}",
            f"🛑 SL: {sl}  |  🎯 TP: {tp}",
            f"⚖️ R:R = {res.get('R_R')}  |  Liquidation: {res.get('liquidation_price')}",
            f"📈 ถ้า TP: +{res.get('pnl_if_tp')} USDT  |  📉 ถ้า SL: {res.get('pnl_if_sl')} USDT",
        ]
        return Response("\n".join(lines), mimetype="text/plain; charset=utf-8")
    except Exception as e:
        return Response(f"calc error: {e}", mimetype="text/plain")


@app.route("/report")
def report():
    """สร้างรายงาน HTML standalone (กราฟฝัง base64 + วิเคราะห์) สำหรับโชว์/ส่งต่อ"""
    try:
        from indicators import analyze, run, draw_plan_chart
        import base64, datetime
        sym = request.args.get("sym", "BTCUSDT").upper()
        tf = request.args.get("tf", "4h")
        entry = request.args.get("entry")
        sl = request.args.get("sl")
        tp = request.args.get("tp")
        budget = request.args.get("budget", "100")
        leverage = request.args.get("leverage", "5")
        # ดึงกราฟหลัก
        df, out = analyze(sym, tf, 200)
        chart_res = run(sym, tf, 200, draw=True)
        chart_path = chart_res["chart"]["chart_path"]
        with open(chart_path, "rb") as f:
            chart_b64 = base64.b64encode(f.read()).decode()
        # ถ้ามีแผน -> วาดแผนด้วย
        plan_b64 = None
        if entry and sl and tp:
            pr = draw_plan_chart(df, out, float(entry), float(sl), float(tp))
            if "chart_path" in pr:
                with open(pr["chart_path"], "rb") as f:
                    plan_b64 = base64.b64encode(f.read()).decode()
        # อ่านตัวเลขอินดิเคเตอร์
        st = out["supertrend"]["trend"]
        macd = out["macd"]["cross"]
        rsi = out["rsi"]["value"]
        rsi_sig = out["rsi"]["signal"]
        tema = out["tema"]["trend"]
        vwap = out["vwap"]["trend"]
        sr = out.get("sr", {})
        fib = out.get("fib", {})
        signals = out.get("signals", [])
        sig_txt = ", ".join(f"{s['type']}" for s in signals[-8:]) or "-"
        # สรุปแนวโน้ม (ตามทฤษฎีเทรดเดอร์)
        trend_score = 0
        if st == "UP": trend_score += 1
        if macd == "bullish": trend_score += 1
        if tema == "UP": trend_score += 1
        if rsi_sig == "neutral": trend_score += 1
        elif rsi_sig == "oversold": trend_score += 2
        verdict = "🟢 ภาพรวมบวก (Bullish bias)" if trend_score >= 3 else ("🔴 ภาพรวมลบ (Bearish bias)" if trend_score <= 1 else "🟡 ผสม (Sideways/ไม่ชัด)")
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        plan_block = ""
        if plan_b64:
            plan_block = f"""
            <h2>📐 แผนเทรด (Plan)</h2>
            <img src="data:image/png;base64,{plan_b64}" style="width:100%;border:1px solid #30363d;border-radius:8px">
            <p>Entry {entry} | SL {sl} | TP {tp} | งบ {budget} USDT | Lev {leverage}x</p>
            """
        html = f"""<!doctype html><html lang="th"><head><meta charset="utf-8">
<title>รายงานวิเคราะห์ {sym} {tf}</title>
<style>body{{font-family:'Segoe UI',sans-serif;background:#0d1117;color:#e6edf3;max-width:900px;margin:20px auto;padding:0 16px}}
h1{{color:#58a6ff}} h2{{color:#7ee787;border-bottom:1px solid #30363d;padding-bottom:6px}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:16px;margin:14px 0}}
.kpi{{display:flex;flex-wrap:wrap;gap:10px}} .kpi div{{background:#21262d;padding:8px 12px;border-radius:6px;font-size:13px}}
.ok{{color:#7ee787}} .bad{{color:#ff7b72}} .warn{{color:#d2a8ff}}
img{{width:100%;border:1px solid #30363d;border-radius:8px;background:#fff}}
.foot{{color:#8b949e;font-size:12px;margin-top:30px;text-align:center}}
</style></head><body>
<h1>📊 รายงานวิเคราะห์เทคนิค {sym} — {tf}</h1>
<p class="foot">สร้างโดย Local Crypto Agent (Ollama + Binance, ฟรี 100% local) | {now}</p>
<div class="card"><div class="kpi">
  <div>SuperTrend: <b class="{ 'ok' if st=='UP' else 'bad' }">{st}</b></div>
  <div>MACD: <b class="{ 'ok' if macd=='bullish' else 'bad' }">{macd}</b></div>
  <div>RSI: <b>{rsi} ({rsi_sig})</b></div>
  <div>TEMA: <b class="{ 'ok' if tema=='UP' else 'bad' }">{tema}</b></div>
  <div>VWAP: <b class="{ 'ok' if vwap=='UP' else 'bad' }">{vwap}</b></div>
  <div>ราคาปัจจุบัน: <b>{out['last_close']}</b></div>
</div></div>
<h2>📈 กราฟเทคนิค</h2>
<img src="data:image/png;base64,{chart_b64}">
<div class="card"><b>สัญญาณล่าสุด:</b> {sig_txt}<br>
<b>Support:</b> {', '.join(str(x) for x in sr.get('support',[])) or '-'} |
<b>Resistance:</b> {', '.join(str(x) for x in sr.get('resistance',[])) or '-'}<br>
<b>Fibo 61.8%:</b> {fib.get('levels',{}).get('61.8%','-')} | <b>78.6%:</b> {fib.get('levels',{}).get('78.6%','-')}
</div>
{plan_block}
<div class="card"><h3>🎯 สรุปแนวโน้ม (ตามหลัก TA)</h3>
<p style="font-size:16px">{verdict}</p>
<p>คะแนนภาพรวม: {trend_score}/5 (นับจาก SuperTrend/MACD/TEMA/RSI/VWAP ตามทิศทางเดียวกัน)</p>
<p class="warn">⚠️ นี้คือเครื่องมือช่วยวางแผน ไม่ใช่คำแนะนำลงทุน ผู้เทรดตัดสินใจเองทั้งหมด</p>
</div>
<p class="foot">Local Crypto Agent — เครื่องมือผู้ช่วยวางแผนการตัดสินใจเทรดคริปโต<br>
รันบนเครื่องคุณเอง 100% ฟรี ไม่ส่งข้อมูลออกภายนอก</p>
</body></html>"""
        return Response(html, mimetype="text/html; charset=utf-8")
    except Exception as e:
        return Response(f"report error: {e}", mimetype="text/plain")


@app.route("/auto_plan")
def auto_plan():
    """หาจุด Entry อัตโนมัติจาก S/R+Fib แล้ววาดแผน PNG ให้"""
    try:
        from indicators import auto_plan as ap, analyze, draw_plan_chart
        sym = request.args.get("sym", "BTCUSDT")
        tf = request.args.get("tf", "4h")
        sl = float(request.args.get("sl", 2))
        tp = float(request.args.get("tp", 4))
        plan = ap(sym, tf, 200, sl, tp)
        df, out = analyze(sym, tf, 200)
        pr = draw_plan_chart(df, out, plan["entry"], plan["sl"], plan["tp"])
        if "error" in pr:
            return Response(pr["error"], mimetype="text/plain")
        with open(pr["chart_path"], "rb") as f:
            data = f.read()
        # ส่งข้อมูล plan ไปด้วยทาง header (ให้ JS อ่าน)
        hdr = f"side={plan['side']}|entry={plan['entry']}|sl={plan['sl']}|tp={plan['tp']}|reason={plan['reason']}"
        return Response(data, mimetype="image/png", headers={"X-Plan": hdr})
    except Exception as e:
        return Response(f"auto_plan error: {e}", mimetype="text/plain")


@app.route("/pdf_report")
def pdf_report():
    """สร้างรายงาน PDF (ถ้ามี reportlab) หรือ fallback HTML ให้พิมพ์เป็น PDF"""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Image, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib import colors
        import io, base64, datetime
        from indicators import analyze, run, draw_plan_chart
        sym = request.args.get("sym", "BTCUSDT").upper()
        tf = request.args.get("tf", "4h")
        entry = request.args.get("entry"); sl = request.args.get("sl"); tp = request.args.get("tp")
        df, out = analyze(sym, tf, 200)
        chart_res = run(sym, tf, 200, draw=True)
        img_path = chart_res["chart"]["chart_path"]
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4)
        ss = getSampleStyleSheet()
        story = [Paragraph(f"รายงานวิเคราะห์ {sym} {tf}", ss["Title"]),
                 Paragraph(f"สร้างโดย Local Crypto Agent | {datetime.datetime.now():%Y-%m-%d %H:%M}", ss["Normal"]),
                 Spacer(1, 10), Image(img_path, width=480, height=330)]
        if entry and sl and tp:
            pr = draw_plan_chart(df, out, float(entry), float(sl), float(tp))
            if "chart_path" in pr:
                story.append(Spacer(1, 10)); story.append(Image(pr["chart_path"], width=480, height=330))
        story.append(Spacer(1, 10))
        story.append(Paragraph(f"SuperTrend: {out['supertrend']['trend']} | MACD: {out['macd']['cross']} | "
                               f"RSI: {out['rsi']['value']} | TEMA: {out['tema']['trend']}", ss["Normal"]))
        story.append(Paragraph("⚠️ เครื่องมือช่วยวางแผน ไม่ใช่คำแนะนำลงทุน", ss["Normal"]))
        doc.build(story)
        buf.seek(0)
        return Response(buf.read(), mimetype="application/pdf",
                        headers={"Content-Disposition": f"attachment; filename=report_{sym}_{tf}.pdf"})
    except ImportError:
        # fallback: ส่ง HTML ให้ผู้ใช้พิมพ์เป็น PDF
        return report()
    except Exception as e:
        return Response(f"pdf error: {e}", mimetype="text/plain")


if __name__ == "__main__":
    port = int(os.environ.get("WEBUI_PORT", "5566"))
    print(f"เปิด browser: http://localhost:{port}")
    app.run(host="127.0.0.1", port=port, debug=False)
