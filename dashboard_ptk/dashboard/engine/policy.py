"""Policy contracts for orchestration runs."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .types import SchedulerConfig


@dataclass
class OrchestrationPolicy:
    """Policy config loaded from .github/automation/orchestrator_policy.json."""

    schema_version: int = 1
    max_steps_per_run: int = 8
    max_failures_per_run: int = 2
    max_runtime_minutes: int = 30  # Safety limit - abort after 30 minutes
    allow_modes: list[str] = field(default_factory=lambda: ["automatic", "batchable"])
    blocked_task_types: list[str] = field(
        default_factory=lambda: ["research_keywords", "custom_keyword_research"]
    )
    allowed_task_types: list[str] = field(default_factory=list)
    reddit_autopost_enabled: bool = False
    reddit_max_posts_per_day: int = 4
    reddit_max_posts_per_week: int = 12
    stop_on_policy_block: bool = False
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig.default)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "max_steps_per_run": self.max_steps_per_run,
            "max_failures_per_run": self.max_failures_per_run,
            "max_runtime_minutes": self.max_runtime_minutes,
            "allow_modes": self.allow_modes,
            "blocked_task_types": self.blocked_task_types,
            "allowed_task_types": self.allowed_task_types,
            "reddit_autopost_enabled": self.reddit_autopost_enabled,
            "reddit_max_posts_per_day": self.reddit_max_posts_per_day,
            "reddit_max_posts_per_week": self.reddit_max_posts_per_week,
            "stop_on_policy_block": self.stop_on_policy_block,
            "scheduler": self.scheduler.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OrchestrationPolicy":
        policy = cls()
        policy.schema_version = int(data.get("schema_version", 1) or 1)
        policy.max_steps_per_run = int(data.get("max_steps_per_run", policy.max_steps_per_run) or 1)
        policy.max_failures_per_run = int(
            data.get("max_failures_per_run", policy.max_failures_per_run) or 1
        )
        policy.max_runtime_minutes = int(
            data.get("max_runtime_minutes", policy.max_runtime_minutes) or 1
        )

        allow_modes = data.get("allow_modes", policy.allow_modes)
        if isinstance(allow_modes, list):
            policy.allow_modes = [str(mode) for mode in allow_modes if mode]

        blocked = data.get("blocked_task_types", policy.blocked_task_types)
        if isinstance(blocked, list):
            policy.blocked_task_types = [str(task_type) for task_type in blocked if task_type]

        allowed = data.get("allowed_task_types", policy.allowed_task_types)
        if isinstance(allowed, list):
            policy.allowed_task_types = [str(task_type) for task_type in allowed if task_type]

        policy.reddit_autopost_enabled = bool(
            data.get("reddit_autopost_enabled", policy.reddit_autopost_enabled)
        )
        policy.reddit_max_posts_per_day = int(
            data.get("reddit_max_posts_per_day", policy.reddit_max_posts_per_day) or 0
        )
        policy.reddit_max_posts_per_week = int(
            data.get("reddit_max_posts_per_week", policy.reddit_max_posts_per_week) or 0
        )
        policy.stop_on_policy_block = bool(data.get("stop_on_policy_block", policy.stop_on_policy_block))
        
        # Load scheduler config (backward compatible - uses defaults if missing)
        scheduler_data = data.get("scheduler")
        policy.scheduler = SchedulerConfig.from_dict(scheduler_data)
        
        return policy


@dataclass
class PolicyContext:
    """Runtime inputs for policy evaluation."""

    reddit_posts_last_day: int = 0
    reddit_posts_last_week: int = 0
    reddit_auth_ready: bool = False
    reddit_auth_error: str | None = None


@dataclass
class PolicyDecision:
    """Decision returned by PolicyEngine."""

    allowed: bool
    reason: str = ""


class PolicyEngine:
    """Loads/saves policies and evaluates task eligibility."""

    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root).expanduser().resolve()
        self.policy_path = self.repo_root / ".github" / "automation" / "orchestrator_policy.json"

    def load_or_create(self) -> OrchestrationPolicy:
        if self.policy_path.exists():
            try:
                payload = json.loads(self.policy_path.read_text())
                if isinstance(payload, dict):
                    return OrchestrationPolicy.from_dict(payload)
            except Exception:
                pass

        policy = OrchestrationPolicy()
        self.save(policy)
        return policy

    def save(self, policy: OrchestrationPolicy) -> None:
        self.policy_path.parent.mkdir(parents=True, exist_ok=True)
        self.policy_path.write_text(json.dumps(policy.to_dict(), indent=2))

    def evaluate(self, task: Any, autonomy_mode: str, policy: OrchestrationPolicy, context: PolicyContext) -> PolicyDecision:
        task_type = str(getattr(task, "type", ""))
        if autonomy_mode not in policy.allow_modes:
            return PolicyDecision(False, f"autonomy mode '{autonomy_mode}' not allowed by policy")

        if policy.allowed_task_types and task_type not in policy.allowed_task_types:
            return PolicyDecision(False, f"task type '{task_type}' not in policy allowlist")

        if task_type in policy.blocked_task_types:
            return PolicyDecision(False, f"task type '{task_type}' blocked by policy")

        if task_type == "reddit_reply":
            return self._evaluate_reddit_reply(policy, context)

        return PolicyDecision(True, "allowed")

    @staticmethod
    def _evaluate_reddit_reply(policy: OrchestrationPolicy, context: PolicyContext) -> PolicyDecision:
        if not policy.reddit_autopost_enabled:
            return PolicyDecision(False, "reddit autopost is disabled by policy")

        if not context.reddit_auth_ready:
            details = f": {context.reddit_auth_error}" if context.reddit_auth_error else ""
            return PolicyDecision(False, f"reddit auth not ready{details}")

        if context.reddit_posts_last_day >= policy.reddit_max_posts_per_day:
            return PolicyDecision(
                False,
                f"reddit daily limit reached ({context.reddit_posts_last_day}/{policy.reddit_max_posts_per_day})",
            )

        if context.reddit_posts_last_week >= policy.reddit_max_posts_per_week:
            return PolicyDecision(
                False,
                f"reddit weekly limit reached ({context.reddit_posts_last_week}/{policy.reddit_max_posts_per_week})",
            )

        return PolicyDecision(True, "reddit policy checks passed")
