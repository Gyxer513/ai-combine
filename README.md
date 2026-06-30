# AI Combine 🌾

Self-hosted мульти-агентный «комбайн» на дешёвых LLM (китайские модели + free-tier
OpenRouter за единым LiteLLM-прокси). Четыре агента с характером, доступ через
OpenWebUI и Telegram, RAG по своей базе знаний, изолированное исполнение команд,
автономные воркеры по расписанию.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

> ⚠️ **Личный проект, опубликован «как есть».** Запускайте **только на своей
> инфраструктуре**. Агенты исполняют команды и обращаются к вашей инфре — перед
> использованием прочитайте [SECURITY.md](SECURITY.md). Без гарантий ([MIT](LICENSE)).

## Агенты

| Агент | Роль | Назначение |
|---|---|---|
| 🦴 **Кощей** | SecOps | ИБ, скан/хардненинг своей инфры (nmap/nuclei/nikto/testssl/httpx в sandbox) |
| 🔨 **Левша** | Coder | Код: чтение/написание/ревью, прогон тестов в sandbox, GitHub |
| 🍞 **Колобок** | General | Общие вопросы, поиск, ресёрч |
| 👴 **Дед** | Chronicler | Летопись комбайна и проектов; пересказ событий |

## Возможности

- **Мульти-агент** на Pydantic AI: персона (`instructions=`), пер-агентные
  fallback-цепочки моделей (`FallbackModel`), ужимание истории по токен-бюджету,
  персист истории/метрик на SQLite.
- **LLM-роутинг** через LiteLLM (Alibaba Model Studio + OpenRouter) одним ключом.
- **RAG** по Nextcloud (Notes + WebDAV) → Qdrant; embeddings **через API**
  (без локальных тяжёлых моделей — бережём RAM).
- **Фронтенды**: OpenWebUI (агенты как «модели») + Telegram (бот на агента, whitelist).
- **Sandbox**: изолированное исполнение через привилегированный `sandbox-broker`
  (docker.sock только у него), allowlist бинарей, hardening, защита от инъекций.
- **Автономия**: воркеры по расписанию — задачи из Nextcloud Deck, ресёрч идей
  заработка, дневная летопись.

## Стек

Python 3.11+ · Pydantic AI · FastAPI · LiteLLM · Qdrant · SearXNG · aiogram 3 ·
OpenWebUI · Docker. LLM и embeddings — через API (без локальных тяжёлых моделей).

## Сервисы (docker-compose)

| Сервис | Профиль | Описание |
|---|---|---|
| `litellm` | (база) | LLM-прокси, OpenAI-совместимый API над Alibaba + OpenRouter |
| `qdrant` | (база) | векторное хранилище RAG |
| `searxng` | (база) | self-hosted метапоиск для `web_search` |
| `openwebui` | (база) | веб-чат (:3000) |
| `orchestrator` | `app` | FastAPI + Pydantic AI, 4 агента, дашборд `/dashboard` (:8000) |
| `sandbox-broker` | `app` | **единственный с `docker.sock`** — порождает sandbox'ы |
| `rag-indexer` | `app` | Nextcloud → Qdrant (цикл) |
| `research-worker` | `app` | Колобок ищет идеи заработка → Deck-доска «Идеи» |
| `chronicle-worker` | `app` | Дед пишет дневную летопись |
| `deck-worker` | `app` | задачи из Nextcloud Deck → агенты |
| `telegram-bot` | `telegram` | боты агентов (по одному на агента) |

## Быстрый старт (Этап 1)

