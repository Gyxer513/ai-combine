"""Дашборд оркестратора: один экран статуса (тот же сервис, отдельный роут).

* `GET /api/dashboard` — JSON-агрегат: здоровье сервисов, агенты + счётчики
  использования, размеры RAG-коллекций, активные разговоры.
* `GET /dashboard` — самодостаточная HTML-страница (inline, без статики и внешних
  зависимостей), которая опрашивает `/api/dashboard` и авто-обновляется.

Живёт на порту оркестратора (8000) — отдельная страница, не отдельный сервис.
"""

from __future__ import annotations

import asyncio

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ..agents.base import shared_store, shared_vstore
from ..agents.registry import REGISTRY
from ..config import settings
from ..metrics import shared_metrics

router = APIRouter()

# namespace RAG по агентам (см. register_rag_tool в модулях агентов).
_RAG_NAMESPACES = {"kolobok": "personal", "koschei": "security", "levsha": "coding"}


async def _probe(http: httpx.AsyncClient, url: str, *, headers: dict | None = None) -> bool:
    """True, если сервис ответил (любой статус < 500)."""
    try:
        resp = await http.get(url, headers=headers, timeout=5)
        return resp.status_code < 500
    except (httpx.HTTPError, OSError):
        return False


async def _services(http: httpx.AsyncClient) -> list[dict]:
    """Здоровье зависимостей (опрашиваются параллельно)."""
    litellm = settings.litellm_base_url.rstrip("/")
    checks = {
        "LiteLLM": _probe(
            http,
            f"{litellm}/models",
            headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
        ),
        "Qdrant": _probe(http, f"{settings.qdrant_url.rstrip('/')}/healthz"),
        "SearXNG": _probe(http, f"{settings.searxng_url.rstrip('/')}/"),
        "Sandbox-broker": _probe(http, f"{settings.broker_url.rstrip('/')}/health"),
    }
    results = await asyncio.gather(*checks.values())
    return [{"name": name, "up": up} for name, up in zip(checks.keys(), results, strict=True)]


async def _rag() -> list[dict]:
    """Размеры RAG-коллекций по namespace (None — Qdrant недоступен)."""
    vstore = shared_vstore()
    names = sorted(set(_RAG_NAMESPACES.values()))
    try:
        counts = await asyncio.wait_for(
            asyncio.gather(*(vstore.count(ns) for ns in names)), timeout=6
        )
    except Exception:  # noqa: BLE001 — таймаут/недоступность Qdrant, дашборд не падает
        counts = [None] * len(names)
    return [{"namespace": ns, "points": c} for ns, c in zip(names, counts, strict=True)]


def _agents() -> list[dict]:
    """Агенты + их счётчики использования."""
    metrics = shared_metrics()
    out: list[dict] = []
    for card in REGISTRY.values():
        m = metrics.for_agent(card.name)
        out.append(
            {
                "name": card.name,
                "title": card.title,
                "sensitivity": str(card.sensitivity),
                "models": card.models,
                "namespace": _RAG_NAMESPACES.get(card.name, ""),
                "requests": m.requests,
                "input_tokens": m.input_tokens,
                "output_tokens": m.output_tokens,
                "total_tokens": m.input_tokens + m.output_tokens,
                "last_used": m.last_used,
            }
        )
    return out


@router.get("/api/dashboard")
async def api_dashboard(request: Request) -> dict:
    """JSON-срез состояния комбайна."""
    http: httpx.AsyncClient = request.app.state.http
    services, rag = await asyncio.gather(_services(http), _rag())
    conversations, messages = shared_store().stats()
    return {
        "uptime_sec": shared_metrics().uptime_sec(),
        "services": services,
        "agents": _agents(),
        "rag": rag,
        "conversations": conversations,
        "messages": messages,
    }


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page() -> str:
    """HTML-страница дашборда."""
    return _PAGE


