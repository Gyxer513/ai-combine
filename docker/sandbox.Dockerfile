# syntax=docker/dockerfile:1
# Изолированный sandbox для bash-исполнения агентами (Этап 6).
# Запускается оркестратором по требованию через docker SDK.
# Гарантии: без сети (или whitelist), RW только /tmp/work, лимиты CPU/RAM,
# без --privileged и без проброса docker.sock.
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git curl ca-certificates ripgrep jq \
    && rm -rf /var/lib/apt/lists/*

# Непривилегированный пользователь
RUN useradd -m -u 10001 sandbox
USER sandbox
WORKDIR /tmp/work

CMD ["sleep", "infinity"]
