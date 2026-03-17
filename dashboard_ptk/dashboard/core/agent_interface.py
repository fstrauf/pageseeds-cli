"""Legacy compatibility wrapper around the engine AgentRuntime."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Type

from ..engine import AgentRuntime, CopilotAdapter, KimiAdapter, PromptSpec
from .agent_config import AgentConfig, AgentProvider


class AgentInterface(ABC):
    """Abstract interface for AI agents."""

    def __init__(self, config: AgentConfig):
        self.config = config

    @abstractmethod
    def is_available(self) -> bool:
        pass

    @abstractmethod
    def invoke(
        self,
        skill_content: str,
        context: dict,
        instructions: str,
        working_dir: Path,
        timeout: Optional[int] = None,
    ) -> tuple[bool, str]:
        pass

    def _build_prompt(self, skill_content: str, context: dict, instructions: str) -> str:
        return (
            "# SKILL CONTEXT\n"
            "```markdown\n"
            f"{skill_content}\n"
            "```\n\n"
            "# DATA CONTEXT\n"
            "```json\n"
            f"{context}\n"
            "```\n\n"
            "# YOUR TASK\n"
            f"{instructions}\n"
        )


class KimiInterface(AgentInterface):
    """Kimi adapter via engine AgentRuntime."""

    def __init__(self, config: AgentConfig):
        super().__init__(config)
        self.runtime = AgentRuntime(adapter=KimiAdapter())

    def is_available(self) -> bool:
        return self.runtime.adapter.is_available()

    def invoke(
        self,
        skill_content: str,
        context: dict,
        instructions: str,
        working_dir: Path,
        timeout: Optional[int] = None,
    ) -> tuple[bool, str]:
        prompt = self._build_prompt(skill_content, context, instructions)
        result = self.runtime.adapter.run(
            PromptSpec(text=prompt, timeout=timeout or self.config.timeout),
            cwd=working_dir,
        )
        return result.success, result.output_text if result.output_text else (result.error or "")


class CopilotInterface(AgentInterface):
    """GitHub Copilot adapter via GitHub Models inference API."""

    def __init__(self, config: AgentConfig):
        super().__init__(config)
        self.runtime = AgentRuntime(adapter=CopilotAdapter())

    def is_available(self) -> bool:
        return self.runtime.adapter.is_available()

    def invoke(
        self,
        skill_content: str,
        context: dict,
        instructions: str,
        working_dir: Path,
        timeout: Optional[int] = None,
    ) -> tuple[bool, str]:
        prompt = self._build_prompt(skill_content, context, instructions)
        result = self.runtime.adapter.run(
            PromptSpec(text=prompt, timeout=timeout or self.config.timeout),
            cwd=working_dir,
        )
        return result.success, result.output_text if result.output_text else (result.error or "")


class AgentFactory:
    """Factory for creating agent interfaces by provider."""

    _interfaces: dict[AgentProvider, Type[AgentInterface]] = {
        AgentProvider.KIMI: KimiInterface,
        AgentProvider.COPILOT: CopilotInterface,
    }

    @classmethod
    def get_interface(cls, config: AgentConfig) -> AgentInterface:
        interface_class = cls._interfaces.get(config.provider, KimiInterface)
        return interface_class(config)

    @classmethod
    def list_available(cls) -> list[tuple[AgentProvider, bool, str]]:
        results = []
        for provider, interface_class in cls._interfaces.items():
            config = AgentConfig(provider=provider)
            interface = interface_class(config)
            available = interface.is_available()
            label = provider.value
            status = f"✓ Available" if available else f"✗ {label} not available"
            results.append((provider, available, status))
        return results

    @classmethod
    def get_first_available(cls) -> Optional[AgentProvider]:
        for provider, available, _ in cls.list_available():
            if available:
                return provider
        return None
