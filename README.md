# AI Combine

Личный мульти-агентный комбайн на базе китайских LLM с локальной инфраструктурой.

Три специализированных агента:

| Агент | Роль | Назначение |
|---|---|---|
| 🦴 **Кощей** | SecOps | Обучение ИБ, threat modeling, defensive coding, hardening собственной инфры |
| 🔨 **Левша** | Coder | Работа с Gitea-репозиториями: чтение, написание, ревью, PR |
| 🍞 **Колобок** | General | Общие вопросы, поиск, ресёрч, помощник по жизни |

## Стек

- **Оркестрация:** Pydantic AI + FastAPI
- **LLM-прокси:** LiteLLM (единый API над Alibaba Model Studio + OpenRouter)
- **RAG:** LlamaIndex + Qdrant + TEI (BGE-M3 embeddings)
- **Фронтенды:** OpenWebUI (локальный чат) + Telegram (aiogram 3)
- **Sandbox:** Docker для изолированного exec

## Сервисы (docker-compose)

| Сервис | Порт | Стадия | Описание |
|---|---|---|---|
| `litellm` | 4000 | Этап 1 | LLM-прокси, единый OpenAI-совместимый API |
| `qdrant` | 6333 | Этап 1 | Векторное хранилище |
| `embeddings` (TEI) | 8081 | Этап 1 | BGE-M3 embeddings (Rust, self-hosted) |
| `openwebui` | 3000 | Этап 1 | Веб-чат |
| `orchestrator` | 8000 | Этап 2 | FastAPI + Pydantic AI (профиль `app`) |
| `telegram-bot` | — | Этап 5 | aiogram бот (профиль `telegram`) |
| `rag-indexer` | — | Этап 3 | Nextcloud → Qdrant краулер (профиль `indexer`) |

## Быстрый старт (Этап 1)

```bash
# 1. Конфиг
cp .env.example .env
#   заполни ALIBABA_API_KEY, ALIBABA_WORKSPACE_ID, OPENROUTER_API_KEY, LITELLM_MASTER_KEY

# 2. Поднять инфру Этапа 1 (litellm + qdrant + tei + openwebui)
docker compose up -d litellm qdrant embeddings openwebui

# 3. Проверить роутинг LiteLLM
curl http://localhost:4000/v1/models -H "Authorization: Bearer $LITELLM_MASTER_KEY"

# 4. Открыть чат
#    http://localhost:3000  — выбрать модель qwen-plus и проверить ответ
```

Запуск оркестратора (Этап 2+):

```bash
docker compose --profile app up -d
```

## Локальная разработка

```bash
uv sync                       # установить зависимости
uv run uvicorn src.orchestrator.main:app --reload --port 8000
uv run ruff check .
uv run pytest
```

## Структура

См. план в Nextcloud («AI Combine — Архитектура и план»). Краткая раскладка:

```
src/
├── orchestrator/   # FastAPI + Pydantic AI: агенты, tools, prompts, api
├── telegram_bot/   # aiogram + whitelist
└── rag_indexer/    # Nextcloud WebDAV crawler -> chunks -> embed -> Qdrant
```

## Безопасность

- Telegram: whitelist user_id, long polling, без публичного домена.
- Gitea: scoped token, push только в feature-ветки, всё через PR.
- Nextcloud: app password только read.
- Bash: Docker sandbox без сети, лимиты CPU/RAM, без `--privileged`.
- Модели: выбор по `DATA_SENSITIVITY` — чувствительные данные не уходят в cloaked-модели.
