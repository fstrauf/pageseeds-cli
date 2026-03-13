"""Runtime configuration contract for dashboard execution."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class RuntimeConfig:
    """Configurable runtime defaults used by TUI + engine wiring."""

    projects_config_path: Path = Path.home() / ".config" / "automation" / "projects.json"
    automation_dir_name: str = ".github/automation"
    output_root: Path = Path("output")
    required_clis: tuple[str, ...] = field(default_factory=tuple)
    agent_provider: str = "kimi"

