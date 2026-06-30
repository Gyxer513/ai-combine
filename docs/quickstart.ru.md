# Быстрый старт

## Требования

- Docker + Docker Compose
- Ключи: Alibaba Model Studio (`ALIBABA_API_KEY`) и/или OpenRouter (`OPENROUTER_API_KEY`)
- (опционально) Nextcloud для RAG, Deck-задач и планировщика
- (опционально) Telegram-боты из [@BotFather](https://t.me/BotFather)

## Конфигурация

```bash
cp .env.example .env
# заполни ALIBABA_API_KEY / OPENROUTER_API_KEY / LITELLM_MASTER_KEY
# сгенерируй токен оркестратора:
openssl rand -hex 32   # -> ORCHESTRATOR_API_TOKEN
```

!!! danger "`.env` никогда не коммить"
    В нём реальные секреты (ключи моделей, токены ботов, app password Nextcloud).
    Файл — в `.gitignore`; держите права `600`.

## Запуск

```bash
# базовый слой: LiteLLM, Qdrant, SearXNG, OpenWebUI
docker compose up -d

# приложение: оркестратор + sandbox-broker + воркеры
docker compose --profile app up -d

# Telegram-боты (если заданы токены)
docker compose --profile telegram up -d
```

Проверка прокси:

```bash
curl http://localhost:4000/v1/models -H "Authorization: Bearer $LITELLM_MASTER_KEY"
```

Проверка агента (заголовок `Authorization` нужен, если задан `ORCHESTRATOR_API_TOKEN`):

```bash
curl -s http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ORCHESTRATOR_API_TOKEN" \
  -d '{"message": "Кто ты?", "agent": "recon"}'
```

## Подключение OpenWebUI

Admin Panel → Settings → Connections → OpenAI API → ＋:

- **Base URL:** `http://orchestrator:8000/v1` (в той же compose-сети) или
  `http://host.docker.internal:8000/v1`.
- **Ключ API:** значение `ORCHESTRATOR_API_TOKEN`.

В выпадашке моделей появятся `assistant` / `recon` / `coder` / `planner`.

!!! note "Доступ к оркестратору"
    Порт оркестратора забинден на `127.0.0.1:8000` — у агентов есть GitHub PAT / RAG /
    sandbox, наружу его публиковать нельзя. Для доступа из LAN ставьте обратный прокси
    с TLS и аутентификацией. Подробнее — [Безопасность](security.md).