```bash
# 1. Конфиг
cp .env.example .env
#   заполни ALIBABA_API_KEY, ALIBABA_WORKSPACE_ID, OPENROUTER_API_KEY, LITELLM_MASTER_KEY

# 2. Поднять инфру (litellm + qdrant + searxng + openwebui)
docker compose up -d litellm qdrant searxng openwebui

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
если OpenWebUI в той же compose-сети), **ключ = `ORCHESTRATOR_API_TOKEN`** (если задан;
оркестратор проверяет его на `/chat`, `/agents`, `/v1/*`). В выпадашке моделей появятся
`kolobok` / `koschei` / `levsha` / `ded`. Прямые модели LiteLLM (`glm-5.1`, `qwen-*`) — это
отдельное подключение к `http://litellm:4000/v1`, у них **нет** персоны/инструментов.

> **Доступ к оркестратору.** Порт забинден на `127.0.0.1:8000` (только localhost) — у
> агентов есть GitHub PAT / RAG / sandbox, наружу публиковать нельзя. Задай
> `ORCHESTRATOR_API_TOKEN` (напр. `openssl rand -hex 32`) — тот же токен подхватывают
> Telegram-боты и воркеры. Пусто = enforcement выключен (только bind localhost),
> оркестратор предупредит в логах. Для LAN — обратный прокси с TLS+auth.

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

## Этап 5: Telegram-бот

Бот на aiogram 3 — мост к оркестратору (сам LLM не зовёт). Доступ по whitelist.

**Один бот на агента** — каждый бот жёстко привязан к своему агенту, переключения
нет (бот *и есть* агент). Один процесс поллит все заданные токены и выбирает агента
по `message.bot.token`.

- Команды: `/who` — кто этот бот; `/reset` — забыть историю; `/start` `/help`.
- Обычный текст уходит агенту этого бота; история по `tg:<agent>:<chat_id>:<session>`.

В `.env`:
- `TELEGRAM_BOT_TOKEN` — общий, идёт Колобку (или явный `TELEGRAM_BOT_TOKEN_KOLOBOK`);
- `TELEGRAM_BOT_TOKEN_KOSCHEI`, `TELEGRAM_BOT_TOKEN_LEVSHA` — отдельные боты
  (создать в @BotFather). Поллятся только заданные — можно начать с одного.
- `TELEGRAM_ALLOWED_USERS` — числовые user_id через запятую (узнать у @userinfobot),
  общий для всех ботов. Пустой = fail-closed (никого; id отказанных пишутся в лог).

```bash
docker compose --profile telegram up -d
# либо на хосте (оркестратор на localhost):
ORCHESTRATOR_URL=http://localhost:8010 uv run python -m src.telegram_bot.main
```

## Всё в Docker (durable, always-on)

Чтобы система пережила перезагрузку и база знаний оставалась свежей — запускай
оркестратор, бота и автоиндексатор в Docker (у всех `restart: unless-stopped`):

```bash
docker compose up -d                              # инфра: litellm, qdrant, searxng, openwebui
docker compose --profile app up -d                # orchestrator (:8000) + авто-RAG-индексатор
docker compose --profile telegram up -d           # telegram-бот
```

- Авто-индексация: `rag-indexer` крутится циклом каждые `RAG_INDEX_INTERVAL_MIN`
  минут (дефолт 60). Разовый прогон: `docker compose run --rm -e RAG_INDEX_INTERVAL_MIN=0 rag-indexer`.
- В Docker оркестратор доступен сервисам по имени `orchestrator:8000` — в OpenWebUI
  укажи подключение `http://orchestrator:8000/v1` (не `host.docker.internal`).
- localhost-оверрайды (`LITELLM_BASE_URL=...localhost...`) нужны ТОЛЬКО при запуске
  на хосте; в Docker дефолты (имена сервисов) работают сами.

## Автономия: Deck-worker (задачи из Nextcloud Deck)

`deck-worker` выполняет задачи **без участия человека**: опрашивает доску
Nextcloud Deck, берёт карточки из To Do, роутит по метке нужному агенту,
выполняет через оркестратор, пишет результат комментарием и двигает в Done.
Claim переносом в In Progress защищает от повторной обработки.

- Доска (`DECK_BOARD`, дефолт «Задачи AI Combine»), стеки `To Do` / `In Progress`
  / `Done`.
- Метка → агент: `DECK_LABEL_AGENT_MAP="sec:koschei,code:levsha,ask:kolobok"`,
  без метки → `DECK_DEFAULT_AGENT` (kolobok).
- Опрос каждые `DECK_POLL_INTERVAL_MIN` (в профиле `app` дефолт 2 мин).

Нужны `NEXTCLOUD_URL` / `NEXTCLOUD_USER` / `NEXTCLOUD_APP_PASSWORD` (app password
из Настройки → Безопасность — тот же, что для RAG-индексатора).

```bash
docker compose --profile app up -d            # deck-worker крутится циклом
# разовый прогон:
docker compose run --rm -e DECK_POLL_INTERVAL_MIN=0 deck-worker
```

## Автономия: research-worker (ресёрч заработка)

Колобок регулярно ищет идеи заработка (автоматизация, AI, нестандартное) и кладёт
их карточками на Deck-доску `Идеи`. **Token-bounded by design:** не agentic-loop, а
детерминированный конвейер на один прогон — ротация темы (по дате) → N поисков
SearXNG (0 токенов) → **один** дешёвый LLM-вызов (`qwen-flash`) с антидублем по уже
существующим карточкам → новые карточки. Один LLM-вызов + потолок вывода = копейки.

- Темы для ротации: `RESEARCH_THEMES` (CSV); идей за прогон — `RESEARCH_IDEAS_PER_RUN`.
- Период: `RESEARCH_INTERVAL_MIN` (дефолт 1440 = раз в день).

```bash
docker compose --profile app up -d                  # research-worker раз в день
docker compose run --rm -e RESEARCH_INTERVAL_MIN=0 research-worker   # разовый прогон
```

## Автономия: 👴 Дед-летописец (chronicle-worker)

Четвёртый агент **Дед** ведёт летопись. Раз в день `chronicle-worker` собирает
«день»: выполненные Deck-задачи (Done) + новые идеи + изменённые заметки владельца →
Дед пишет короткий нарратив → дозапись в Nextcloud-заметку «Летопись AI Combine»
(новая запись сверху, под датой). Интерактивно Дед пересказывает события.

- Модели разведены: **интерактивный** Дед (чат/бот) — быстрая `qwen-plus`;
  **разовая летопись** — жирная `nemotron-ultra-free` (NVIDIA Nemotron-3 Ultra
  550B, 1M контекст; качество нарратива важнее скорости, free-тир медленный для
  чата) через `CHRONICLE_MODEL`.
- Свой Telegram-бот: `TELEGRAM_BOT_TOKEN_DED` (как у Кощея/Левши/Колобка).
- Окно дня — `CHRONICLE_LOOKBACK_HOURS` (24); период — `CHRONICLE_INTERVAL_MIN` (1440).

```bash
docker compose --profile app up -d                   # chronicle-worker раз в день
docker compose run --rm -e CHRONICLE_INTERVAL_MIN=0 chronicle-worker   # разовый прогон
```

## Этап 6: Sandbox (изолированное исполнение)

Кощей и Левша запускают команды в одноразовом Docker-контейнере и сами разбирают
вывод (а не просят копипастить):

- 🦴 Кощей — `run_security_command` (nmap/openssl/dig/curl/nc) **с сетью**, для
  скана/харденинга собственной инфры.
- 🔨 Левша — `run_shell` (код/тесты/линтеры) **без сети**.

Hardening sandbox'а: `cap_drop ALL`, `no-new-privileges`, read-only rootfs +
tmpfs `/tmp`, лимиты mem/cpu/pids, non-root (uid 10001), таймаут, `--rm`.

Каждую команду перед запуском проверяет allowlist бинарей (без `$()`/backtick и
цепочек на чужой бинарь) — защита от prompt injection.

### Архитектура исполнения (sandbox-broker)

`docker.sock` смонтирован **только** в отдельный сервис `sandbox-broker` — у
оркестратора прямого доступа к Docker нет. Оркестратор шлёт брокеру по HTTP
минимальный запрос `{profile, command}`; образ, hardening, сеть и allowlist
захардкожены в брокере и снаружи не управляются. Так RCE в оркестраторе (через
инъекцию) не даёт ни произвольного docker, ни хоста — лишь allowlist-команду в
зажатом sandbox.

```
agent → orchestrator → (HTTP) → sandbox-broker → (docker.sock) → hardened sandbox
```

```bash
docker build -t ai-combine/sandbox:latest -f docker/sandbox.Dockerfile .  # образ sandbox, один раз
```

## Дашборд

Один экран статуса на том же сервисе-оркестраторе (порт 8000), без отдельного
сервиса/домена:

- `GET /dashboard` — HTML-страница (inline, авто-обновление каждые 10 с): здоровье
  сервисов (LiteLLM/Qdrant/SearXNG/брокер), карточки агентов со счётчиками
  использования (запросы, токены, когда последний раз), размеры RAG-коллекций,
  число разговоров в памяти.
- `GET /api/dashboard` — те же данные в JSON.

Метрики in-memory, считаются с момента старта процесса (см.
[metrics.py](src/orchestrator/metrics.py)). Кнопку в OpenWebUI не добавляли —
это сторонний образ без точки расширения; дашборд открывается по своему адресу
`:8000/dashboard`.

## Ужимание истории диалога

Перед каждым запросом к модели история ужимается до токен-бюджета
(`HISTORY_MAX_TOKENS`, дефолт 12000) — `ProcessHistory`-capability на всех агентах
([agents/history.py](src/orchestrator/agents/history.py)). Работает на обоих путях
(Telegram `/chat` и OpenWebUI `/v1`): держим свежий хвост, ранние сообщения
сворачиваем с пометкой, не разрывая tool-call пары. Системный промпт
(`instructions=`) идёт отдельно и не трогается. LLM-суммаризация старого хвоста —
позже, вместе с персистом состояния по `conversation_id`.

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
