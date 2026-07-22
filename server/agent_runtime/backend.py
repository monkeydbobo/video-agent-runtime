"""Agent runtime backend selection."""

from __future__ import annotations

import os
from typing import Literal

AgentBackend = Literal["local", "managed", "e2b", "disabled"]


def agent_runtime_backend() -> AgentBackend:
    """Select E2B automatically on Railway, local SDK elsewhere."""
    configured = os.environ.get("ARCREEL_AGENT_BACKEND", "").strip().lower()
    if configured in {"local", "managed", "e2b", "disabled"}:
        return configured  # type: ignore[return-value]
    legacy = os.environ.get("ARCREEL_AGENT_RUNTIME_ENABLED", "").strip().lower()
    if legacy in {"false", "0", "no", "off"}:
        return "disabled"
    if any(os.environ.get(key) for key in ("RAILWAY_ENVIRONMENT", "RAILWAY_PROJECT_ID", "RAILWAY_SERVICE_ID")):
        return "e2b"
    return "local"
