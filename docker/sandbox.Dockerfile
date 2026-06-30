# syntax=docker/dockerfile:1
# Isolated sandbox for bash execution by the agents (Stage 6).
# Started on demand by the orchestrator via the docker SDK.
# Guarantees: no network (or a whitelist), RW only on /tmp/work, CPU/RAM limits,
# no --privileged and no docker.sock passthrough.
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        # code: git, ripgrep, jq, python (the base is already python:3.12-slim)
        git ca-certificates ripgrep jq unzip \
        # secops: nmap, dns, tls, net
        nmap dnsutils openssl curl netcat-openbsd iputils-ping \
        # nikto (perl script) — perl + modules: Net::SSLeay (HTTPS), JSON, XML::Writer
        perl libnet-ssleay-perl libjson-perl libxml-writer-perl \
    && rm -rf /var/lib/apt/lists/*

# nuclei (template scanner for CVEs/misconfigs) + httpx (HTTP probe, tech fingerprinting) —
# static Go binaries from ProjectDiscovery releases (clean, no ruby/perl dependencies).
# Versions are pinned (the GitHub API without a token is rate-limited/flaky); bump manually.
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

# nuclei templates are baked into the image (at runtime the sandbox is ephemeral —
# otherwise it would download them every time). We fetch them deterministically by
# git-cloning the templates repo (the `nuclei -update-templates` mechanism depends on
# config/HOME and turned out to be flaky).
# Invoked as: nuclei -u <url> -t /opt/nuclei-templates -duc
RUN set -eux; \
    git clone --depth 1 https://github.com/projectdiscovery/nuclei-templates /opt/nuclei-templates; \
    rm -rf /opt/nuclei-templates/.git; \
    chmod -R a+rX /opt/nuclei-templates

# testssl.sh (deep TLS audit) and nikto (web server scanner) — from their repos.
RUN git clone --depth 1 https://github.com/testssl/testssl.sh /opt/testssl \
    && ln -s /opt/testssl/testssl.sh /usr/local/bin/testssl.sh \
    && git clone --depth 1 https://github.com/sullo/nikto /opt/nikto \
    && ln -s /opt/nikto/program/nikto.pl /usr/local/bin/nikto && chmod +x /opt/nikto/program/nikto.pl

# Python stack for reports/presentations (tested offline): data — pandas,
# presentations — python-pptx, DB logic — against sqlite (stdlib). Installed at image
# build time; at runtime the sandbox has no network.
RUN pip install --no-cache-dir pandas python-pptx openpyxl

# Unprivileged user
RUN useradd -m -u 10001 sandbox
USER sandbox
WORKDIR /tmp/work

CMD ["sleep", "infinity"]
