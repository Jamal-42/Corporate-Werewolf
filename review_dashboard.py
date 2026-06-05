# -*- coding: utf-8 -*-
"""评测+复盘前端：查看多维评分、关键失误、反事实推演和 Leaderboard。"""

from __future__ import annotations

import argparse
import json
import logging
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_log = logging.getLogger("werewolf.diag.webui")
from typing import Any
from urllib.parse import parse_qs, urlparse

from evaluation_cn import PROJECT_ROOT, demo_bad_case_log, evaluate_log
from shared.parsing_utils import discover_log_files


def resolve_log(file_id: str | None) -> Path:
    candidates = {item["id"]: PROJECT_ROOT / item["id"] for item in discover_log_files(PROJECT_ROOT, [PROJECT_ROOT / "exports"])}
    if file_id and file_id in candidates:
        return candidates[file_id]
    default = PROJECT_ROOT / "game_log.txt"
    if default.exists():
        return default
    if candidates:
        return next(iter(candidates.values()))
    raise FileNotFoundError("未找到可用日志")


INDEX_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>狼人杀 Agent 评测复盘台</title>
  <style>
    :root{--ink:#261a12;--muted:#7a6859;--paper:#fff8e9;--red:#b4233a;--green:#13795b;--gold:#d99a2b;--blue:#285a84;--line:rgba(84,60,38,.14)}
    *{box-sizing:border-box} body{margin:0;min-height:100vh;color:var(--ink);font-family:"LXGW WenKai","Microsoft YaHei","STKaiti",Georgia,serif;background:radial-gradient(circle at 12% 8%,#ffe3a3 0 18%,transparent 32%),radial-gradient(circle at 88% 12%,#c4e7d4 0 16%,transparent 30%),linear-gradient(135deg,#f8ecd4,#f5e1bc 46%,#efe9d8)}
    .page{width:min(1220px,calc(100% - 28px));margin:0 auto;padding:28px 0 44px}.hero{display:grid;grid-template-columns:minmax(0,1fr) 360px;gap:18px}.panel{background:rgba(255,253,247,.9);border:1px solid var(--line);border-radius:28px;box-shadow:0 22px 70px rgba(86,55,25,.14);backdrop-filter:blur(10px)}
    .title{padding:28px}.eyebrow{display:inline-flex;padding:7px 12px;border-radius:999px;background:#2b221b;color:#ffe8bf;font-size:13px;letter-spacing:.08em}.title h1{margin:18px 0 10px;font-size:clamp(34px,6vw,68px);line-height:.95}.title p{margin:0;color:var(--muted);font-size:18px;line-height:1.7}.controls{padding:22px;display:flex;flex-direction:column;gap:14px}.controls label{font-weight:800}.row{display:flex;gap:10px}.select,.btn{border:1px solid var(--line);border-radius:16px;padding:12px 14px;font:inherit}.select{width:100%;background:#fffdf8}.btn{cursor:pointer;background:#2b221b;color:#fff3dc;font-weight:900}.btn.alt{background:#fffdf8;color:#2b221b}
    .grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-top:16px}.metric{padding:18px}.metric small{color:var(--muted);display:block}.metric strong{font-size:34px;display:block;margin-top:6px}.metric.speech strong{color:var(--blue)}.metric.vote strong{color:var(--gold)}.metric.skill strong{color:var(--green)}.main{display:grid;grid-template-columns:1.1fr .9fr;gap:16px;margin-top:16px}.section{padding:22px}.section h2{margin:0 0 14px;font-size:24px}
    .leader{display:flex;flex-direction:column;gap:10px}.leader-row{display:grid;grid-template-columns:34px 1fr 86px;gap:12px;align-items:center;padding:12px;border:1px solid var(--line);border-radius:18px;background:#fffaf0}.rank{width:34px;height:34px;border-radius:50%;display:grid;place-items:center;background:#2b221b;color:#ffe8bf;font-weight:900}.bar{height:10px;border-radius:99px;background:#efe2c7;overflow:hidden;margin-top:8px}.bar span{display:block;height:100%;background:linear-gradient(90deg,var(--green),var(--gold));border-radius:inherit}.score{text-align:right;font-size:22px;font-weight:900}.muted{color:var(--muted)}
    .finding{padding:14px;border-radius:18px;border:1px solid var(--line);background:#fffaf0;margin-bottom:10px}.finding.high{border-color:rgba(180,35,58,.35);background:#fff1f1}.finding.medium{border-color:rgba(217,154,43,.35);background:#fff8e8}.tag{display:inline-block;border-radius:999px;padding:4px 9px;font-size:12px;font-weight:900;background:#2b221b;color:#ffe8bf;margin-right:8px}.tag.high{background:var(--red)}.tag.medium{background:var(--gold);color:#2b221b}.tag.low{background:var(--blue)}.finding h3{margin:8px 0 6px;font-size:18px}.finding p{margin:6px 0;color:#4d3a2d;line-height:1.65}.cf{border-left:4px solid var(--green);padding-left:10px}.events{max-height:520px;overflow:auto}.event{display:grid;grid-template-columns:80px 1fr 58px;gap:10px;padding:10px;border-bottom:1px solid var(--line)}.event b{color:var(--blue)}
    .loading{opacity:.62;pointer-events:none}@media(max-width:900px){.hero,.main{grid-template-columns:1fr}.grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:560px){.row{flex-direction:column}.grid{grid-template-columns:1fr}.event{grid-template-columns:1fr}.title,.section,.controls{padding:18px}}
  </style>
</head>
<body>
<div class="page">
  <div class="hero">
    <section class="panel title"><span class="eyebrow">评测 + 复盘 · B 方向</span><h1>Agent 决策质量审计台</h1><p>多维评测发言、投票、技能，不只看胜负；自动定位 bad case，给出关键决策复盘、反事实推演与 Leaderboard。</p></section>
    <section class="panel controls"><label>选择对局日志</label><select id="file" class="select"></select><div class="row"><button id="eval" class="btn">评测当前日志</button><button id="demo" class="btn alt">明显失误样例</button></div><div class="muted" id="source">等待加载...</div></section>
  </div>
  <div class="grid">
    <div class="panel metric"><small>综合得分</small><strong id="overall">--</strong></div>
    <div class="panel metric speech"><small>发言评分</small><strong id="speech">--</strong></div>
    <div class="panel metric vote"><small>投票评分</small><strong id="vote">--</strong></div>
    <div class="panel metric skill"><small>技能评分</small><strong id="skill">--</strong></div>
  </div>
  <div class="main">
    <section class="panel section"><h2>Leaderboard</h2><div id="leader" class="leader"></div></section>
    <section class="panel section"><h2>关键失误复盘</h2><div id="findings"></div></section>
    <section class="panel section"><h2>反事实推演</h2><div id="counterfactuals"></div></section>
    <section class="panel section"><h2>结构化决策流</h2><div id="events" class="events"></div></section>
  </div>
</div>
<script>
const $=id=>document.getElementById(id);
function fmt(v){return (v===undefined||v===null||Number.isNaN(v))?'--':Number(v).toFixed(1)}
async function loadFiles(){const res=await fetch('/api/files');const data=await res.json();$('file').innerHTML='';for(const f of data.files){const o=document.createElement('option');o.value=f.id;o.textContent=f.name;$('file').appendChild(o)}if(data.files.length) await evaluate(false)}
async function evaluate(demo){document.body.classList.add('loading');try{const q=demo?'?demo=1':'?file='+encodeURIComponent($('file').value);const res=await fetch('/api/evaluate'+q);const report=await res.json();render(report)}finally{document.body.classList.remove('loading')}}
function render(r){$('source').textContent='来源：'+r.source_file+' · 决策 '+r.summary.decision_count+' · 高危 '+r.summary.high_severity_mistakes;$('overall').textContent=fmt(r.summary.overall_score);$('speech').textContent=fmt(r.dimension_scores.speech);$('vote').textContent=fmt(r.dimension_scores.vote);$('skill').textContent=fmt(r.dimension_scores.skill);renderLeader(r.leaderboard||[]);renderFindings(r.findings||[]);renderCounter(r.counterfactuals||[]);renderEvents(r.events||[])}
function renderLeader(rows){$('leader').innerHTML=rows.map((x,i)=>`<div class="leader-row"><div class="rank">${i+1}</div><div><b>${x.player}</b> <span class="muted">${x.role} · ${x.agent_version}</span><div class="bar"><span style="width:${Math.max(2,x.overall_score)}%"></span></div><small class="muted">发言 ${fmt(x.speech_score)} / 投票 ${fmt(x.vote_score)} / 技能 ${fmt(x.skill_score)} / 高危 ${x.critical_mistakes}</small></div><div class="score">${fmt(x.overall_score)}</div></div>`).join('')||'<p class="muted">暂无数据</p>'}
function renderFindings(rows){$('findings').innerHTML=rows.slice(0,10).map(x=>`<div class="finding ${x.severity}"><span class="tag ${x.severity}">${x.severity}</span><span class="muted">第 ${x.round||'-'} 轮 · ${x.player} · ${x.role}</span><h3>${x.title}</h3><p>${x.evidence}</p><p><b>建议：</b>${x.recommendation}</p></div>`).join('')||'<p class="muted">未发现明显失误，可增加更多结构化日志提升覆盖率。</p>'}
function renderCounter(rows){$('counterfactuals').innerHTML=rows.slice(0,8).map(x=>`<div class="finding"><p class="cf">${x}</p></div>`).join('')||'<p class="muted">暂无反事实推演</p>'}
function renderEvents(rows){$('events').innerHTML=rows.slice(0,120).map(x=>`<div class="event"><span class="muted">${x.category}<br>第${x.round||'-'}轮</span><div><b>${x.player}</b> ${x.action}${x.target?' → '+x.target:''}<br><span class="muted">${(x.reason||x.raw||'').slice(0,110)}</span></div><strong>${fmt(x.score)}</strong></div>`).join('')||'<p class="muted">暂无结构化事件</p>'}
$('eval').onclick=()=>evaluate(false);$('demo').onclick=()=>evaluate(true);loadFiles();
</script>
</body>
</html>"""


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "WerewolfReviewDashboard/1.0"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            self._send_html(INDEX_HTML)
            return
        if parsed.path == "/api/files":
            self._send_json({"files": discover_log_files(PROJECT_ROOT, [PROJECT_ROOT / "exports"])})
            return
        if parsed.path == "/api/evaluate":
            query = parse_qs(parsed.query)
            try:
                if query.get("demo", [""])[0] == "1":
                    report = evaluate_log(text=demo_bad_case_log())
                else:
                    report = evaluate_log(path=resolve_log(query.get("file", [None])[0]))
                self._send_json(report)
            except Exception as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="启动狼人杀 Agent 评测复盘前端")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7007)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    _log.info(f"Review dashboard running on http://{server.server_address[0]}:{server.server_address[1]}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        _log.info("Shutting down review dashboard...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
