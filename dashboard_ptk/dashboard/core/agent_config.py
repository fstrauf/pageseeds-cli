"""Legacy compatibility config for agent runtime.

The canonical execution path is dashboard.engine.agent_runtime.
Provider is controlled via the AGENT_PROVIDER environment variable
(values: ``kimi`` | ``copilot``).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class AgentProvider(Enum):
    """Supported agent providers."""

    KIMI = "kimi"
    COPILOT = "copilot"

    @classmethod
    def from_string(cls, value: str) -> "AgentProvider":
        normalized = value.lower().strip()
        for member in cls:
            if member.value == normalized:
                return member
        return cls.KIMI


@dataclass
class AgentConfig:
    """Compatibility config object."""

    provider: AgentProvider = AgentProvider.KIMI
    api_key: Optional[str] = None
    model: Optional[str] = None
    timeout: int = 600

    @classmethod
    def load(cls, config_dir: Optional[Path] = None) -> "AgentConfig":
        raw = os.environ.get("AGENT_PROVIDER", "kimi")
        provider = AgentProvider.from_string(raw)
        return cls(provider=provider)

    def save(self, config_dir: Optional[Path] = None):
        # Compatibility no-op; runtime is driven by AGENT_PROVIDER env var.
        return None

    def get_required_env_var(self) -> Optional[str]:
        if self.provider == AgentProvider.COPILOT:
            return None  # uses gh CLI token — no separate env var needed
        return None
