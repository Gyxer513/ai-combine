"""Typed settings from the environment (pydantic-settings)."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Single source of configuration. Read from .env and environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LiteLLM proxy ---
    litellm_base_url: str = Field(default="http://litellm:4000/v1")
    litellm_master_key: str = Field(default="sk-litellm-change-me")

    # --- Orchestrator authentication ---
    # Bearer token on /chat, /agents, /v1/* (agents have access to GitHub PAT/RAG/
    # sandbox-broker — without a token anyone with port access can invoke an agent). Empty
    # means NOT enforced (we rely on bind localhost), but the orchestrator warns loudly.
    # In OpenWebUI this token is set as the connection's "API key".
    orchestrator_api_token: str = Field(default="")

    # --- Persistence (SQLite) ---
    # The file survives restarts: conversation history, notes, metrics. ":memory:" in tests.
    db_path: str = Field(default="data/ai_combine.db")

    # --- Vector store / embeddings (via API, no local TEI) ---
    qdrant_url: str = Field(default="http://qdrant:6333")
    embed_model: str = Field(default="embed")  # model name in LiteLLM (text-embedding-v4)
    embed_dim: int = Field(default=1024)

    # --- Conversation history ---
    # Token budget for history before a model request (instructions counted separately).
    # Beyond it, early messages are collapsed (see agents/history.py).
    history_max_tokens: int = Field(default=12000)

    # --- RAG ---
    rag_top_k: int = Field(default=5)
    rag_chunk_tokens: int = Field(default=512)
    rag_chunk_overlap: int = Field(default=64)
    # Notes: which categories map to which namespace (CSV "Category:namespace").
    # Unmapped categories fall into rag_notes_default_ns.
    rag_notes_category_map: str = Field(default="")
    rag_notes_default_ns: str = Field(default="personal")
    # WebDAV: which folders map to which namespace (CSV "/path:namespace").
    rag_webdav_folders: str = Field(default="")
    # Auto-indexing interval in minutes: >0 — indexer runs in a loop, 0 — a single pass.
    rag_index_interval_min: int = Field(default=0)

    # --- Docs semantic search (local, offline) ---
    # A small local semantic index over the combine's OWN Markdown docs, separate from
    # the Nextcloud RAG above. EmbeddingGemma-300m (int8) via ONNX Runtime + FAISS — no
    # torch, no API, ~0.4-0.7 GB resident when loaded. Opt-in: needs the `docs` extra
    # installed AND a built index (python -m src.docs_search.index); otherwise the
    # search_docs tool degrades to a friendly "index not built" message.
    docs_search_enabled: bool = Field(default=False)
    docs_model_repo: str = Field(default="onnx-community/embeddinggemma-300m-ONNX")
    docs_model_file: str = Field(default="onnx/model_quantized.onnx")  # int8/quantized
    docs_tokenizer_file: str = Field(default="tokenizer.json")
    docs_model_dim: int = Field(default=768)  # full dim; Matryoshka could truncate lower
    docs_model_cache: str = Field(default="data/models")  # HF download cache (volume)
    docs_index_dir: str = Field(default="data/docs_index")  # faiss index + metadata
    docs_chunk_chars: int = Field(default=1200)  # chars per chunk
    docs_chunk_overlap: int = Field(default=200)
    docs_top_k: int = Field(default=5)
    # Which Markdown files make up the corpus (CSV of globs, relative to repo root).
    docs_globs: str = Field(default="README.md,README.ru.md,SECURITY.md,docs/**/*.md")
    # EmbeddingGemma prompt prefixes (recommended by the model card for retrieval).
    docs_query_prefix: str = Field(default="task: search result | query: ")
    docs_doc_prefix: str = Field(default="title: none | text: ")
    # Optional HF token if the model repo is gated.
    hf_token: str = Field(default="")

    # --- Sandbox (Stage 6: isolated command execution) ---
    # The orchestrator does NOT have docker.sock — it talks to the sandbox-broker over HTTP.
    # docker.sock is only on the broker; the broker reads the parameters below.
    broker_url: str = Field(default="http://sandbox-broker:9000")
    sandbox_image: str = Field(default="ai-combine/sandbox:latest")
    sandbox_mem: str = Field(default="512m")
    sandbox_cpus: float = Field(default=1.0)
    sandbox_pids: int = Field(default=256)
    sandbox_timeout_sec: int = Field(default=300)  # scans (nuclei/nikto) run for minutes
    sandbox_output_limit: int = Field(default=8000)  # chars of output in the model's reply

    # --- Web search (SearXNG, self-hosted) ---
    searxng_url: str = Field(default="http://searxng:8080")

    # --- Telegram (Stage 5) ---
    # One bot per agent: each bot is firmly tied to an agent by its own token.
    # telegram_bot_token (shared) → assistant by default (backward compatibility);
    # separate bots are created in @BotFather, tokens below.
    telegram_bot_token: str = Field(default="")
    telegram_bot_token_assistant: str = Field(default="")
    telegram_bot_token_recon: str = Field(default="")
    telegram_bot_token_coder: str = Field(default="")
    telegram_bot_token_planner: str = Field(default="")
    telegram_allowed_users: str = Field(default="")
    # Fail-closed: with an empty whitelist we let NOBODY in by default (denied ids are
    # written to the log — find yours and add it). Open bootstrap mode (let everyone in
    # when the list is empty) is only enabled via an explicit TELEGRAM_ALLOW_BOOTSTRAP=true
    # for dev.
    telegram_allow_bootstrap: bool = Field(default=False)
    # Where the bot goes for agent replies (in docker — the service name).
    orchestrator_url: str = Field(default="http://orchestrator:8000")
    # How long the bot waits for an agent reply (seconds). recon with a series of scans can
    # run for several minutes — a short timeout gives a false "orchestrator unavailable".
    telegram_reply_timeout_sec: int = Field(default=600)

    # --- Nextcloud (Stage 3) ---
    nextcloud_url: str = Field(default="")
    nextcloud_user: str = Field(default="")
    nextcloud_app_password: str = Field(default="")

    # --- Deck-worker (autonomy): tasks from Nextcloud Deck ---
    deck_board: str = Field(default="AI Combine Tasks")  # must match your Nextcloud board name
    deck_todo_stack: str = Field(default="To Do")
    deck_doing_stack: str = Field(default="In Progress")
    deck_done_stack: str = Field(default="Done")
    # Where a card moves on an execution error (NOT to Done — otherwise the board lies about
    # success and there's no retry). If the stack isn't on the board, the card stays in
    # In Progress (visibly stuck) rather than moving to Done.
    deck_failed_stack: str = Field(default="Failed")
    # Card label -> agent (CSV "label:agent"). No label -> deck_default_agent.
    deck_label_agent_map: str = Field(default="sec:recon,code:coder,ask:assistant")
    deck_default_agent: str = Field(default="assistant")
    # Board polling interval in minutes: >0 — loop, 0 — a single pass.
    deck_poll_interval_min: int = Field(default=0)

    # --- Research-worker (assistant: regular money-making research) ---
    # Token-bounded: deterministic search + ONE cheap LLM call per run.
    research_board: str = Field(default="Ideas")
    research_stack: str = Field(default="New")  # stack for new idea cards
    research_model: str = Field(default="qwen-flash")  # cheap + private (Alibaba)
    research_ideas_per_run: int = Field(default=2)
    research_searches_per_run: int = Field(default=3)
    research_max_tokens: int = Field(default=900)  # cap on LLM output
    research_interval_min: int = Field(default=0)  # 0 — a single pass; 1440 — once a day
    # Theme angles to rotate through (by date). CSV.
    research_themes: str = Field(
        default=(
            "business process automation,no-code/low-code SaaS,"
            "AI services and assistants,data scraping and arbitrage,"
            "content and info products,b2b microservices,Telegram bots and automation"
        )
    )

    # --- Gitea (Stage 6) ---
    gitea_url: str = Field(default="")
    gitea_token: str = Field(default="")

    # --- GitHub (coder: repositories; bridge for the homelab) ---
    # coder on the homelab pushes to GitHub (the work GitLab behind VPN isn't reliably
    # reachable); GitHub↔GitLab sync is done manually by a human. PAT scoped to the repo.
    github_api_url: str = Field(default="https://api.github.com")
    github_token: str = Field(default="")
    github_repo: str = Field(default="")  # "owner/name"
    github_default_branch: str = Field(default="main")

    @property
    def notes_category_map(self) -> dict[str, str]:
        """'AI Projects:personal, Security:security' -> {'AI Projects': 'personal', ...}."""
        out: dict[str, str] = {}
        for pair in self.rag_notes_category_map.split(","):
            cat, _, ns = pair.partition(":")
            if cat.strip() and ns.strip():
                out[cat.strip()] = ns.strip()
        return out

    @property
    def webdav_folders(self) -> list[tuple[str, str]]:
        """'/Knowledge/Security:security' -> [('/Knowledge/Security', 'security'), ...]."""
        out: list[tuple[str, str]] = []
        for pair in self.rag_webdav_folders.split(","):
            path, _, ns = pair.rpartition(":")
            if path.strip() and ns.strip():
                out.append((path.strip(), ns.strip()))
        return out

    @property
    def deck_label_agents(self) -> dict[str, str]:
        """'sec:recon,code:coder' -> {'sec': 'recon', ...} (label lowercased)."""
        out: dict[str, str] = {}
        for pair in self.deck_label_agent_map.split(","):
            label, _, agent = pair.partition(":")
            if label.strip() and agent.strip():
                out[label.strip().lower()] = agent.strip()
        return out

    @property
    def research_theme_list(self) -> list[str]:
        """Research themes from CSV (non-empty, trimmed of surrounding whitespace)."""
        return [t.strip() for t in self.research_themes.split(",") if t.strip()]

    @property
    def agent_bot_tokens(self) -> dict[str, str]:
        """{agent_name: bot_token} for agents that have a token set.

        assistant takes telegram_bot_token_assistant or the shared telegram_bot_token.
        Only agents with a non-empty token are polled — you can run just a single bot.
        """
        out: dict[str, str] = {}
        assistant = self.telegram_bot_token_assistant or self.telegram_bot_token
        if assistant:
            out["assistant"] = assistant
        if self.telegram_bot_token_recon:
            out["recon"] = self.telegram_bot_token_recon
        if self.telegram_bot_token_coder:
            out["coder"] = self.telegram_bot_token_coder
        if self.telegram_bot_token_planner:
            out["planner"] = self.telegram_bot_token_planner
        return out

    @property
    def allowed_user_ids(self) -> set[int]:
        """Whitelist of Telegram user_ids from a '123,456' string.

        Non-numeric values (e.g. @username) are ignored — a numeric id is required
        (see @userinfobot). An empty result -> fail-closed (nobody), unless
        telegram_allow_bootstrap is enabled.
        """
        ids: set[int] = set()
        for token in self.telegram_allowed_users.split(","):
            token = token.strip()
            if token.isdigit():
                ids.add(int(token))
        return ids


settings = Settings()
