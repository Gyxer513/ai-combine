# Агенты

Каждый агент — отдельная «модель» в OpenWebUI и (опционально) свой Telegram-бот.
Персона задаётся через `instructions=` (не `system_prompt=` — тот теряется при
передаче `message_history`). Модели идут пер-агентной fallback-цепочкой через Pydantic
AI `FallbackModel`. Выбор моделей завязан на `DataSensitivity`: чувствительные данные
не уходят в cloaked-модели.

| Агент | Модель (основная → fallback) | Sensitivity | RAG namespace |
|---|---|---|---|
| 💬 `assistant` | `owl-alpha-free` → qwen-plus → qwen-max | public | personal |
| 🛡 `recon` | `glm-5.1` (thinking) → nemotron-super-free → qwen-max | secret | security |
| 🔨 `coder` | `nemotron-super-free` → qwen-coder → qwen-max | internal | coding |
| 🧭 `planner` | `qwen-max` → qwen-plus | internal | personal |

## 🛡 recon — SecOps

Обучение ИБ, threat modeling, hardening **собственной** инфры. Инструмент
`run_security_command` исполняет команды в изолированном sandbox **с сетью**
(nmap/openssl/dig/curl/nc + веб-аудит nuclei/nikto/testssl.sh/httpx). Sensitivity
`secret` — только платные/enterprise-модели, без cloaked.

## 🔨 coder — Coder

Чтение/написание/ревью кода. `run_shell` гоняет тесты/линтеры в sandbox **без сети**
(эксфильтрация невозможна). GitHub-скил: ветки, коммиты, Pull Request — изменения
всегда в feature-ветку + PR на ревью человеку, никогда в основную ветку.

## 💬 assistant — General

Общий помощник: ресёрч, поиск, бытовые вопросы. Sensitivity `public` — впереди
бесплатные модели. Тот же агент стоит за `research-worker` (автономный ресёрч идей
заработка на Deck-доску «Идеи»).

## 🧭 planner — Orchestrator

Работает как тимлид: получает ТЗ/цель проекта и режет на дочерние задачи для
остальных агентов. Сначала показывает план текстом (подзадача = исполнитель +
критерий приёмки), и по подтверждению вызывает `slice_project`, который раскладывает
подзадачи карточками в стек `To Do` доски задач (с меткой исполнителя) — дальше их
подхватывает `deck-worker`.

- Исполнители: `recon` / `coder` / `assistant` (метки `sec` / `code` / `ask`).
- Метки `sec`/`code`/`ask` должны существовать на доске, иначе карточка создаётся без
  метки и уходит агенту по умолчанию.

## Telegram

Один бот = один агент (жёсткая привязка по токену, переключения нет). Токены:
`TELEGRAM_BOT_TOKEN_ASSISTANT` / `_RECON` / `_CODER` / `_PLANNER` (или общий
`TELEGRAM_BOT_TOKEN` → assistant). Доступ — whitelist по числовому `user_id`,
по умолчанию **fail-closed** (пустой список = никого).
