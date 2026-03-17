"""Dashboard execution engine package."""

from .agent_runtime import AgentRuntime, CopilotAdapter, KimiAdapter
from .env_resolver import EnvResolver
from .executor import ExecutionEngine, execution_context_for
from .history_paths import resolve_reddit_history_path
from .orchestrator import OrchestrationRunResult, OrchestratorService
from .policy import OrchestrationPolicy, PolicyContext, PolicyDecision, PolicyEngine
from .migration import migrate_file_in_place, migrate_state_data
from .normalizers import NormalizerRegistry
from .preflight import PreflightFinding, ProjectPreflight, ProjectPreflightReport
from .runtime_config import RuntimeConfig
from .task_store import TaskStore
from .tool_registry import ToolRegistry
from .types import (
    AgentRawResult,
    ExecutionContext,
    NormalizedResult,
    PromptSpec,
    SchedulerConfig,
    SchedulerRule,
    SchedulerState,
    SchedulerStats,
    RuleState,
    TaskRecord,
    TaskState,
    ToolResult,
    WorkflowStep,
)

__all__ = [
    "AgentRuntime",
    "AgentRawResult",
    "ExecutionContext",
    "ExecutionEngine",
    "EnvResolver",
    "CopilotAdapter",
    "KimiAdapter",
    "NormalizedResult",
    "NormalizerRegistry",
    "OrchestrationPolicy",
    "OrchestrationRunResult",
    "OrchestratorService",
    "PolicyContext",
    "PolicyDecision",
    "PolicyEngine",
    "PromptSpec",
    "PreflightFinding",
    "ProjectPreflight",
    "ProjectPreflightReport",
    "resolve_reddit_history_path",
    "RuntimeConfig",
    "RuleState",
    "SchedulerConfig",
    "SchedulerRule",
    "SchedulerState",
    "SchedulerStats",
    "TaskRecord",
    "TaskState",
    "TaskStore",
    "ToolRegistry",
    "ToolResult",
    "WorkflowStep",
    "execution_context_for",
    "migrate_file_in_place",
    "migrate_state_data",
]
