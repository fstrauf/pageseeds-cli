"""Bounded orchestration loop for autonomous workflow execution."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from ..config import AUTONOMY_MODE_MAP, PHASES
from .env_resolver import EnvResolver
from .ledger import OrchestrationLedger
from .policy import OrchestrationPolicy, PolicyContext, PolicyEngine
from .reporter import build_run_summary
from .tool_registry import ToolRegistry
from .types import ExecutionContext


@dataclass
class OrchestrationRunResult:
    """Outcome of one orchestration run."""

    run_id: str
    status: str
    reason: str
    processed: int
    succeeded: int
    failed: int
    blocked: int
    summary_json: str
    summary_markdown: str
    events_path: str


class OrchestratorService:
    """Runs a policy-bounded orchestration loop for a single project."""

    def __init__(
        self,
        task_list,
        project,
        executor,
        runners: dict[str, Any],
        *,
        autonomy_mode_map: dict[str, str] | None = None,
        phase_order: list[str] | tuple[str, ...] | None = None,
    ):
        self.task_list = task_list
        self.project = project
        self.executor = executor
        self.runners = runners
        self.autonomy_mode_map = autonomy_mode_map or AUTONOMY_MODE_MAP
        self.phase_order = list(phase_order) if phase_order else list(PHASES)
        self.policy_engine = PolicyEngine(Path(project.repo_root))
        self.ledger = OrchestrationLedger(Path(task_list.automation_dir))
        self.tool_registry = ToolRegistry()

    def run(
        self,
        *,
        max_steps: int | None = None,
        max_runtime_minutes: int | None = None,
        reddit_autopost: bool | None = None,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> OrchestrationRunResult:
        policy = self.policy_engine.load_or_create()
        policy = self._apply_overrides(policy, max_steps=max_steps, max_runtime_minutes=max_runtime_minutes, reddit_autopost=reddit_autopost)

        run_id, run_dir = self.ledger.start_run(self.project.website_id, policy.to_dict())
        started_at = datetime.now()
        events: list[dict[str, Any]] = []
        processed = 0
        succeeded = 0
        failed = 0
        blocked = 0
        status = "complete"
        reason = "max_steps_reached"

        for step_num in range(policy.max_steps_per_run):
            # Check runtime limit before each step
            elapsed = datetime.now() - started_at
            elapsed_minutes = elapsed.total_seconds() / 60
            
            if elapsed_minutes >= policy.max_runtime_minutes:
                status = "stopped"
                reason = f"max_runtime_reached ({policy.max_runtime_minutes}m)"
                
                # Add timeout event
                timeout_event = self.ledger.append_event(
                    run_dir,
                    "runtime_timeout",
                    {
                        "elapsed_minutes": round(elapsed_minutes, 1),
                        "limit_minutes": policy.max_runtime_minutes,
                        "step_num": step_num,
                    },
                )
                events.append(timeout_event)
                if progress_callback:
                    progress_callback(timeout_event)
                break

            self.task_list.load()
            ready_tasks = self.task_list.get_ready()
            if not ready_tasks:
                status = "complete"
                reason = "no_ready_tasks"
                break

            context = self._build_policy_context(policy, ready_tasks)
            candidate, block_events = self._select_candidate(ready_tasks, policy, context)
            for event_payload in block_events:
                blocked += 1
                event = self.ledger.append_event(run_dir, "policy_block", event_payload)
                events.append(event)
                if progress_callback:
                    progress_callback(event)

            if candidate is None:
                status = "paused"
                reason = "no_policy_eligible_tasks"
                break

            selected_event = self.ledger.append_event(
                run_dir,
                "task_selected",
                {
                    "task_id": candidate.id,
                    "task_type": candidate.type,
                    "title": candidate.title,
                    "elapsed_minutes": round(elapsed_minutes, 1),
                },
            )
            events.append(selected_event)
            if progress_callback:
                progress_callback(selected_event)

            ok, message = self._execute_task(candidate, policy)
            processed += 1
            if ok:
                succeeded += 1
            else:
                failed += 1

            # Recalculate elapsed time after task execution
            elapsed = datetime.now() - started_at
            elapsed_minutes = elapsed.total_seconds() / 60

            result_event = self.ledger.append_event(
                run_dir,
                "task_result",
                {
                    "task_id": candidate.id,
                    "task_type": candidate.type,
                    "success": ok,
                    "message": message,
                    "elapsed_minutes": round(elapsed_minutes, 1),
                },
            )
            events.append(result_event)
            if progress_callback:
                progress_callback(result_event)

            if failed >= policy.max_failures_per_run:
                status = "stopped"
                reason = "max_failures_reached"
                break
        else:
            status = "complete"
            reason = "max_steps_reached"

        finished_at = datetime.now()
        summary_dict, summary_md = build_run_summary(
            run_id=run_id,
            project_id=self.project.website_id,
            started_at=started_at,
            finished_at=finished_at,
            status=status,
            reason=reason,
            processed=processed,
            succeeded=succeeded,
            failed=failed,
            blocked=blocked,
            events=events,
            policy=policy.to_dict(),
        )
        summary_json, summary_markdown = self.ledger.write_summary(run_dir, summary_dict, summary_md)

        return OrchestrationRunResult(
            run_id=run_id,
            status=status,
            reason=reason,
            processed=processed,
            succeeded=succeeded,
            failed=failed,
            blocked=blocked,
            summary_json=str(summary_json),
            summary_markdown=str(summary_markdown),
            events_path=str(run_dir / "events.jsonl"),
        )

    def _apply_overrides(
        self,
        policy: OrchestrationPolicy,
        *,
        max_steps: int | None,
        max_runtime_minutes: int | None,
        reddit_autopost: bool | None,
    ) -> OrchestrationPolicy:
        overridden = OrchestrationPolicy.from_dict(policy.to_dict())
        if max_steps is not None:
            overridden.max_steps_per_run = max(1, int(max_steps))
        if max_runtime_minutes is not None:
            overridden.max_runtime_minutes = max(1, int(max_runtime_minutes))
        if reddit_autopost is not None:
            overridden.reddit_autopost_enabled = bool(reddit_autopost)
        return overridden

    def _select_candidate(
        self,
        ready_tasks: list[Any],
        policy: OrchestrationPolicy,
        context: PolicyContext,
    ) -> tuple[Any | None, list[dict[str, Any]]]:
        ordered = sorted(ready_tasks, key=self._task_sort_key)
        blocks: list[dict[str, Any]] = []
        for task in ordered:
            autonomy_mode = self.autonomy_mode_map.get(getattr(task, "type", ""), "manual")
            decision = self.policy_engine.evaluate(task, autonomy_mode, policy, context)
            if decision.allowed:
                return task, blocks
            blocks.append(
                {
                    "task_id": task.id,
                    "task_type": task.type,
                    "autonomy_mode": autonomy_mode,
                    "reason": decision.reason,
                }
            )
            if policy.stop_on_policy_block:
                return None, blocks
        return None, blocks

    def _task_sort_key(self, task: Any) -> tuple[int, int, str]:
        phase = str(getattr(task, "phase", "implementation"))
        phase_idx = self.phase_order.index(phase) if phase in self.phase_order else len(self.phase_order)
        priority = str(getattr(task, "priority", "medium")).lower()
        priority_idx = {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(priority, 2)
        created_at = str(getattr(task, "created_at", "") or "")
        return phase_idx, priority_idx, created_at

    def _build_policy_context(self, policy: OrchestrationPolicy, ready_tasks: list[Any]) -> PolicyContext:
        day_count, week_count = self._reddit_counts()
        auth_ready = False
        auth_error = None

        needs_reddit = any(getattr(task, "type", "") == "reddit_reply" for task in ready_tasks)
        if policy.reddit_autopost_enabled and needs_reddit:
            auth_ready, auth_error = self._reddit_auth_status()

        return PolicyContext(
            reddit_posts_last_day=day_count,
            reddit_posts_last_week=week_count,
            reddit_auth_ready=auth_ready,
            reddit_auth_error=auth_error,
        )

    def _reddit_counts(self) -> tuple[int, int]:
        now = datetime.now()
        last_day_cutoff = now - timedelta(days=1)
        last_week_cutoff = now - timedelta(days=7)
        day_count = 0
        week_count = 0

        for task in self.task_list.tasks:
            if getattr(task, "type", "") != "reddit_reply" or getattr(task, "status", "") != "done":
                continue
            completed_at = getattr(task, "completed_at", None)
            if not completed_at:
                continue
            try:
                completed = datetime.fromisoformat(str(completed_at).replace("Z", "+00:00"))
                if completed.tzinfo is not None:
                    completed = completed.replace(tzinfo=None)
            except Exception:
                continue

            if completed >= last_day_cutoff:
                day_count += 1
            if completed >= last_week_cutoff:
                week_count += 1

        return day_count, week_count

    def _reddit_auth_status(self) -> tuple[bool, str | None]:
        resolver = EnvResolver(repo_root=Path(self.project.repo_root))
        token, _, _ = resolver.resolve_key("REDDIT_REFRESH_TOKEN")
        if not token:
            return False, "Missing REDDIT_REFRESH_TOKEN."

        context = ExecutionContext(repo_root=Path(self.project.repo_root))
        result = self.tool_registry.run_command(
            ["automation-cli", "reddit", "auth-status"],
            context=context,
            timeout=45,
            env_overrides={"REDDIT_REFRESH_TOKEN": token},
        )
        if not result.success:
            return False, (result.stderr or result.stdout or "auth-status failed").strip()

        payload = self._parse_json_payload(result.stdout)
        if not payload:
            return False, "Could not parse auth-status output."
        if payload.get("authenticated") is True:
            return True, None
        return False, str(payload.get("error") or "Unknown reddit auth error.")

    def _execute_task(self, task: Any, policy: OrchestrationPolicy) -> tuple[bool, str]:
        self._set_runner_execution_context(
            {
                "non_interactive": True,
                "auto_confirm": True,
                "reddit_reply": {
                    "action": "auto_post" if policy.reddit_autopost_enabled else "keep",
                },
            }
        )
        if task.type == "reddit_reply" and policy.reddit_autopost_enabled:
            try:
                return self._execute_reddit_reply(task)
            finally:
                self._set_runner_execution_context({})

        try:
            result = self.executor.execute_task(task)
            # Handle both old bool return and new tuple return
            if isinstance(result, tuple):
                success, message = result
                if success:
                    return True, message or "executed via execution engine"
                return False, message or "execution engine reported failure"
            else:
                # Legacy compatibility
                if result:
                    return True, "executed via execution engine"
                return False, "execution engine reported failure"
        finally:
            self._set_runner_execution_context({})

    def _execute_reddit_reply(self, task: Any) -> tuple[bool, str]:
        runner = self.runners.get("reddit")
        if runner and hasattr(runner, "run_reply_task_autonomous"):
            ok, message = runner.run_reply_task_autonomous(task)
            return ok, message

        return False, "reddit runner does not support autonomous reply execution"

    def _set_runner_execution_context(self, context: dict[str, Any]) -> None:
        for runner in self.runners.values():
            if hasattr(runner, "set_execution_context"):
                runner.set_execution_context(context)

    @staticmethod
    def _parse_json_payload(stdout: str) -> dict[str, Any] | None:
        if not stdout:
            return None
        try:
            return json.loads(stdout)
        except Exception:
            pass
        start = stdout.find("{")
        end = stdout.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            return json.loads(stdout[start : end + 1])
        except Exception:
            return None
