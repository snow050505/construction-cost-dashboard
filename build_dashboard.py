#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
營造成本原物料情報板 — 靜態產生器
邏輯完全對應原本 n8n 的「建立 FRED 查詢」+「抓 FRED API」+「解析 + 渲染 HTML」三個節點。
由 GitHub Actions 定期執行，產出 index.html，交給 GitHub Pages 顯示。
"""

import os
import sys
import json
import datetime
import requests

API_KEY = os.environ.get("FRED_API_KEY", "")
if not API_KEY:
    print("錯誤：找不到環境變數 FRED_API_KEY，請確認 GitHub Secrets 已設定。", file=sys.stderr)
    sys.exit(1)

META = {
    "WPU101":      {"ticker": "WPU101 · STEEL",    "name": "鋼鐵",       "unit": "指數 1982=100", "kind": "index"},
    "PCOPPUSDM":   {"ticker": "CU · COPPER",       "name": "銅",         "unit": "USD / 噸",      "kind": "usd"},
    "PALUMUSDM":   {"ticker": "AL · ALUMINIUM",    "name": "鋁",         "unit": "USD / 噸",      "kind": "usd"},
    "WPU1322":     {"ticker": "CEM · CEMENT",      "name": "水泥",       "unit": "指數 1982=100", "kind": "index"},
    "WPU081":      {"ticker": "LBR · LUMBER",      "name": "木材",       "unit": "指數 1982=100", "kind": "index"},
    "WPU1333":     {"ticker": "RMC · READY-MIX",   "name": "預拌混凝土", "unit": "指數 1982=100", "kind": "index"},
    "WPU1321":     {"ticker": "AGG · SAND/GRAVEL", "name": "砂石・碎石", "unit": "指數 1982=100", "kind": "index"},
    "WPU05810212": {"ticker": "ASP · ASPHALT",     "name": "瀝青",       "unit": "指數 1985=100", "kind": "index"},
    "PIORECRUSDM": {"ticker": "IRON · IRON ORE",   "name": "鐵礦砂",     "unit": "USD / 噸",      "kind": "usd"},
    "PZINCUSDM":   {"ticker": "ZN · ZINC",         "name": "鋅",         "unit": "USD / 噸",      "kind": "usd"},
}
ORDER = ["WPU101", "PCOPPUSDM", "PALUMUSDM", "WPU1322", "WPU081",
         "WPU1333", "WPU1321", "WPU05810212", "PIORECRUSDM", "PZINCUSDM"]
SERIES = ORDER + ["DEXTAUS"]

DRIVERS = {
    "WPU101": "廢鋼與能源成本、中國產能與出口政策、各國關稅與 CBAM、營建/基建季節性需求。",
    "PCOPPUSDM": "礦山供給（罷工/品位下滑）、AI 資料中心與電氣化需求、美國 50% 關稅、美元走勢。",
    "PALUMUSDM": "冶煉電力成本、中國產能上限、地緣供給中斷（波斯灣/荷莫茲）、運輸。",
    "WPU1322": "屬地性高（重、運費敏感）、燃料/電力成本、營建需求、碳費與環保限產。",
    "WPU081": "北美林木供給與關稅、房市/營建需求、運輸成本、天候與林災。",
    "WPU1333": "水泥＋砂石＋運輸的綜合成本、在地營建需求、人力與運距。",
    "WPU1321": "開採許可與環保、運距/運費（重貨）、在地營建需求。",
    "WPU05810212": "原油/石油價格（瀝青為煉油副產品）、煉油廠產出、夏季鋪路旺季需求、道路工程與公共建設預算。",
    "PIORECRUSDM": "中國鋼鐵需求（最大買家）、澳洲/巴西礦商供給、海運運費。",
    "PZINCUSDM": "鍍鋅鋼（營建）需求、礦山與冶煉供給、能源/電力成本。",
}

# --- 手動維護區：FRED 沒有的資料，需人工更新（對應原本節點裡的 MANUAL / DRIVERS） ---
MANUAL_HTML = '''<div class="manual-grid">
<div class="mcard"><div class="mt"><span class="mname">台灣碳費（水泥/鋼筋/玻璃）</span><span class="mval">▲ +12~13%</span></div><p class="mnote">2025 碳費上路的結構性成本，每坪約 +NT$2–4 萬。主要因素：碳定價政策、高碳建材轉嫁。台灣本地資料，FRED 無。</p></div>
<div class="mcard"><div class="mt"><span class="mname">美國 COMEX 銅即時價</span><span class="mval">$6.31 / 磅 ≈ $13,911 / 噸</span></div><p class="mnote">美國 COMEX 現貨即時價（≈ NT$439,592/噸）。通常比上方全球月均價高 5–10%，差額為美國關稅溢價。供「全球月均 ↔ 美國即時」對照；手動維護、非自動更新（更新時改每磅價即可）。</p></div>
<div class="mcard"><div class="mt"><span class="mname">PVC・塑膠管材</span><span class="mval">▲ 每月調漲 1–2 次</span></div><p class="mnote">主要因素：乙烯/原油原料成本、資料中心等需求、產能與交期。無公開單一報價，以調漲頻率為訊號。</p></div>
<div class="mcard"><div class="mt"><span class="mname">海運運費・能源</span><span class="mval">▲ 上行</span></div><p class="mnote">主要因素：地緣衝突（荷莫茲海峽）、油價、艙位供需。推升燃料、保險與到岸建材成本。</p></div></div>'''

CSS = r"""
:root{--paper:#FBFAF7;--ink:#14171A;--muted:#6B7177;--line:#E4E1D9;--up:#B23B0E;--up-bg:#FBEDE6;--down:#0F766E;--down-bg:#E5F1EF;--flat:#5A6066;--flat-bg:#EDECE6;--card:#FFFFFF;}
*{box-sizing:border-box;}body{margin:0;background:var(--paper);color:var(--ink);font-family:"Noto Sans TC","Space Grotesk",system-ui,sans-serif;line-height:1.6;}
.wrap{max-width:1080px;margin:0 auto;padding:32px 22px 64px;}
header{border-bottom:2px solid var(--ink);padding-bottom:16px;margin-bottom:22px;}
.eyebrow{font-family:"IBM Plex Mono",monospace;font-size:12px;letter-spacing:.22em;text-transform:uppercase;color:var(--muted);display:flex;gap:12px;align-items:center;flex-wrap:wrap;}
.eyebrow .dot{width:6px;height:6px;background:var(--up);border-radius:50%;}
h1{font-family:"Space Grotesk","Noto Sans TC",sans-serif;font-weight:700;font-size:clamp(26px,5vw,40px);line-height:1.1;margin:12px 0 6px;letter-spacing:-.01em;}
.sub{color:var(--muted);font-size:14px;}
.source{font-family:"IBM Plex Mono",monospace;font-size:11px;color:#8A9097;margin-top:7px;letter-spacing:.02em;line-height:1.55;}
.section-label{font-family:"IBM Plex Mono",monospace;font-size:12px;letter-spacing:.2em;text-transform:uppercase;color:var(--muted);margin:6px 0 14px;display:flex;align-items:center;gap:10px;}
.section-label::after{content:"";flex:1;height:1px;background:var(--line);}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:30px;}
.card{background:var(--card);border:1px solid var(--line);border-radius:5px;padding:16px 17px;display:flex;flex-direction:column;gap:9px;}
.card.up{border-top:3px solid var(--up);}.card.down{border-top:3px solid var(--down);}.card.flat{border-top:3px solid var(--flat);}
.card.pending{opacity:.6;border-style:dashed;}
.ct{display:flex;justify-content:space-between;align-items:flex-start;gap:8px;}
.ticker{font-family:"IBM Plex Mono",monospace;font-size:11px;letter-spacing:.1em;color:var(--muted);}
.name{font-family:"Space Grotesk","Noto Sans TC",sans-serif;font-size:18px;font-weight:700;margin-top:1px;}
.badge{font-family:"IBM Plex Mono",monospace;font-size:16px;font-weight:700;}
.badge.up{color:var(--up);}.badge.down{color:var(--down);}.badge.flat{color:var(--flat);}
.val{display:flex;align-items:baseline;gap:8px;}
.big{font-family:"IBM Plex Mono",monospace;font-size:28px;font-weight:700;}
.big.up{color:var(--up);}.big.down{color:var(--down);}.big.flat{color:var(--ink);}
.u{font-family:"IBM Plex Mono",monospace;font-size:11.5px;color:var(--muted);}
.twd{font-family:"IBM Plex Mono",monospace;font-size:13px;color:#44494E;margin-top:-2px;}
.twd .rate{color:#A8ADB2;font-size:11px;margin-left:4px;}
.chgs{display:flex;gap:8px;font-family:"IBM Plex Mono",monospace;font-size:12.5px;font-weight:600;}
.chgs span{padding:3px 7px;border-radius:3px;}
.mom.up,.yoy.up{background:var(--up-bg);color:var(--up);}.mom.down,.yoy.down{background:var(--down-bg);color:var(--down);}.mom.flat,.yoy.flat{background:var(--flat-bg);color:var(--flat);}
.spark{width:100%;height:auto;display:block;margin-top:4px;}
.spark .axis{stroke:#D6D2C8;stroke-width:1.2;}
.spark .yl,.spark .xl{font-family:"IBM Plex Mono",monospace;font-size:18px;fill:#6B7177;font-weight:500;}
.factors{border-top:1px dashed var(--line);padding-top:9px;}
.flabel{font-family:"IBM Plex Mono",monospace;font-size:10px;letter-spacing:.12em;color:var(--muted);display:block;margin-bottom:3px;}
.ftext{font-size:12.5px;color:#3C4147;line-height:1.55;}
.cap{font-family:"IBM Plex Mono",monospace;font-size:10px;color:#A8ADB2;margin-top:6px;}
.manual-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:14px;}
.mcard{background:#F6F4EF;border:1px solid var(--line);border-radius:5px;padding:15px 17px;}
.mcard .mt{display:flex;justify-content:space-between;align-items:baseline;gap:8px;}
.mname{font-family:"Space Grotesk","Noto Sans TC",sans-serif;font-size:16px;font-weight:700;}
.mval{font-family:"IBM Plex Mono",monospace;font-size:14px;font-weight:600;color:var(--up);}
.mnote{font-size:13px;color:#33383D;margin:6px 0 0;line-height:1.55;}
.manual-flag{font-family:"IBM Plex Mono",monospace;font-size:10.5px;color:var(--muted);border:1px solid var(--line);border-radius:99px;padding:2px 8px;display:inline-block;margin-bottom:12px;}
footer{margin-top:30px;padding-top:18px;border-top:1px solid var(--line);color:var(--muted);font-size:12.5px;line-height:1.7;}
footer b{color:var(--ink);}
@media(max-width:820px){.grid{grid-template-columns:repeat(2,1fr);}}
@media(max-width:560px){.grid,.manual-grid{grid-template-columns:1fr;}}
"""


def fetch_series(series_id: str, start_date: str) -> dict:
    """對應原本「抓 FRED API」節點：單項失敗不中斷。"""
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": API_KEY,
        "file_type": "json",
        "observation_start": start_date,
    }
    try:
        resp = requests.get(url, params=params, timeout=20)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"警告：抓取 {series_id} 失敗（{e}），此項將顯示「資料未到」。", file=sys.stderr)
        return {}


def pct(p: float) -> str:
    return f"{'+' if p >= 0 else ''}{p:.1f}%"


def cls(p: float) -> str:
    return "up" if p > 0.5 else ("down" if p < -0.5 else "flat")


def arrow(d: str) -> str:
    return {"up": "▲", "down": "▼"}.get(d, "●")


def fmt_ym(d: str) -> str:
    y, m = d.split("-")[:2]
    return f"{y}/{int(m)}"


def fmt_axis(v: float, kind: str) -> str:
    return f"{round(v):,}" if kind == "usd" else f"{v:.0f}"


def build_chart(vals, color, kind, x0label, xlabel) -> str:
    w, h, pl, pr, pt, pb = 480, 165, 76, 16, 18, 34
    n = len(vals)
    if n == 0:
        return ""
    vmin, vmax = min(vals), max(vals)
    mean = sum(vals) / n
    mid = (vmin + vmax) / 2
    half_real = (vmax - vmin) / 2
    half_eff = max(half_real, mean * 0.02)
    lo, hi = mid - half_eff, mid + half_eff
    span = (hi - lo) or 1
    iw, ih = w - pl - pr, h - pt - pb

    def X(i):
        return pl + (iw * (i / (n - 1)) if n > 1 else iw / 2)

    def Y(v):
        return pt + ih * (1 - (v - lo) / span)

    r1 = lambda x: round(x * 10) / 10
    pts = [(r1(X(i)), r1(Y(v))) for i, v in enumerate(vals)]
    line = " ".join(f"{x},{y}" for x, y in pts)
    area = f"{r1(pl)},{r1(pt + ih)} {line} {r1(X(n - 1))},{r1(pt + ih)}"
    last = pts[-1]
    return (
        f'<svg viewBox="0 0 {w} {h}" class="spark" xmlns="http://www.w3.org/2000/svg">'
        f'<line x1="{pl}" y1="{pt}" x2="{pl}" y2="{r1(pt + ih)}" class="axis"/>'
        f'<line x1="{pl}" y1="{r1(pt + ih)}" x2="{w - pr}" y2="{r1(pt + ih)}" class="axis"/>'
        f'<text x="{pl - 6}" y="{r1(Y(vmax)) + 6}" class="yl" text-anchor="end">{fmt_axis(vmax, kind)}</text>'
        f'<text x="{pl - 6}" y="{r1(Y(vmin)) + 6}" class="yl" text-anchor="end">{fmt_axis(vmin, kind)}</text>'
        f'<polyline points="{area}" fill="{color}22" stroke="none"/>'
        f'<polyline points="{line}" fill="none" stroke="{color}" stroke-width="3.5" stroke-linejoin="round" stroke-linecap="round"/>'
        f'<circle cx="{last[0]}" cy="{last[1]}" r="4.5" fill="{color}"/>'
        f'<text x="{r1(X(0))}" y="{h - 9}" class="xl" text-anchor="start">{x0label}</text>'
        f'<text x="{r1(X(n - 1))}" y="{h - 9}" class="xl" text-anchor="end">{xlabel}</text></svg>'
    )


def build_card(series_id: str, by_id: dict, rate: float) -> str:
    m = META[series_id]
    it = by_id.get(series_id)
    if not it or not it["rows"]:
        return (
            f'<div class="card pending"><div class="ct"><div><div class="ticker">{m["ticker"]}</div>'
            f'<div class="name">{m["name"]}</div></div><div class="badge flat">…</div></div>'
            f'<div class="val"><span class="big flat">—</span><span class="u">{m["unit"]}</span></div>'
            f'<div class="chgs"><span class="mom flat">資料未到</span></div>'
            f'<div class="factors"><span class="flabel">主要因素</span><span class="ftext">{DRIVERS.get(series_id, "")}</span></div>'
            f'<div class="cap">FRED {series_id}</div></div>'
        )

    rows = it["rows"]
    last, prev = rows[-1], (rows[-2] if len(rows) > 1 else None)
    latest = last["val"]
    mom = (latest / prev["val"] - 1) * 100 if prev else None

    if len(rows) >= 13:
        yoy = (latest / rows[0]["val"] - 1) * 100
        yoy_label = f"年 {pct(yoy)}"
    else:
        yoy = (latest / rows[0]["val"] - 1) * 100
        yoy_label = f"{len(rows) - 1}月 {pct(yoy)}"

    dir_ = cls(yoy)
    color = "#B23B0E" if dir_ == "up" else ("#0F766E" if dir_ == "down" else "#5A6066")
    big_val = f"${round(latest):,}" if m["kind"] == "usd" else f"{latest:.1f}"
    unit_txt = m["unit"] if m["kind"] == "usd" else f'{m["unit"]}（非貨幣價）'

    twd_html = ""
    if m["kind"] == "usd":
        t = round(latest * rate)
        twd_html = f'<div class="twd">≈ NT$ {t:,} / 噸<span class="rate">匯率 {rate:.1f}</span></div>'

    mom_html = f'<span class="mom {cls(mom)}">月 {pct(mom)}</span>' if mom is not None else ""

    return (
        f'<div class="card {dir_}"><div class="ct"><div><div class="ticker">{m["ticker"]}</div>'
        f'<div class="name">{m["name"]}</div></div><div class="badge {dir_}">{arrow(dir_)}</div></div>'
        f'<div class="val"><span class="big {dir_}">{big_val}</span><span class="u">{unit_txt}</span></div>'
        f'{twd_html}'
        f'<div class="chgs">{mom_html}<span class="yoy {cls(yoy)}">{yoy_label}</span></div>'
        f'{build_chart([r["val"] for r in rows], color, m["kind"], fmt_ym(rows[0]["date"]), fmt_ym(last["date"]))}'
        f'<div class="factors"><span class="flabel">主要因素</span><span class="ftext">{DRIVERS.get(series_id, "")}</span></div>'
        f'<div class="cap">FRED {series_id} · 截至 {last["date"][:7]} · {len(rows)} 個月</div></div>'
    )


def main():
    start_date = (datetime.date.today() - datetime.timedelta(days=396)).isoformat()

    by_id = {}
    for series_id in SERIES:
        data = fetch_series(series_id, start_date)
        obs = data.get("observations", [])
        rows = []
        for o in obs:
            v = o.get("value")
            if v in (".", "", None):
                continue
            try:
                num = float(v)
            except (TypeError, ValueError):
                continue
            rows.append({"date": o["date"], "val": num})
        if rows:
            by_id[series_id] = {"id": series_id, "rows": rows[-13:]}

    rate = 31.6
    if "DEXTAUS" in by_id and by_id["DEXTAUS"]["rows"]:
        rate = by_id["DEXTAUS"]["rows"][-1]["val"]

    cards = "".join(build_card(sid, by_id, rate) for sid in ORDER)
    today = datetime.date.today().isoformat()

    html = f"""<!DOCTYPE html><html lang="zh-Hant"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>營造成本原物料情報板</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600;700&family=Noto+Sans+TC:wght@400;500;700&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body><div class="wrap">
<header><div class="eyebrow"><span class="dot"></span> 原物料成本監測 · FRED 官方資料庫 · 月度自動更新</div>
<h1>營造成本原物料情報板</h1>
<div class="sub">資料拉取於 {today}　·　台幣換算匯率 US$1≈NT${rate:.1f}（FRED DEXTAUS）　·　每次更新即時重拉</div>
<div class="source">資料來源：FRED · 美國聖路易聯邦準備銀行官方資料庫（金屬價＝IMF 國際貨幣基金／建材＝美國勞工統計局 BLS／匯率＝美國聯準會）</div></header>
<div class="section-label">FRED 自動更新料別 · 10 項</div>
<div class="grid">{cards}</div>
<div class="section-label">手動維護 · FRED 無資料</div>
<span class="manual-flag">⚙ 此區不自動更新，需人工調整（見下方 MANUAL_HTML）</span>{MANUAL_HTML}
<footer><p><b>資料來源與權威性：</b>本看板數據全部取自 <b>FRED（Federal Reserve Economic Data）</b>，由美國<b>聖路易聯邦準備銀行</b>維運。金屬價（銅/鋁/鐵礦砂/鋅）來自 <b>IMF 國際貨幣基金</b>全球商品基準價、建材指數（鋼/水泥/木材/預拌混凝土/砂石/瀝青）來自<b>美國勞工統計局 BLS</b>生產者物價、匯率來自<b>美國聯準會</b>——皆為官方權威、公開可查的數據，非民間估算。</p>
<p style="margin-top:8px;"><b>關於數值與台幣換算：</b>銅、鋁、鐵礦砂、鋅為實際美元報價（USD/噸），已用 FRED 即時匯率換算台幣；鋼鐵、水泥、木材、預拌混凝土、砂石、瀝青為 BLS 生產者物價<b>指數</b>（非貨幣價），無台幣換算。價格大字以顏色標方向：橘＝上行（不利）、藍綠＝下行（有利）、灰＝持平。圖表為過去約一年實際月度走勢（含座標），不含未來推估。各料別單位與基期不同，請以方向與漲跌幅判讀，不構成採購或投資建議。</p></footer>
</div></body></html>"""

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("index.html 產生完成。")


if __name__ == "__main__":
    main()
