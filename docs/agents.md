# Agents

Each agent is a separate "model" in OpenWebUI and (optionally) its own Telegram bot. The
persona is set via `instructions=` (not `system_prompt=`, which is lost when
`message_history` is passed). Models run as a per-agent fallback chain via Pydantic AI
`FallbackModel`. Model choice is tied to `DataSensitivity`: sensitive data never goes to
cloaked models.

| Agent | Model (primary → fallback) | Sensitivity | RAG namespace |
|---|---|---|---|
| 💬 `assistant` | `owl-alpha-free` → qwen-plus → qwen-max | public | personal |
| 🛡 `recon` | `glm-5.1` (thinking) → nemotron-super-free → qwen-max | secret | security |
| 🔨 `coder` | `nemotron-super-free` → qwen-coder → qwen-max | internal | coding |
| 🧭 `planner` | `qwen-max` → qwen-plus | internal | personal |

## 🛡 recon — SecOps

InfoSec learning, threat modeling, hardening of **your own** infra. The
`run_security_command` tool runs commands in an isolated sandbox **with network**
(nmap/openssl/dig/curl/nc + web audit nuclei/nikto/testssl.sh/httpx). Sensitivity
`secret` — paid/enterprise models only, no cloaked.

## 🔨 coder — Coder

Read/write/review code. `run_shell` runs tests/linters in a sandbox **without network**
(exfiltration impossible). GitHub skill: branches, commits, Pull Requests — changes always
go to a feature branch + PR for human review, never to the main branch.

## 💬 assistant — General

General helper: research, search, everyday questions. Sensitivity `public` — free models
first. The same agent powers `research-worker` (autonomous research of money-making ideas
onto the Deck board "Ideas").

## 🧭 planner — Orchestrator

Works like a team lead: takes a project brief/goal and slices it into child tasks for the
other agents. It first shows the plan as text (subtask = executor + acceptance criterion),
and on confirmation calls `slice_project`, which lays the subtasks out as cards in the
`To Do` stack (with the executor's label) — then `deck-worker` picks them up.

- Executors: `recon` / `coder` / `assistant` (labels `sec` / `code` / `ask`).
- Labels `sec`/`code`/`ask` must exist on the board, otherwise a card is created without a
  label and goes to the default agent.

## Telegram

One bot = one agent (hard-bound by token, no switching). Tokens:
`TELEGRAM_BOT_TOKEN_ASSISTANT` / `_RECON` / `_CODER` / `_PLANNER` (or a shared
`TELEGRAM_BOT_TOKEN` → assistant). Access is whitelisted by numeric `user_id`,
**fail-closed** by default (empty list = nobody).
