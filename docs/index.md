# AI Combine

**A self-hosted multi-agent "combine" built on cheap LLMs** (Chinese models from Alibaba
Model Studio + OpenRouter free tiers behind a single LiteLLM proxy). Four agents reachable
via OpenWebUI and Telegram, RAG over your own Nextcloud knowledge base, isolated command
execution, and autonomous workers.

!!! warning "Personal project, as-is"
    Run it **only on your own infrastructure and against your own targets**. The agents
    execute commands and reach into your infra on your behalf — read the
    [security model](security.md) first. MIT license, no warranty.

## Agents

| Agent | Role | What it does |
|---|---|---|
| 🛡 `recon` | SecOps | scan/harden your own infra (nmap/nuclei/nikto/testssl/httpx in a sandbox) |
| 🔨 `coder` | Coder | read/write/review code, run tests in a sandbox, GitHub |
| 💬 `assistant` | General | general questions, search, research |
| 🧭 `planner` | Orchestrator | slices a project brief into child tasks for the agents |

## What's inside

- **Multi-agent** on Pydantic AI: persona via `instructions=`, per-agent model fallback
  chains (`FallbackModel`), token-budget history compaction, history and metrics
  persisted on SQLite.
- **LLM routing** through LiteLLM (Alibaba + OpenRouter) with one key.
- **RAG** over Nextcloud (Notes + WebDAV) → Qdrant; embeddings via API.
- **Frontends**: OpenWebUI (agents as "models") + Telegram (one bot per agent).
- **Sandbox**: isolated execution via a privileged `sandbox-broker` (it alone holds
  docker.sock), binary allowlist, injection defenses.
- **Autonomy**: scheduled workers — tasks from Nextcloud Deck, money-making idea
  research; the planner slices a project into tasks for the other agents.

Next: [quickstart](quickstart.md) · [agents](agents.md) · [architecture](architecture.md)
· [security](security.md).
