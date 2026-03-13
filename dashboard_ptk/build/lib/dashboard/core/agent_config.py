"""Legacy compatibility config for agent runtime.

The canonical execution path is dashboard.engine.agent_runtime (Kimi v1).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class AgentProvider(Enum):
    """Supported providers in v1."""

    KIMI = "kimi"

    @classmethod
    def from_string(cls, value: str) -> "AgentProvider":
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
        return cls(provider=AgentProvider.KIMI)

    def save(self, config_dir: Optional[Path] = None):
        # Compatibility no-op; v1 runtime does not use per-provider config files.
        return None

    def get_required_env_var(self) -> Optional[str]:
        return None
