# syntax=docker/dockerfile:1
# Изолированный sandbox для bash-исполнения агентами (Этап 6).
# Запускается оркестратором по требованию через docker SDK.
# Гарантии: без сети (или whitelist), RW только /tmp/work, лимиты CPU/RAM,
# без --privileged и без проброса docker.sock.
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        # code: git, ripgrep, jq, python (база уже python:3.12-slim)
        git ca-certificates ripgrep jq unzip \
        # secops: nmap, dns, tls, net
        nmap dnsutils openssl curl netcat-openbsd iputils-ping \
        # nikto (perl-скрипт) — perl + модули: Net::SSLeay (HTTPS), JSON, XML::Writer
        perl libnet-ssleay-perl libjson-perl libxml-writer-perl \
    && rm -rf /var/lib/apt/lists/*

# nuclei (template-сканер CVE/мисконфигов) + httpx (HTTP-проба, фингерпринт техно) —
# статические Go-бинари с релизов ProjectDiscovery (чисто, без ruby/perl-зависимостей).
# Версии запинены (GitHub API без токена rate-limited/flaky); бампать вручную.
ARG NUCLEI_VER=3.8.0
ARG HTTPX_VER=1.9.0
RUN set -eux; \
    for spec in "nuclei:${NUCLEI_VER}" "httpx:${HTTPX_VER}"; do \
        repo=${spec%%:*}; ver=${spec##*:}; \
        curl -fsSL --retry 3 --retry-delay 2 \
            "https://github.com/projectdiscovery/${repo}/releases/download/v${ver}/${repo}_${ver}_linux_amd64.zip" \
            -o /tmp/${repo}.zip; \
        unzip -o /tmp/${repo}.zip ${repo} -d /usr/local/bin; \
        chmod +x /usr/local/bin/${repo}; rm /tmp/${repo}.zip; \
    done

# Шаблоны nuclei пекутся в образ (в рантайме sandbox эфемерный — иначе тянул бы
# каждый раз). Берём детерминированно git-клоном репозитория шаблонов (механика
# `nuclei -update-templates` зависит от конфига/HOME и оказалась флаки).
# Кощей зовёт: nuclei -u <url> -t /opt/nuclei-templates -duc
RUN set -eux; \
    git clone --depth 1 https://github.com/projectdiscovery/nuclei-templates /opt/nuclei-templates; \
    rm -rf /opt/nuclei-templates/.git; \
    chmod -R a+rX /opt/nuclei-templates

# testssl.sh (глубокий TLS-аудит) и nikto (сканер веб-сервера) — репозиториями.
RUN git clone --depth 1 https://github.com/testssl/testssl.sh /opt/testssl \
    && ln -s /opt/testssl/testssl.sh /usr/local/bin/testssl.sh \
    && git clone --depth 1 https://github.com/sullo/nikto /opt/nikto \
    && ln -s /opt/nikto/program/nikto.pl /usr/local/bin/nikto && chmod +x /opt/nikto/program/nikto.pl

# Python-стек для отчётов/презентаций (Левша тестирует офлайн): данные — pandas,
# презентация — python-pptx, БД-логика — против sqlite (stdlib). Ставится на этапе
# сборки образа; в рантайме sandbox сети не имеет.
RUN pip install --no-cache-dir pandas python-pptx openpyxl

# Непривилегированный пользователь
RUN useradd -m -u 10001 sandbox
USER sandbox
WORKDIR /tmp/work

CMD ["sleep", "infinity"]
