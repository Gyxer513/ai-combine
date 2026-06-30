# AI Combine 🌾

🌐 **English** · [Русский](README.ru.md)

A self-hosted multi-agent "combine" built on cheap LLMs (Chinese models + OpenRouter
free tiers behind a single LiteLLM proxy). Four agents reachable via OpenWebUI and
Telegram, RAG over your own knowledge base, isolated command execution, and scheduled
autonomous workers.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-gh--pages-teal.svg)](https://gyxer513.github.io/ai-combine/)

> ⚠️ **Personal project, published as-is.** Run it **only on your own infrastructure
> and against your own targets**. The agents execute commands and reach into your infra
> on your behalf — read [SECURITY.md](SECURITY.md) before using. No warranty ([MIT](LICENSE)).

📖 Full documentation: **https://gyxer513.github.io/ai-combine/**

## Agents

| Agent | Role | What it does |
|---|---|---|
| 🛡 **recon** | SecOps | scanning/hardening your own infra (nmap/nuclei/nikto/testssl/httpx in a sandbox) |
| 🔨 **coder** | Coder | read/write/review code, run tests in a sandbox, GitHub |
| 💬 **assistant** | General | general questions, search, research |
| 🧭 **planner** | Orchestrator | slices a project brief into child tasks for the agents (Deck cards) |

## Features

- **Multi-agent** on Pydantic AI: persona via `instructions=`, per-agent model
  fallback chains (`FallbackModel`), token-budget history compaction, history/metrics
  persisted on SQLite.
- **LLM routing** through LiteLLM (Alibaba Model Studio + OpenRouter) with one key.
- **RAG** over Nextcloud (Notes + WebDAV) → Qdrant; embeddings **via API** (no heavy
  local models — saves RAM).
- **Frontends**: OpenWebUI (agents as "models") + Telegram (one bot per agent, whitelist).
- **Sandbox**: isolated execution via a privileged `sandbox-broker` (it alone holds
  `docker.sock`), binary allowlist, hardening, injection defenses.
- **Autonomy**: scheduled workers — tasks from Nextcloud Deck, money-making idea
  research; the planner slices a project into tasks for the other agents.

## Stack

Python 3.11+ · Pydantic AI · FastAPI · LiteLLM · Qdrant · SearXNG · aiogram 3 ·
OpenWebUI · Docker. LLMs and embeddings go through APIs (no heavy local models).

## Services (docker-compose)

| Service | Profile | Description |
|---|---|---|
| `litellm` | (base) | LLM proxy, OpenAI-compatible API over Alibaba + OpenRouter |
| `qdrant` | (base) | RAG vector store |
| `searxng` | (base) | self-hosted metasearch for `web_search` |
| `openwebui` | (base) | web chat (:3000) |
| `orchestrator` | `app` | FastAPI + Pydantic AI, 4 agents, dashboard `/dashboard` (:8000) |
| `sandbox-broker` | `app` | **the only holder of `docker.sock`** — spawns sandboxes |
| `rag-indexer` | `app` | Nextcloud → Qdrant (loop) |
| `research-worker` | `app` | assistant researches money-making ideas → Deck board "Ideas" |
| `deck-worker` | `app` | tasks from Nextcloud Deck → agents |
| `telegram-bot` | `telegram` | agent bots (one per agent) |

## Quickstart

```bash
# 1. Config
cp .env.example .env
#   fill ALIBABA_API_KEY / OPENROUTER_API_KEY / LITELLM_MASTER_KEY
#   generate a token: openssl rand -hex 32   -> ORCHESTRATOR_API_TOKEN

# 2. Base infra
docker compose up -d                       # litellm + qdrant + searxng + openwebui

# 3. Application (orchestrator + sandbox-broker + workers)
docker compose --profile app up -d

# 4. Telegram bots (if tokens are set)
docker compose --profile telegram up -d
```

Check the proxy and an agent:

```bash
curl http://localhost:4000/v1/models -H "Authorization: Bearer $LITELLM_MASTER_KEY"

curl -s http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ORCHESTRATOR_API_TOKEN" \
  -d '{"message": "Who are you?", "agent": "recon"}'
```

> ⚠️ **Orchestrator access.** The port is bound to `127.0.0.1:8000` (localhost only) —
> the agents hold a GitHub PAT / RAG / sandbox access and must not be exposed. Set
> `ORCHESTRATOR_API_TOKEN` (e.g. `openssl rand -hex 32`); the Telegram bots and workers
> pick up the same token. Empty = enforcement off (localhost bind only); the
> orchestrator warns in the logs. For LAN access, put a reverse proxy with TLS+auth
> in front.

## Models per agent

| Agent | Model (primary → fallback) | Sensitivity |
|---|---|---|
| 💬 `assistant` | `owl-alpha-free` → qwen-plus → qwen-max | public |
| 🛡 `recon` | `glm-5.1` (thinking) → nemotron-super-free → qwen-max | secret |
| 🔨 `coder` | `nemotron-super-free` → qwen-coder → qwen-max | internal |
| 🧭 `planner` | `qwen-max` → qwen-plus | internal |

Per-agent fallback chains are assembled via Pydantic AI `FallbackModel`. Model choice is
tied to `DataSensitivity` — sensitive data never goes to cloaked models. Personas are set
via `instructions=` (not `system_prompt=`), so they apply on every turn including the
multi-turn `/chat` and OpenWebUI paths.

## OpenWebUI

Admin Panel → Settings → Connections → OpenAI API → ＋:

- **Base URL:** `http://orchestrator:8000/v1` (same compose network) or
  `http://host.docker.internal:8000/v1`.
- **API key:** the value of `ORCHESTRATOR_API_TOKEN` (the orchestrator checks it on
  `/chat`, `/agents`, `/v1/*`).

The model dropdown will show `assistant` / `recon` / `coder` / `planner`. Direct LiteLLM
models (`glm-5.1`, `qwen-*`) are a separate connection to `http://litellm:4000/v1` and
have **no** persona/tools.

## RAG (knowledge base from Nextcloud)

Agents search a personal knowledge base via `search_knowledge_base`. Embeddings go
**through the API** (Alibaba `text-embedding-v4` behind LiteLLM, dim 1024), no local
TEI/BGE-M3. Vectors live in Qdrant, one collection per namespace.

- Sources: Nextcloud **Notes** (category → namespace) and **WebDAV folders**.
- Namespace per agent: assistant/planner → `personal`, recon → `security`, coder → `coding`.
- The indexer is incremental: `data/rag_manifest.json` stores hashes, unchanged docs
  aren't re-embedded.

Set in `.env`: `NEXTCLOUD_URL`, `NEXTCLOUD_USER`, `NEXTCLOUD_APP_PASSWORD` (an app
password from Settings → Security). Notes category mapping —
`RAG_NOTES_CATEGORY_MAP="Security:security, Dev:coding"`; WebDAV folders —
`RAG_WEBDAV_FOLDERS="/Knowledge/Security:security"`.

```bash
docker compose --profile app up -d   # rag-indexer loops every RAG_INDEX_INTERVAL_MIN (default 60)
docker compose run --rm -e RAG_INDEX_INTERVAL_MIN=0 rag-indexer   # one-off run
```

## Telegram

An aiogram 3 bot — a bridge to the orchestrator (it doesn't call the LLM itself).
Access is whitelisted.

**One bot per agent** — each bot is hard-bound to its agent, no switching (the bot *is*
the agent). One process polls all configured tokens and picks the agent by
`message.bot.token`.

- Commands: `/who` — which bot is this; `/reset` — forget history; `/start` `/help`.
- Plain text goes to that bot's agent; history keyed by `tg:<agent>:<chat_id>:<session>`.

In `.env`:
- `TELEGRAM_BOT_TOKEN` — shared, goes to assistant (or explicit `TELEGRAM_BOT_TOKEN_ASSISTANT`);
- `TELEGRAM_BOT_TOKEN_RECON` / `_CODER` / `_PLANNER` — separate bots (create in @BotFather).
  Only configured tokens are polled — you can start with a single bot.
- `TELEGRAM_ALLOWED_USERS` — numeric user IDs, comma-separated (find yours via
  @userinfobot). Empty = fail-closed (nobody; denied IDs are logged).

## Autonomy: deck-worker (tasks from Nextcloud Deck)

`deck-worker` runs tasks **without a human in the loop**: it polls a Nextcloud Deck
board, takes cards from To Do, routes by label to the right agent, runs it through the
orchestrator, posts the result as a comment, and moves the card to Done. Claiming (a
move to In Progress) protects against double processing.

- Board (`DECK_BOARD`), stacks `To Do` / `In Progress` / `Done`.
- Label → agent: `DECK_LABEL_AGENT_MAP="sec:recon,code:coder,ask:assistant"`, no label →
  `DECK_DEFAULT_AGENT` (assistant). A failed task → `DECK_FAILED_STACK` (default
  "Failed"), **not** Done; if that stack is missing, the card stays in In Progress.
- Polls every `DECK_POLL_INTERVAL_MIN`.

## Autonomy: research-worker

assistant regularly looks for money-making ideas and drops them as cards onto the Deck
board "Ideas". **Token-bounded by design:** not an agentic loop but a deterministic
pipeline per run — rotate the theme (by date) → N SearXNG searches (0 tokens) → **one**
cheap LLM call (`qwen-flash`) deduped against existing cards → new cards.

- Rotation themes: `RESEARCH_THEMES` (CSV); ideas per run: `RESEARCH_IDEAS_PER_RUN`.
- Period: `RESEARCH_INTERVAL_MIN` (default 1440 = once a day).

## Orchestration: 🧭 planner (project decomposition)

The `planner` agent works like a team lead: it takes a project brief or goal and slices
it into child tasks for the other agents. It first shows the plan as text (subtask =
executor + acceptance criterion), and on confirmation calls the `slice_project` tool,
which lays the subtasks out as cards in the `To Do` stack (with the executor's label) —
then `deck-worker` picks them up. Together this forms a brief → tasks → execution cascade.

- Executors: `recon` / `coder` / `assistant` (labels `sec` / `code` / `ask`).
- Model: `qwen-max` → `qwen-plus` (decomposition needs reasoning).
- Own Telegram bot: `TELEGRAM_BOT_TOKEN_PLANNER`.
- Labels `sec`/`code`/`ask` must exist on the board — otherwise a card is created without
  a label and goes to the default agent.

## Sandbox (isolated execution)

recon and coder run commands in a one-shot Docker container and analyze the output
themselves (instead of asking for copy-paste):

- 🛡 recon — `run_security_command` (nmap/openssl/dig/curl/nc) **with network**, for
  scanning/hardening your own infra.
- 🔨 coder — `run_shell` (code/tests/linters) **without network**.

Sandbox hardening: `cap_drop ALL`, `no-new-privileges`, read-only rootfs + tmpfs `/tmp`,
mem/cpu/pids limits, non-root (uid 10001), timeout, `--rm`. Before running, every command
is checked against a binary allowlist (no `$()`/backtick, no chains to a non-allowlisted
binary) — a defense against prompt injection.

### Execution architecture (sandbox-broker)

`docker.sock` is mounted **only** into the separate `sandbox-broker` service — the
orchestrator has no direct Docker access. The orchestrator sends the broker a minimal
`{profile, command}` over HTTP; the image, hardening, network and allowlist are baked
into the broker and not controllable from outside. So RCE in the orchestrator (via
injection) yields neither arbitrary docker nor the host — only an allowlisted command in
a locked-down sandbox.

```
agent → orchestrator → (HTTP) → sandbox-broker → (docker.sock) → hardened sandbox
```

```bash
docker build -t ai-combine/sandbox:latest -f docker/sandbox.Dockerfile .  # build once
```

## Dashboard

A single status screen on the orchestrator itself (port 8000), no separate service:

- `GET /dashboard` — HTML page (inline, auto-refresh every 10s): service health
  (LiteLLM/Qdrant/SearXNG/broker), agent cards with usage counters (requests, tokens,
  last seen), RAG collection sizes, in-memory conversation count.
- `GET /api/dashboard` — the same data as JSON.

## History compaction

Before each model call, history is compacted to a token budget (`HISTORY_MAX_TOKENS`,
default 12000) — a `ProcessHistory` capability on every agent
([agents/history.py](src/orchestrator/agents/history.py)). It works on both paths
(Telegram `/chat` and OpenWebUI `/v1`): keep a fresh tail, fold earlier messages with a
marker without breaking tool-call pairs. The system prompt (`instructions=`) is separate
and left untouched.

## Local development

```bash
uv sync
uv run ruff check .
uv run pytest

# Orchestrator on the host (services on localhost):
LITELLM_BASE_URL=http://localhost:4000/v1 SEARXNG_URL=http://localhost:8888 \
  QDRANT_URL=http://localhost:6333 \
  uv run uvicorn src.orchestrator.main:app --port 8000
```

> On Windows avoid `--reload`: the reloader leaves a zombie worker holding the port and
> running stale code. Restart the process manually.

## Project layout

```
src/
├── orchestrator/    # FastAPI + Pydantic AI: agents, tools, prompts, api
├── deck_worker/     # autonomous tasks from Nextcloud Deck
├── research_worker/ # token-bounded idea research
├── telegram_bot/    # aiogram + whitelist
├── sandbox_broker/  # the only docker.sock holder
└── rag_indexer/     # Nextcloud crawler -> chunks -> embed -> Qdrant
```

## Security

See [SECURITY.md](SECURITY.md) for the full threat model. In short: secrets only in
`.env` (never committed); orchestrator behind a token and bound to localhost; sandbox is
the real isolation boundary (the allowlist is a guardrail); Telegram whitelist is
fail-closed; model choice respects data sensitivity.