_PAGE = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Combine — дашборд</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin:0; font:14px/1.5 system-ui,Segoe UI,Roboto,sans-serif;
         background:#0f1115; color:#e6e8ec; padding:24px; }
  h1 { font-size:20px; margin:0 0 2px; }
  .sub { color:#8b909a; font-size:13px; margin-bottom:20px; }
  .grid { display:grid; gap:14px; grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); }
  .card { background:#171a21; border:1px solid #232833; border-radius:12px; padding:16px; }
  .card h2 { font-size:12px; text-transform:uppercase; letter-spacing:.06em;
             color:#8b909a; margin:0 0 12px; }
  .row { display:flex; justify-content:space-between; align-items:center; padding:5px 0;
         border-bottom:1px solid #1f242e; }
  .row:last-child { border-bottom:0; }
  .dot { width:9px; height:9px; border-radius:50%; display:inline-block; margin-right:8px; }
  .up { background:#3fb950; } .down { background:#f85149; }
  .muted { color:#8b909a; } .big { font-size:22px; font-weight:600; }
  .agent .title { font-weight:600; margin-bottom:6px; }
  .tag { display:inline-block; font-size:11px; padding:1px 7px; border-radius:999px;
         background:#222834; color:#aab2c0; margin:2px 4px 2px 0; }
  .sec-secret { color:#f0883e; } .sec-internal { color:#d2a8ff; } .sec-public { color:#3fb950; }
  .stat { display:flex; gap:18px; flex-wrap:wrap; margin-top:8px; }
  .stat div span { display:block; font-size:11px; color:#8b909a; }
  .err { color:#f85149; }
  a { color:#58a6ff; }
</style>
</head>
<body>
  <h1>🐜 AI Combine</h1>
  <div class="sub">Дашборд · обновляется каждые 10 с · <span id="uptime"></span></div>
  <div class="grid">
    <div class="card"><h2>Сервисы</h2><div id="services"></div></div>
    <div class="card"><h2>База знаний (RAG)</h2><div id="rag"></div>
      <div class="row"><span class="muted">Разговоры в памяти</span><span id="convs" class="big"></span></div>
    </div>
  </div>
  <h2 style="font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:#8b909a;margin:22px 0 12px">Агенты</h2>
  <div class="grid" id="agents"></div>
<script>
const fmt = n => n==null ? "—" : n.toLocaleString("ru-RU");
const ago = ts => { if(!ts) return "не использовался";
  const s = Math.floor(Date.now()/1000 - ts);
  if(s<60) return s+" с назад"; if(s<3600) return Math.floor(s/60)+" мин назад";
  if(s<86400) return Math.floor(s/3600)+" ч назад"; return Math.floor(s/86400)+" д назад"; };
const secCls = s => "sec-"+(s||"").toLowerCase();

async function load(){
  let d;
  try { d = await (await fetch("/api/dashboard")).json(); }
  catch(e){ document.getElementById("services").innerHTML =
    '<div class="err">оркестратор недоступен</div>'; return; }

  const up = d.uptime_sec;
  document.getElementById("uptime").textContent =
    "uptime " + (up<3600 ? Math.floor(up/60)+" мин" : Math.floor(up/3600)+" ч "+Math.floor(up%3600/60)+" мин");

  document.getElementById("services").innerHTML = d.services.map(s =>
    `<div class="row"><span><span class="dot ${s.up?'up':'down'}"></span>${s.name}</span>`+
    `<span class="muted">${s.up?'ok':'недоступен'}</span></div>`).join("");

  document.getElementById("rag").innerHTML = d.rag.map(r =>
    `<div class="row"><span class="muted">${r.namespace}</span><span>${r.points==null?'<span class="err">n/a</span>':fmt(r.points)+' чанков'}</span></div>`).join("");
  document.getElementById("convs").textContent = fmt(d.conversations);

  document.getElementById("agents").innerHTML = d.agents.map(a =>
    `<div class="card agent">
       <div class="title">${a.title} <span class="muted ${secCls(a.sensitivity)}">· ${a.sensitivity}</span></div>
       <div>${a.models.map(m=>`<span class="tag">${m}</span>`).join("")}</div>
       <div class="stat">
         <div><b>${fmt(a.requests)}</b><span>запросов</span></div>
         <div><b>${fmt(a.total_tokens)}</b><span>токенов (in+out)</span></div>
       </div>
       <div class="muted" style="margin-top:8px;font-size:12px">RAG: ${a.namespace||'—'} · ${ago(a.last_used)}</div>
     </div>`).join("");
}
load(); setInterval(load, 10000);
</script>
</body>
</html>"""
