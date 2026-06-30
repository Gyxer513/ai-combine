"""Shared test setup.

On import, agents build their model through the LiteLLM provider, which needs a
non-empty api_key. So tests don't depend on the developer's real `.env`, we inject
dummy values into the environment BEFORE importing `src.orchestrator.config`
(environment variables take priority over .env in pydantic-settings).
"""

from __future__ import annotations

import os

# setdefault: if the developer/CI set real values, don't overwrite them.
os.environ.setdefault("LITELLM_MASTER_KEY", "test-master-key")
os.environ.setdefault("LITELLM_BASE_URL", "http://litellm.test/v1")
# Tests must not write a SQLite file to disk — use a shared in-memory DB.
os.environ.setdefault("DB_PATH", ":memory:")
