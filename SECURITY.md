# Security model & disclaimer

AI Combine is a personal, self-hosted tool. It **executes commands and reaches into your
infrastructure** on your behalf. Understand the threat model before using it.

## ⚠️ Disclaimer

- This is a personal project, published as-is (see [LICENSE](LICENSE), no warranty).
- Run it **only on your own infrastructure and against your own targets**. Scanning or
  recon of someone else's systems without permission is illegal. The recon (SecOps)
  agent's prompt restricts this, but the technical boundary is on you.
- The agents call LLMs (some via external/cloaked providers). Don't send sensitive data
  through public/cloaked models. Model choice is tied to `DataSensitivity`
  (PUBLIC/INTERNAL/SECRET) — review the mapping for your case.

## Network access to the orchestrator

- The orchestrator drives agents that hold a **GitHub PAT, RAG and sandbox-broker**
  access — it must not be exposed. In `docker-compose.yml` the port is bound to
  `127.0.0.1:8000` (localhost only); for LAN access put a reverse proxy with TLS and
  authentication in front of it.
- A **mandatory Bearer token** `ORCHESTRATOR_API_TOKEN` is checked on `/chat`, `/agents`,
  `/v1/*` (see `require_token` in `api/routes.py`). The bots and workers use the same
  token; in OpenWebUI it's the connection's "API key". If the token is **unset**,
  enforcement is off (relying on the localhost bind only) and the orchestrator warns
  loudly in the logs at startup. Set the token for production use.

## Privileges and isolation

- **sandbox-broker is the only service with access to `docker.sock`.** That's a
  privilege: compromising the broker = access to Docker/the host. So it is minimal (a
  fixed `{profile, command}` API, allowlist and hardening hardcoded) and its port is not
  published (docker network only). The orchestrator does **not** hold docker.sock — it
  sends commands to the broker over HTTP, so RCE/injection in the orchestrator gives no
  direct host access.
- **Sandbox containers** are ephemeral (`--rm`), non-root (uid 10001), `cap_drop ALL`,
  `no-new-privileges`, read-only rootfs + tmpfs, with mem/cpu/pids limits and a timeout.
  The `coder` profile has no network; `secops` has network (for scanning your own infra).
- **Binary allowlist** (`src/orchestrator/tools/guard.py`) + injection defenses (`$()`,
  backtick, chains to a non-allowlisted binary). Tool output is marked untrusted
  (`wrap_untrusted`) against prompt injection from target responses/notes. The allowlist
  is a **guardrail, not a security boundary**: the real boundary is the sandbox itself
  (ephemeral, no secrets, no network for coder, no docker.sock). The allowlist filters
  the first binary *and* dangerous arguments of allowed binaries that could break out
  into arbitrary execution (`nmap --script`, `nc -e`, `nuclei -code`, `curl file://`);
  interpreters and `awk`/`gawk` (which have `system()`) are deliberately excluded from
  the SecOps profile. Enumerating every escape surface is impossible — don't rely on the
  allowlist as the only line of defense.

## Access and secrets

- **Secrets only in `.env`** (in `.gitignore`; `.env.example` is the template). Never
  commit `.env`.
- **Telegram**: whitelist by numeric user IDs, **fail-closed** by default (empty list =
  nobody). Bootstrap mode (allow everyone) only via an explicit
  `TELEGRAM_ALLOW_BOOTSTRAP=true` for local development.
- **Nextcloud**: use an app password (not your main password), ideally a separate
  read-only account.
- **GitHub skill (coder)**: a PAT scoped to a specific repository.
- `searxng/settings.yml` contains a dev `secret_key` — replace it with your own in
  production.

## Reporting a vulnerability

Open a private security advisory on this repo (Security → Report a vulnerability) or an
issue without sensitive details. This is a hobby project — fixes on a best-effort basis,
no SLA.
