# syntax=docker/dockerfile:1
# Изолированный sandbox для bash-исполнения агентами (Этап 6).
# Запускается оркестратором по требованию через docker SDK.
# Гарантии: без сети (или whitelist), RW только /tmp/work, лимиты CPU/RAM,
# без --privileged и без проброса docker.sock.
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        # code: git, ripgrep, jq, python (база уже python:3.12-slim)
        git ca-certificates ripgrep jq \
        # secops: nmap, dns, tls, net
        nmap dnsutils openssl curl netcat-openbsd iputils-ping \
    && rm -rf /var/lib/apt/lists/*

# Python-стек для отчётов/презентаций (Левша тестирует офлайн): данные — pandas,
# презентация — python-pptx, БД-логика — против sqlite (stdlib). Ставится на этапе
# сборки образа; в рантайме sandbox сети не имеет.
RUN pip install --no-cache-dir pandas python-pptx openpyxl

# Непривилегированный пользователь
RUN useradd -m -u 10001 sandbox
USER sandbox
WORKDIR /tmp/work

CMD ["sleep", "infinity"]
