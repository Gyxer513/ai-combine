# Architecture

```
OpenWebUI / Telegram
        │  (OpenAI-compatible /v1, native /chat — behind a Bearer token)
        ▼
   orchestrator  ──HTTP──▶  sandbox-broker ──docker.sock──▶  one-shot sandboxes
   (Pydantic AI)              (the only holder of the socket)
        │
        ├── LiteLLM ──▶ Alibaba Model Studio + OpenRouter
        ├── Qdrant (RAG, one collection per namespace)
        └── SearXNG (web_search)

   Workers (scheduled): rag-indexer · deck-worker · research-worker
```

## Services (docker-compose)

| Service | Profile | Description |
|---|---|---|
| `litellm` | base | LLM proxy over Alibaba + OpenRouter with one key |
| `qdrant` | base | RAG vector store |
| `searxng` | base | self-hosted metasearch for `web_search` |
| `openwebui` | base | web chat |
| `orchestrator` | app | FastAPI + Pydantic AI, 4 agents, dashboard `/dashboard` |
| `sandbox-broker` | app | **the only holder of `docker.sock`** — spawns sandboxes |
| `rag-indexer` | app | Nextcloud → Qdrant (incremental) |
| `research-worker` | app | assistant researches money-making ideas → Deck board "Ideas" |
| `deck-worker` | app | tasks from Nextcloud Deck → agents |
| `telegram-bot` | telegram | bridge to `/chat`, one bot per agent |

## Key decisions

- **Sandbox-broker.** `docker.sock` is moved out of the orchestrator into a separate
  service. The orchestrator talks to the broker over HTTP; RCE/injection in the
  orchestrator no longer grants direct access to Docker/the host. Profiles `secops`
  (network on) and `coder` (network off).
- **Token-bounded autonomy.** Workers are not an agentic loop but a deterministic
  pipeline: search (0 tokens) + one cheap LLM call. `research-worker` thus drops ideas
  onto Deck for pennies.
- **RAG via API.** Embeddings — Alibaba `text-embedding-v4` behind LiteLLM (no local
  TEI/BGE-M3, saves RAM). The namespace is bound to the agent so foreign data doesn't leak.
- **SQLite persistence.** Conversation history, notes and metrics survive restarts.
- **History compaction.** History is compacted to a token budget (`HISTORY_MAX_TOKENS`)
  before each model call.
- **Local docs search (optional).** A separate `search_docs` tool gives agents semantic
  search over the combine's own Markdown — EmbeddingGemma-300m (int8) via ONNX + FAISS,
  fully local and offline, ~0.4–0.7 GB resident. Off by default; build the index with
  `docker compose --profile docs run --rm docs-indexer`.

## Deck-worker: autonomous tasks

It polls a Nextcloud Deck board: cards from `To Do` → claim by moving to `In Progress`
(protects against double processing) → the agent by label via the orchestrator → result
as a comment → `Done`. A failed task moves to `DECK_FAILED_STACK` (default "Failed"),
**not** Done; if that stack is missing, the card stays in `In Progress` (no false success).

Pairing with the planner: `planner` slices a project into child cards in `To Do`, and
`deck-worker` runs them — forming a brief → tasks → execution cascade.
