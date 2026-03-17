"""Core engine types for task execution and persistence."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

TaskStatus = Literal["todo", "in_progress", "review", "done", "cancelled"]
StepKind = Literal["deterministic", "agentic", "workflow", "manual"]


@dataclass
class ArtifactRef:
    """Typed reference to a task artifact."""

    key: str
    path: str
    type: str = "json"
    source: str = "task"

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "path": self.path,
            "type": self.type,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ArtifactRef":
        return cls(
            key=str(data.get("key", "artifact")),
            path=str(data.get("path", "")),
            type=str(data.get("type", "json")),
            source=str(data.get("source", "task")),
        )


@dataclass
class RunMetadata:
    """Execution metadata tracked per task."""

    attempts: int = 0
    last_error: str | None = None
    provider: str | None = None
    started_at: str | None = None
    completed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempts": self.attempts,
            "last_error": self.last_error,
            "provider": self.provider,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "RunMetadata":
        payload = data or {}
        return cls(
            attempts=int(payload.get("attempts", 0) or 0),
            last_error=payload.get("last_error"),
            provider=payload.get("provider"),
            started_at=payload.get("started_at"),
            completed_at=payload.get("completed_at"),
        )


@dataclass
class TaskRecord:
    """Schema-v4 compatible task payload."""

    id: str
    type: str
    title: str
    phase: str
    status: TaskStatus
    priority: str = "medium"
    depends_on: list[str] = field(default_factory=list)
    spawns_tasks: list[str] = field(default_factory=list)
    parent_task: str | None = None
    workflow_key: str | None = None
    execution_mode: str = "manual"
    agent_policy: str = "optional"
    artifacts: list[ArtifactRef] = field(default_factory=list)
    run: RunMetadata = field(default_factory=RunMetadata)
    metadata: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        base = {
            "id": self.id,
            "type": self.type,
            "title": self.title,
            "phase": self.phase,
            "status": self.status,
            "priority": self.priority,
            "depends_on": self.depends_on,
            "spawns_tasks": self.spawns_tasks,
            "parent_task": self.parent_task,
            "workflow_key": self.workflow_key or self.type,
            "execution_mode": self.execution_mode,
            "agent_policy": self.agent_policy,
            "artifacts": [a.to_dict() for a in self.artifacts],
            "run": self.run.to_dict(),
            "metadata": self.metadata,
        }
        for key, value in self.raw.items():
            if key not in base:
                base[key] = value
        return base

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskRecord":
        depends = data.get("depends_on", [])
        if isinstance(depends, str):
            depends = [depends]
        elif not isinstance(depends, list):
            depends = []

        artifacts_payload = data.get("artifacts", [])
        artifacts: list[ArtifactRef] = []
        if isinstance(artifacts_payload, list):
            artifacts = [ArtifactRef.from_dict(a) for a in artifacts_payload if isinstance(a, dict)]

        known = {
            "id",
            "type",
            "title",
            "phase",
            "status",
            "priority",
            "depends_on",
            "spawns_tasks",
            "parent_task",
            "workflow_key",
            "execution_mode",
            "agent_policy",
            "artifacts",
            "run",
            "metadata",
        }

        return cls(
            id=str(data.get("id", "")),
            type=str(data.get("type", "")),
            title=str(data.get("title", "Untitled")),
            phase=str(data.get("phase", "implementation")),
            status=str(data.get("status", "todo")),
            priority=str(data.get("priority", "medium")),
            depends_on=[str(dep) for dep in depends if dep],
            spawns_tasks=[str(task_id) for task_id in data.get("spawns_tasks", []) if task_id],
            parent_task=data.get("parent_task"),
            workflow_key=data.get("workflow_key") or data.get("type"),
            execution_mode=str(data.get("execution_mode", "manual")),
            agent_policy=str(data.get("agent_policy", "optional")),
            artifacts=artifacts,
            run=RunMetadata.from_dict(data.get("run")),
            metadata=data.get("metadata", {}) if isinstance(data.get("metadata"), dict) else {},
            raw={k: v for k, v in data.items() if k not in known},
        )


@dataclass
class TaskState:
    """Top-level state object for task_list.json."""

    schema_version: int = 4
    version: str = "4.0"
    project_id: str = ""
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())
    tasks: list[TaskRecord] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "version": self.version,
            "project_id": self.project_id,
            "last_updated": self.last_updated,
            "tasks": [task.to_dict() for task in self.tasks],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskState":
        return cls(
            schema_version=int(data.get("schema_version", 4) or 4),
            version=str(data.get("version", "4.0")),
            project_id=str(data.get("project_id", "")),
            last_updated=str(data.get("last_updated", datetime.now().isoformat())),
            tasks=[TaskRecord.from_dict(item) for item in data.get("tasks", []) if isinstance(item, dict)],
            metadata=data.get("metadata", {}) if isinstance(data.get("metadata"), dict) else {},
        )


@dataclass
class ExecutionContext:
    """Runtime context for tool and agent execution."""

    repo_root: Path
    task_id: str | None = None
    task_results_dir: Path | None = None


@dataclass
class ToolResult:
    """Result of deterministic CLI command execution."""

    success: bool
    command: list[str]
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0
    error_type: str | None = None


@dataclass
class PromptSpec:
    """Agent prompt descriptor.

    mode: 'text'  — agent produces plain text output only; no file/shell tools needed.
           'agent' — agent may read/write files and run shell commands (default).
    """

    text: str
    timeout: int = 600
    output_filename: str = "agent_output.md"
    mode: str = "agent"  # 'text' | 'agent'


@dataclass
class AgentRawResult:
    """Raw agent output, always persisted on disk when available."""

    success: bool
    provider: str
    output_text: str = ""
    output_path: str | None = None
    error: str | None = None


@dataclass
class NormalizedResult:
    """Result of deterministic normalization stage."""

    success: bool
    payload: dict[str, Any] | None = None
    output_path: str | None = None
    error: str | None = None


@dataclass
class WorkflowStep:
    """Single workflow step in a task execution graph."""

    name: str
    kind: StepKind
    handler: str
    params: dict[str, Any] = field(default_factory=dict)
    optional: bool = False


@dataclass
class StepResult:
    """Execution result for a workflow step."""

    success: bool
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)


class EngineError(Exception):
    """Base engine error."""


class MigrationError(EngineError):
    """Raised when state migration fails."""


class ToolExecutionError(EngineError):
    """Raised when tool execution fails irrecoverably."""


class NormalizationError(EngineError):
    """Raised when normalization fails."""


# =============================================================================
# Scheduler Types
# =============================================================================

SchedulerRuleMode = Literal["create_task", "reminder_only"]
SchedulerRuleStatus = Literal["due", "created", "reminded", "skipped", "error"]


@dataclass
class SchedulerRule:
    """Single scheduler rule configuration."""

    id: str
    task_type: str
    mode: SchedulerRuleMode
    cadence_hours: int
    priority: str = "medium"
    phase: str = "collection"
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task_type": self.task_type,
            "mode": self.mode,
            "cadence_hours": self.cadence_hours,
            "priority": self.priority,
            "phase": self.phase,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SchedulerRule":
        return cls(
            id=str(data.get("id", "")),
            task_type=str(data.get("task_type", "")),
            mode=str(data.get("mode", "create_task")),  # type: ignore
            cadence_hours=int(data.get("cadence_hours", 168) or 168),
            priority=str(data.get("priority", "medium")),
            phase=str(data.get("phase", "collection")),
            enabled=bool(data.get("enabled", True)),
        )


@dataclass
class SchedulerConfig:
    """Scheduler configuration loaded from orchestrator_policy.json."""

    enabled: bool = True
    timezone: str = ""
    max_task_creations_per_cycle: int = 3
    quiet_hours_start: str = "22:00"
    quiet_hours_end: str = "07:00"
    overdue_warn_after_hours: int = 48
    overdue_error_after_hours: int = 168
    rules: list[SchedulerRule] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "timezone": self.timezone,
            "max_task_creations_per_cycle": self.max_task_creations_per_cycle,
            "quiet_hours_start": self.quiet_hours_start,
            "quiet_hours_end": self.quiet_hours_end,
            "overdue_warn_after_hours": self.overdue_warn_after_hours,
            "overdue_error_after_hours": self.overdue_error_after_hours,
            "rules": [r.to_dict() for r in self.rules],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "SchedulerConfig":
        if not data:
            return cls.default()

        rules_data = data.get("rules", [])
        rules = []
        if isinstance(rules_data, list):
            rules = [SchedulerRule.from_dict(r) for r in rules_data if isinstance(r, dict)]

        return cls(
            enabled=bool(data.get("enabled", True)),
            timezone=str(data.get("timezone", "")),
            max_task_creations_per_cycle=int(data.get("max_task_creations_per_cycle", 3) or 3),
            quiet_hours_start=str(data.get("quiet_hours_start", "22:00")),
            quiet_hours_end=str(data.get("quiet_hours_end", "07:00")),
            overdue_warn_after_hours=int(data.get("overdue_warn_after_hours", 48) or 48),
            overdue_error_after_hours=int(data.get("overdue_error_after_hours", 168) or 168),
            rules=rules,
        )

    @classmethod
    def default(cls) -> "SchedulerConfig":
        """Return default scheduler config with built-in rules."""
        return cls(
            enabled=True,
            timezone="",
            max_task_creations_per_cycle=3,
            quiet_hours_start="22:00",
            quiet_hours_end="07:00",
            overdue_warn_after_hours=48,
            overdue_error_after_hours=168,
            rules=[
                SchedulerRule("collect_gsc_weekly", "collect_gsc", "create_task", 168, "medium", "collection"),
                SchedulerRule("collect_posthog_weekly", "collect_posthog", "create_task", 168, "medium", "collection"),
                SchedulerRule("reddit_opportunity_search", "reddit_opportunity_search", "create_task", 48, "medium", "research"),
                SchedulerRule("research_keywords", "research_keywords", "reminder_only", 336, "medium", "research"),
                SchedulerRule("indexing_diagnostics", "indexing_diagnostics", "reminder_only", 168, "medium", "verification"),
            ],
        )


@dataclass
class RuleState:
    """Per-rule state tracked in scheduler_state.json."""

    last_due_at: str | None = None
    last_task_created_at: str | None = None
    last_reminder_at: str | None = None
    last_status: SchedulerRuleStatus = "skipped"
    last_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "last_due_at": self.last_due_at,
            "last_task_created_at": self.last_task_created_at,
            "last_reminder_at": self.last_reminder_at,
            "last_status": self.last_status,
            "last_message": self.last_message,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RuleState":
        return cls(
            last_due_at=data.get("last_due_at"),
            last_task_created_at=data.get("last_task_created_at"),
            last_reminder_at=data.get("last_reminder_at"),
            last_status=str(data.get("last_status", "skipped")),  # type: ignore
            last_message=str(data.get("last_message", "")),
        )


@dataclass
class SchedulerStats:
    """Scheduler statistics tracked in scheduler_state.json."""

    cycles: int = 0
    tasks_created: int = 0
    orchestrator_runs: int = 0
    reminders_emitted: int = 0
    errors: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycles": self.cycles,
            "tasks_created": self.tasks_created,
            "orchestrator_runs": self.orchestrator_runs,
            "reminders_emitted": self.reminders_emitted,
            "errors": self.errors,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SchedulerStats":
        return cls(
            cycles=int(data.get("cycles", 0) or 0),
            tasks_created=int(data.get("tasks_created", 0) or 0),
            orchestrator_runs=int(data.get("orchestrator_runs", 0) or 0),
            reminders_emitted=int(data.get("reminders_emitted", 0) or 0),
            errors=int(data.get("errors", 0) or 0),
        )


@dataclass
class SchedulerState:
    """Per-project scheduler state persisted in scheduler_state.json."""

    schema_version: int = 1
    last_cycle_started_at: str | None = None
    last_cycle_finished_at: str | None = None
    rules: dict[str, RuleState] = field(default_factory=dict)
    stats: SchedulerStats = field(default_factory=SchedulerStats)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "last_cycle_started_at": self.last_cycle_started_at,
            "last_cycle_finished_at": self.last_cycle_finished_at,
            "rules": {k: v.to_dict() for k, v in self.rules.items()},
            "stats": self.stats.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SchedulerState":
        rules_data = data.get("rules", {})
        rules = {}
        if isinstance(rules_data, dict):
            rules = {k: RuleState.from_dict(v) for k, v in rules_data.items() if isinstance(v, dict)}

        return cls(
            schema_version=int(data.get("schema_version", 1) or 1),
            last_cycle_started_at=data.get("last_cycle_started_at"),
            last_cycle_finished_at=data.get("last_cycle_finished_at"),
            rules=rules,
            stats=SchedulerStats.from_dict(data.get("stats", {})),
        )
