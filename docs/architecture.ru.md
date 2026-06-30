# Архитектура

```
OpenWebUI / Telegram
        │  (OpenAI-совместимый /v1, нативный /chat — под Bearer-токеном)
        ▼
   orchestrator  ──HTTP──▶  sandbox-broker ──docker.sock──▶  одноразовые sandbox'ы
   (Pydantic AI)              (единственный с сокетом)
        │
        ├── LiteLLM ──▶ Alibaba Model Studio + OpenRouter
        ├── Qdrant (RAG, по коллекции на namespace)
        └── SearXNG (web_search)

   Воркеры (по расписанию): rag-indexer · deck-worker · research-worker
```

## Сервисы (docker-compose)

| Сервис | Профиль | Описание |
|---|---|---|
| `litellm` | база | LLM-прокси над Alibaba + OpenRouter одним ключом |
| `qdrant` | база | векторное хранилище RAG |
| `searxng` | база | self-hosted метапоиск для `web_search` |
| `openwebui` | база | веб-чат |
| `orchestrator` | app | FastAPI + Pydantic AI, 4 агента, дашборд `/dashboard` |
| `sandbox-broker` | app | **единственный с `docker.sock`** — порождает sandbox'ы |
| `rag-indexer` | app | Nextcloud → Qdrant (инкрементально) |
| `research-worker` | app | assistant ищет идеи заработка → Deck-доска «Идеи» |
| `deck-worker` | app | задачи из Nextcloud Deck → агенты |
| `telegram-bot` | telegram | мост к `/chat`, один бот на агента |

## Ключевые решения

- **Sandbox-broker.** `docker.sock` вынесен из оркестратора в отдельный сервис.
  Оркестратор ходит к брокеру по HTTP; RCE/инъекция в оркестраторе больше не даёт
  прямого доступа к Docker/хосту. Профили `secops` (сеть вкл) и `coder` (сеть выкл).
- **Token-bounded автономия.** Воркеры — не agentic-loop, а детерминированный
  конвейер: поиск (0 токенов) + один дешёвый LLM-вызов. `research-worker` так кладёт
  идеи на Deck за копейки.
- **RAG через API.** Embeddings — Alibaba `text-embedding-v4` за LiteLLM (без
  локального TEI/BGE-M3, бережём RAM). Namespace привязан к агенту, чужие данные не
  утекают.
- **Персист на SQLite.** История диалогов, заметки и метрики переживают рестарт.
- **History compaction.** История ужимается по токен-бюджету (`HISTORY_MAX_TOKENS`)
  перед запросом к модели.
- **Локальный поиск по докам (опционально).** Отдельный инструмент `search_docs` даёт
  агентам семантический поиск по собственным MD комбайна — EmbeddingGemma-300m (int8)
  через ONNX + FAISS, полностью локально и офлайн, ~0.4–0.7 ГБ резидентно. По умолчанию
  выключено; сборка индекса: `docker compose --profile docs run --rm docs-indexer`.

## Deck-worker: автономные задачи

Опрашивает доску Nextcloud Deck: карточки из `To Do` → claim переносом в `In Progress`
(защита от повторной обработки) → агент по метке через оркестратор → результат
комментарием → `Done`. Провал задачи уезжает в `DECK_FAILED_STACK` (дефолт «Failed»),
**не** в Done; если стека нет — карточка остаётся в `In Progress` (не ложный успех).

Связка с планировщиком: `planner` режет проект на дочерние карточки в `To Do`, а
`deck-worker` их исполняет — получается каскад «ТЗ → задачи → выполнение».
