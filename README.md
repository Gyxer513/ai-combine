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
| `searxng` | 8888 | Этап 2 | Self-hosted метапоиск для `web_search` |
| `openwebui` | 3000 | Этап 1 | Веб-чат |
| `orchestrator` | 8000 | Этап 2 | FastAPI + Pydantic AI, 3 агента (профиль `app`) |
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

## Этап 2: оркестратор и три агента

Поднят FastAPI-оркестратор на Pydantic AI со всеми тремя агентами. Каждый —
отдельная «модель» в OpenWebUI; переключение = выбор модели.

| Агент | Модель (основная → fallback) | Чувствительность |
|---|---|---|
| 🍞 `kolobok` | `owl-alpha-free` → qwen-plus → qwen-max | public |
| 🦴 `koschei` | `glm-5.1` (thinking) → nemotron-super-free → qwen-max | secret |
| 🔨 `levsha` | `nemotron-super-free` → qwen-coder → qwen-max | internal |

Инструменты (Этап 2): `web_search` (SearXNG → fallback DuckDuckGo) и простая память
(scratchpad-заметки + многоходовой диалог по `conversation_id`). Пер-агентные
fallback-цепочки собраны через Pydantic AI `FallbackModel` (не через LiteLLM —
там fallbacks ключуются по реальным model_name, а не по именам агентов).

Персона задаётся через `instructions=` (не `system_prompt=`): только так она
применяется на каждом запуске, включая многоходовой диалог и путь OpenWebUI.

```bash
docker compose --profile app up -d        # orchestrator на :8000
```

Эндпоинты оркестратора:

| Метод | Путь | Назначение |
|---|---|---|
| `GET` | `/health`, `/health/litellm` | проверки |
| `GET` | `/agents` | список агентов |
| `POST` | `/chat` | нативный чат: `{message, agent?, conversation_id?}` |
| `GET` | `/v1/models` | OpenAI-совместимый список (по «модели» на агента) |
| `POST` | `/v1/chat/completions` | OpenAI-совместимый чат (stream + non-stream) |

Быстрая проверка (агент выбирается полем `agent`):

```bash
curl -s http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Кто ты?", "agent": "koschei"}'
```

**Агенты в OpenWebUI:** Admin Panel → Settings → Connections → OpenAI API → ＋,
base URL `http://host.docker.internal:8000/v1` (или `http://orchestrator:8000/v1`,
если OpenWebUI в той же compose-сети), ключ любой. В выпадашке моделей появятся
`kolobok` / `koschei` / `levsha`. Прямые модели LiteLLM (`glm-5.1`, `qwen-*`) — это
отдельное подключение к `http://litellm:4000/v1`, у них **нет** персоны/инструментов.

## Этап 3: RAG (база знаний из Nextcloud)

Агенты ищут по личной базе знаний через `search_knowledge_base`. Embeddings —
**через API** (Alibaba `text-embedding-v4` за LiteLLM, dim 1024), без локального
TEI/BGE-M3 — бережём RAM. Вектора в Qdrant, по коллекции на namespace.

- Источники: Nextcloud **Notes** (категория → namespace) и **WebDAV-папки**.
- Namespace на агента: Колобок→`personal`, Кощей→`security`, Левша→`coding`.
- Индексатор инкрементальный: манифест `data/rag_manifest.json` хранит хэши,
  неизменённые документы не переэмбеддятся.

Заполни в `.env`: `NEXTCLOUD_URL`, `NEXTCLOUD_USER`, `NEXTCLOUD_APP_PASSWORD`
(пароль приложения из Настройки → Безопасность). Маппинг категорий Notes —
`RAG_NOTES_CATEGORY_MAP="Security:security, Dev:coding"`; папок WebDAV —
`RAG_WEBDAV_FOLDERS="/Knowledge/Security:security"`.

```bash
# Индексация (профиль indexer в Docker или напрямую):
docker compose --profile indexer run --rm rag-indexer
# либо на хосте:
LITELLM_BASE_URL=http://localhost:4000/v1 QDRANT_URL=http://localhost:6333 \
  uv run python -m src.rag_indexer.main
```

## Локальная разработка

```bash
uv sync                       # установить зависимости
uv run ruff check .
uv run pytest

# Оркестратор на хосте (сервисы торчат на localhost):
LITELLM_BASE_URL=http://localhost:4000/v1 SEARXNG_URL=http://localhost:8888 \
  QDRANT_URL=http://localhost:6333 \
  uv run uvicorn src.orchestrator.main:app --port 8000
```

> На Windows избегай `--reload`: reloader оставляет worker-зомби, который держит
> порт и крутит старый код. Перезапускай процесс вручную.

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
