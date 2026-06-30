# Quickstart

## Requirements

- Docker + Docker Compose
- Keys: Alibaba Model Studio (`ALIBABA_API_KEY`) and/or OpenRouter (`OPENROUTER_API_KEY`)
- (optional) Nextcloud for RAG, Deck tasks and the planner
- (optional) Telegram bots from [@BotFather](https://t.me/BotFather)

## Configuration

```bash
cp .env.example .env
# fill ALIBABA_API_KEY / OPENROUTER_API_KEY / LITELLM_MASTER_KEY
# generate the orchestrator token:
openssl rand -hex 32   # -> ORCHESTRATOR_API_TOKEN
```

!!! danger "Never commit `.env`"
    It holds real secrets (model keys, bot tokens, the Nextcloud app password). The file
    is in `.gitignore`; keep it `600`.

## Run

```bash
# base layer: LiteLLM, Qdrant, SearXNG, OpenWebUI
docker compose up -d

# application: orchestrator + sandbox-broker + workers
docker compose --profile app up -d

# Telegram bots (if tokens are set)
docker compose --profile telegram up -d
```

Check the proxy:

```bash
curl http://localhost:4000/v1/models -H "Authorization: Bearer $LITELLM_MASTER_KEY"
```

Check an agent (the `Authorization` header is required if `ORCHESTRATOR_API_TOKEN` is set):

```bash
curl -s http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ORCHESTRATOR_API_TOKEN" \
  -d '{"message": "Who are you?", "agent": "recon"}'
```

## Connecting OpenWebUI

Admin Panel → Settings → Connections → OpenAI API → ＋:

- **Base URL:** `http://orchestrator:8000/v1` (same compose network) or
  `http://host.docker.internal:8000/v1`.
- **API key:** the value of `ORCHESTRATOR_API_TOKEN`.

The model dropdown will show `assistant` / `recon` / `coder` / `planner`.

!!! note "Orchestrator access"
    The orchestrator port is bound to `127.0.0.1:8000` — the agents hold a GitHub PAT /
    RAG / sandbox access, so it must not be exposed. For LAN access put a reverse proxy
    with TLS and auth in front. See [Security](security.md).
