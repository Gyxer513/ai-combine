"""Sandbox-broker: the only service with access to docker.sock.

Compresses the privilege (spawning containers) down to a tiny, auditable surface
with no LLM/injection logic. The orchestrator talks to it over HTTP with a minimal
API {profile, command} — the client cannot set the hardening parameters or allowlist.
"""
