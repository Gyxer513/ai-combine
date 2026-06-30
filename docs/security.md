# Security

AI Combine **executes commands and reaches into your infrastructure** on your behalf.
Understand the threat model before using it. The canonical source is
[`SECURITY.md`](https://github.com/Gyxer513/ai-combine/blob/main/SECURITY.md) in the repo.

!!! danger "Disclaimer"
    Run it only on your own infrastructure and against your own targets. Scanning other
    people's systems without permission is illegal. The `recon` prompt restricts this, but
    the technical boundary is on you.

## Orchestrator access

- The port is bound to `127.0.0.1:8000` (localhost only): the agents hold a GitHub PAT,
  RAG and sandbox-broker access, so it must not be exposed. For LAN — a reverse proxy with
  TLS+auth.
- A **mandatory Bearer token** `ORCHESTRATOR_API_TOKEN` is checked on `/chat`, `/agents`,
  `/v1/*`. The bots and workers use the same token; in OpenWebUI it's the connection's
  "API key". Empty = enforcement off (localhost bind only); the orchestrator warns loudly
  in the logs at startup.

## Privileges and isolation

- **sandbox-broker is the only service with `docker.sock`.** Minimal, port not published.
  The orchestrator has no docker.sock — RCE in it gives no direct host access.
- **Sandbox containers** are ephemeral (`--rm`), non-root, `cap_drop ALL`,
  `no-new-privileges`, read-only rootfs + tmpfs, mem/cpu/pids limits and a timeout. The
  `coder` profile has no network; `secops` has network.
- **Binary allowlist** + injection defenses (`$()`, backtick, chains). This is a
  **guardrail, not a security boundary** — the real boundary is the sandbox itself. The
  allowlist filters the first binary *and* dangerous arguments (`nmap --script`, `nc -e`,
  `nuclei -code`, `curl file://`); interpreters and `awk`/`gawk` are deliberately excluded
  from the SecOps profile. Tool output is marked untrusted (`wrap_untrusted`) against
  prompt injection from target responses and notes.

## Secrets

- **Only in `.env`** (in `.gitignore`; `.env.example` is the template). Never commit it.
- **Telegram**: whitelist by numeric `user_id`, fail-closed by default.
- **Nextcloud**: an app password (not the main one), ideally a separate read-only account.
- **GitHub skill**: a PAT scoped to a specific repository.

## Reporting a vulnerability

A private security advisory on GitHub (Security → Report a vulnerability) or an issue
without sensitive details. It's a hobby project — fixes on a best-effort basis, no SLA.
