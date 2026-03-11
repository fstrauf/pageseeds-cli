"""Workflow handler abstractions."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from ..types import StepResult, WorkflowStep


@dataclass
class RuntimeServices:
    """Services available to workflow handlers during execution."""

    runners: dict[str, Any]


class WorkflowHandler(ABC):
    """Task workflow contract."""

    @abstractmethod
    def supports(self, task: Any) -> bool:
        """Return True when handler can execute the task."""

    @abstractmethod
    def plan(self, task: Any) -> list[WorkflowStep]:
        """Return explicit workflow step graph."""

    @abstractmethod
    def execute(self, step: WorkflowStep, task: Any, services: RuntimeServices) -> StepResult:
        """Execute one planned step."""
