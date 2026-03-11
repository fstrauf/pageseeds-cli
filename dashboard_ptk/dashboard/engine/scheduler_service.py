"""Scheduled cycle runner for automated task creation and orchestration."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .ledger import OrchestrationLedger
from .policy import OrchestrationPolicy, PolicyEngine
from .preflight import ProjectPreflight
from .runtime_config import RuntimeConfig
from .task_store import TaskStore
from .types import (
    SchedulerConfig,
    SchedulerRule,
    SchedulerState,
    SchedulerStats,
    RuleState,
    TaskRecord,
    TaskState,
)
from ..workflow_bundle import WorkflowBundle, legacy_seo_reddit_bundle, scheduler_default_bundle

# Imported lazily to avoid circular dependencies
# from ..storage import TaskList
# from ..models import Project


class _NonInteractiveSession:
    """Prompt shim used when scheduler executes runners outside the TUI."""

    def prompt(self, *_args, **kwargs) -> str:
        default = kwargs.get("default")
        return str(default) if default is not None else ""


@dataclass
class DueRuleResult:
    """Result of evaluating a single rule for being due."""

    rule: SchedulerRule
    is_due: bool
    next_due_at: datetime
    reason: str = ""
    overdue_level: str = "none"  # none, warn, error


@dataclass
class TaskCreationResult:
    """Result of attempting to create a task from a rule."""

    rule_id: str
    success: bool
    task_id: str | None = None
    message: str = ""


@dataclass
class ProjectCycleResult:
    """Result of running a scheduled cycle for one project."""

    website_id: str
    preflight_ok: bool
    preflight_error: str = ""
    due_rules: list[DueRuleResult] = field(default_factory=list)
    tasks_created: list[TaskCreationResult] = field(default_factory=list)
    orchestrator_run: bool = False
    orchestrator_result: dict[str, Any] = field(default_factory=dict)
    reminders: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "website_id": self.website_id,
            "preflight_ok": self.preflight_ok,
            "preflight_error": self.preflight_error,
            "due_rules": [
                {
                    "rule_id": r.rule.id,
                    "is_due": r.is_due,
                    "next_due_at": r.next_due_at.isoformat(),
                    "reason": r.reason,
                    "overdue_level": r.overdue_level,
                }
                for r in self.due_rules
            ],
            "tasks_created": [
                {
                    "rule_id": t.rule_id,
                    "success": t.success,
                    "task_id": t.task_id,
                    "message": t.message,
                }
                for t in self.tasks_created
            ],
            "orchestrator_run": self.orchestrator_run,
            "orchestrator_result": self.orchestrator_result,
            "reminders": self.reminders,
            "error": self.error,
        }


@dataclass
class GlobalCycleResult:
    """Result of running a scheduled cycle across all projects."""

    started_at: str
    finished_at: str
    result: str  # ok, warn, error
    project_results: list[ProjectCycleResult]
    total_tasks_created: int
    total_orchestrator_runs: int
    errors: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "result": self.result,
            "project_results": [p.to_dict() for p in self.project_results],
            "total_tasks_created": self.total_tasks_created,
            "total_orchestrator_runs": self.total_orchestrator_runs,
            "errors": self.errors,
        }


class SchedulerService:
    """Main cycle runner: iterates projects, evaluates due rules, creates tasks."""

    def __init__(
        self,
        projects_config_path: Path,
        output_dir: Path,
        workflow_bundle: WorkflowBundle | None = None,
        runtime_config: RuntimeConfig | None = None,
    ):
        self.workflow_bundle = workflow_bundle or scheduler_default_bundle()
        self.runtime_config = runtime_config or RuntimeConfig(
            required_clis=tuple(self.workflow_bundle.required_clis)
        )
        self.projects_config_path = Path(projects_config_path).expanduser().resolve()
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.monitoring_dir = self.output_dir / "monitoring" / "seo_scheduler"
        self.monitoring_dir.mkdir(parents=True, exist_ok=True)

    def run_cycle(self, project_id: str | None = None) -> GlobalCycleResult:
        """Run scheduled cycle over all projects or a single project."""
        started_at = datetime.now().isoformat()
        started_dt = datetime.now()
        project_results: list[ProjectCycleResult] = []
        errors: list[str] = []
        total_tasks_created = 0
        total_orchestrator_runs = 0

        # Load projects config
        projects = self._load_projects()
        if project_id:
            projects = {k: v for k, v in projects.items() if k == project_id}
            if not projects:
                errors.append(f"Project {project_id} not found in config")

        # Process each project
        for website_id, project_config in projects.items():
            try:
                result = self._process_project(website_id, project_config)
                project_results.append(result)
                total_tasks_created += len([t for t in result.tasks_created if t.success])
                if result.orchestrator_run:
                    total_orchestrator_runs += 1
            except Exception as exc:
                errors.append(f"Project {website_id}: {exc}")
                project_results.append(
                    ProjectCycleResult(
                        website_id=website_id,
                        preflight_ok=False,
                        error=str(exc),
                    )
                )

        finished_at = datetime.now().isoformat()
        
        # Determine overall result
        result_status = "ok"
        if errors:
            result_status = "error"
        elif any(r.reminders for r in project_results):
            result_status = "warn"

        cycle_result = GlobalCycleResult(
            started_at=started_at,
            finished_at=finished_at,
            result=result_status,
            project_results=project_results,
            total_tasks_created=total_tasks_created,
            total_orchestrator_runs=total_orchestrator_runs,
            errors=errors,
        )

        # Write status files
        self._write_status_files(cycle_result, started_dt)

        return cycle_result

    def _load_projects(self) -> dict[str, dict[str, Any]]:
        """Load projects from config file."""
        if not self.projects_config_path.exists():
            return {}
        try:
            data = json.loads(self.projects_config_path.read_text())
            if isinstance(data, dict):
                # Handle {"projects": [...]} format (standard)
                if "projects" in data:
                    projects = data["projects"]
                    if isinstance(projects, list):
                        return {p.get("website_id", f"project_{i}"): p for i, p in enumerate(projects)}
                    return {}
                # Handle flat dict format {"site1": {...}, "site2": {...}}
                return data
            if isinstance(data, list):
                return {p.get("website_id", f"project_{i}"): p for i, p in enumerate(data)}
        except Exception:
            pass
        return {}

    def _process_project(
        self,
        website_id: str,
        project_config: dict[str, Any],
    ) -> ProjectCycleResult:
        """Process a single project in the scheduled cycle."""
        repo_root = Path(project_config.get("repo_root", "")).expanduser().resolve()
        
        # Preflight check
        preflight = ProjectPreflight(
            repo_root=repo_root,
            website_id=website_id,
            runtime_config=self.runtime_config,
            required_clis=self.workflow_bundle.required_clis,
            check_reddit_auth=self.workflow_bundle.check_reddit_auth,
        )
        preflight_report = preflight.run()
        if not preflight_report.is_ready:
            error_msg = "; ".join([f.message for f in preflight_report.errors]) if preflight_report.errors else "Preflight failed"
            return ProjectCycleResult(
                website_id=website_id,
                preflight_ok=False,
                preflight_error=error_msg,
            )

        result = ProjectCycleResult(
            website_id=website_id,
            preflight_ok=True,
        )

        # Load policy and scheduler config
        policy_engine = PolicyEngine(repo_root)
        policy = policy_engine.load_or_create()
        scheduler_config = policy.scheduler

        if not scheduler_config.enabled:
            result.reminders.append({"type": "info", "message": "Scheduler disabled for project"})
            return result

        # Load scheduler state
        scheduler_state = self._load_scheduler_state(repo_root)
        scheduler_state.last_cycle_started_at = datetime.now().isoformat()

        # Load task store
        automation_dir = repo_root / ".github" / "automation"
        task_list_path = automation_dir / "task_list.json"
        task_store = TaskStore(task_list_path, website_id)
        task_state = task_store.load()
        reddit_open_before = self._count_open_reddit_reply_tasks(task_state)

        # Evaluate due rules
        tz = self._get_timezone(scheduler_config.timezone)
        now = datetime.now(tz)
        due_results = self._evaluate_due_rules(
            scheduler_config.rules,
            scheduler_state,
            task_state,
            now,
            scheduler_config,
        )
        result.due_rules = due_results

        # Create tasks for due rules (with deduplication and caps)
        created_count = 0
        for due_result in due_results:
            if not due_result.is_due:
                continue
            if due_result.rule.mode == "reminder_only":
                reminder = self._emit_reminder_for_rule(
                    due_result.rule,
                    scheduler_state,
                    now,
                )
                result.reminders.append(reminder)
                continue
            if created_count >= scheduler_config.max_task_creations_per_cycle:
                result.reminders.append({
                    "type": "cap_hit",
                    "message": f"Max creations ({scheduler_config.max_task_creations_per_cycle}) reached",
                })
                break

            creation_result = self._create_task_for_rule(
                due_result.rule,
                task_state,
                task_store,
                scheduler_state,
                now,
            )
            result.tasks_created.append(creation_result)
            if creation_result.success:
                created_count += 1

        # Run orchestrator if tasks were created
        if created_count > 0:
            orchestrator_result = self._run_orchestrator(
                repo_root, policy, automation_dir, website_id
            )
            result.orchestrator_run = True
            result.orchestrator_result = orchestrator_result
            scheduler_state.stats.orchestrator_runs += 1

            # Detect newly generated Reddit reply opportunities and notify on macOS.
            latest_state = task_store.load()
            reddit_open_after = self._count_open_reddit_reply_tasks(latest_state)
            new_reddit_opportunities = max(0, reddit_open_after - reddit_open_before)
            result.orchestrator_result["new_reddit_opportunities"] = new_reddit_opportunities

            if new_reddit_opportunities > 0:
                reminder = {
                    "type": "reddit_opportunities",
                    "project": website_id,
                    "count": new_reddit_opportunities,
                    "message": (
                        f"{new_reddit_opportunities} new Reddit opportunity draft(s) ready. "
                        "Open Dashboard -> Work on Tasks -> Bulk by Type (reddit_reply)."
                    ),
                }
                result.reminders.append(reminder)
                notification_sent = self._notify_macos_reddit_opportunities(
                    website_id=website_id,
                    new_count=new_reddit_opportunities,
                )
                result.orchestrator_result["reddit_notification_sent"] = notification_sent

        # Build reminders and attention summary
        result.reminders.extend(
            self._build_reminders(task_state, due_results, scheduler_config)
        )
        
        # Add attention summary to result
        attention_summary = self._build_attention_summary(task_state, due_results)
        result.orchestrator_result["attention_summary"] = attention_summary

        # Update stats and save state
        scheduler_state.stats.cycles += 1
        scheduler_state.stats.tasks_created += created_count
        scheduler_state.stats.reminders_emitted += len(
            [r for r in result.reminders if r.get("type") == "rule_reminder"]
        )
        scheduler_state.last_cycle_finished_at = datetime.now().isoformat()
        self._save_scheduler_state(repo_root, scheduler_state)

        return result

    def _evaluate_due_rules(
        self,
        rules: list[SchedulerRule],
        scheduler_state: SchedulerState,
        task_state: TaskState,
        now: datetime,
        config: SchedulerConfig,
    ) -> list[DueRuleResult]:
        """Evaluate which rules are due for execution."""
        results: list[DueRuleResult] = []

        for rule in rules:
            if not rule.enabled:
                results.append(
                    DueRuleResult(
                        rule=rule,
                        is_due=False,
                        next_due_at=now,
                        reason="Rule disabled",
                    )
                )
                continue

            rule_state = scheduler_state.rules.get(rule.id, RuleState())
            
            # Determine anchor time
            if rule.mode == "create_task":
                anchor_str = rule_state.last_task_created_at or rule_state.last_due_at
            else:  # reminder_only
                anchor_str = rule_state.last_reminder_at or rule_state.last_due_at
            
            if anchor_str:
                try:
                    anchor = datetime.fromisoformat(anchor_str)
                    if anchor.tzinfo is None and now.tzinfo is not None:
                        anchor = anchor.replace(tzinfo=now.tzinfo)
                except Exception:
                    anchor = now - timedelta(hours=rule.cadence_hours + 1)
            else:
                # Never run before, mark as due
                anchor = now - timedelta(hours=rule.cadence_hours + 1)

            next_due_at = anchor + timedelta(hours=rule.cadence_hours)
            is_due = now >= next_due_at

            # Check quiet hours
            quiet_hours_active = self._is_quiet_hours(now, config)
            if is_due and quiet_hours_active:
                is_due = False
                reason = "Due but deferred (quiet hours)"
            elif is_due:
                reason = "Due for execution"
            else:
                reason = f"Next due at {next_due_at.isoformat()}"

            # Calculate overdue level
            overdue_level = "none"
            if is_due or now > next_due_at:
                hours_overdue = (now - next_due_at).total_seconds() / 3600
                if hours_overdue > config.overdue_error_after_hours:
                    overdue_level = "error"
                elif hours_overdue > config.overdue_warn_after_hours:
                    overdue_level = "warn"

            results.append(
                DueRuleResult(
                    rule=rule,
                    is_due=is_due,
                    next_due_at=next_due_at,
                    reason=reason,
                    overdue_level=overdue_level,
                )
            )

            # Update rule state tracking
            if is_due:
                rule_state.last_due_at = now.isoformat()
                scheduler_state.rules[rule.id] = rule_state

        return results

    def _create_task_for_rule(
        self,
        rule: SchedulerRule,
        task_state: TaskState,
        task_store: TaskStore,
        scheduler_state: SchedulerState,
        now: datetime,
    ) -> TaskCreationResult:
        """Create a task for a due rule with deduplication."""
        if rule.mode != "create_task":
            return TaskCreationResult(
                rule_id=rule.id,
                success=False,
                message=f"Rule mode '{rule.mode}' does not create tasks",
            )
        
        # Check for existing open task of same type
        open_statuses = {"todo", "in_progress", "review"}
        for task in task_state.tasks:
            if task.type == rule.task_type and task.status in open_statuses:
                return TaskCreationResult(
                    rule_id=rule.id,
                    success=False,
                    message=f"Open task exists: {task.id}",
                )

        # Create new task
        task_id = f"{rule.task_type}_{now.strftime('%Y%m%d_%H%M%S')}"
        new_task = TaskRecord(
            id=task_id,
            type=rule.task_type,
            title=f"Scheduled {rule.task_type.replace('_', ' ').title()}",
            phase=rule.phase,
            status="todo",
            priority=rule.priority,
            execution_mode="automatic" if rule.mode == "create_task" else "manual",
            metadata={
                "created_by": "scheduler",
                "rule_id": rule.id,
                "created_at": now.isoformat(),
            },
        )

        task_state.tasks.append(new_task)
        task_store.save(task_state)

        # Update scheduler state
        rule_state = scheduler_state.rules.get(rule.id, RuleState())
        rule_state.last_task_created_at = now.isoformat()
        rule_state.last_status = "created"
        rule_state.last_message = f"Created task {task_id}"
        scheduler_state.rules[rule.id] = rule_state

        return TaskCreationResult(
            rule_id=rule.id,
            success=True,
            task_id=task_id,
            message="Task created successfully",
        )

    def _emit_reminder_for_rule(
        self,
        rule: SchedulerRule,
        scheduler_state: SchedulerState,
        now: datetime,
    ) -> dict[str, Any]:
        """Record and return a reminder payload for a reminder-only rule."""
        rule_state = scheduler_state.rules.get(rule.id, RuleState())
        rule_state.last_reminder_at = now.isoformat()
        rule_state.last_status = "reminded"
        rule_state.last_message = f"Reminder emitted for {rule.task_type}"
        scheduler_state.rules[rule.id] = rule_state
        return {
            "type": "rule_reminder",
            "rule_id": rule.id,
            "task_type": rule.task_type,
            "message": f"Reminder: {rule.task_type} is due",
        }

    def _run_orchestrator(
        self,
        repo_root: Path,
        policy: OrchestrationPolicy,
        automation_dir: Path,
        website_id: str,
    ) -> dict[str, Any]:
        """Run the bounded orchestrator for the project."""
        # Import here to avoid circular dependency
        from .orchestrator import OrchestratorService
        from .executor import ExecutionEngine
        from ..storage import TaskList
        from ..models import Project
        # Create project instance
        project = Project(
            name=website_id,
            website_id=website_id,
            repo_root=str(repo_root),
        )
        
        # Load task list
        task_list = TaskList(
            project,
            autonomy_mode_map=self.workflow_bundle.autonomy_mode_map,
        )
        
        # Build the same runner registry used by interactive dashboard execution.
        bundle = self.workflow_bundle
        if bundle.runner_builder is None or bundle.handler_builder is None:
            bundle = legacy_seo_reddit_bundle()

        runners = bundle.build_runners(task_list, project, _NonInteractiveSession())
        executor = ExecutionEngine(
            task_list,
            project,
            runners,
            handlers=bundle.build_handlers(),
        )

        # Run orchestrator
        orchestrator = OrchestratorService(
            task_list,
            project,
            executor,
            runners,
            autonomy_mode_map=bundle.autonomy_mode_map,
        )
        result = orchestrator.run(max_steps=policy.max_steps_per_run)

        return {
            "run_id": result.run_id,
            "status": result.status,
            "reason": result.reason,
            "processed": result.processed,
            "succeeded": result.succeeded,
            "failed": result.failed,
            "blocked": result.blocked,
        }

    def _build_reminders(
        self,
        task_state: TaskState,
        due_results: list[DueRuleResult],
        config: SchedulerConfig,
    ) -> list[dict[str, Any]]:
        """Build reminders for overdue and manual tasks."""
        reminders: list[dict[str, Any]] = []

        # Overdue rules
        for dr in due_results:
            if dr.overdue_level != "none":
                reminders.append({
                    "type": "overdue_rule",
                    "level": dr.overdue_level,
                    "rule_id": dr.rule.id,
                    "message": f"Rule {dr.rule.id} is {dr.overdue_level}",
                })

        # Manual tasks
        manual_tasks = [t for t in task_state.tasks if t.execution_mode == "manual" and t.status in {"todo", "in_progress"}]
        for task in manual_tasks:
            reminders.append({
                "type": "manual_task",
                "task_id": task.id,
                "task_type": task.type,
                "message": f"Manual task requires attention: {task.title}",
            })

        # Spec tasks
        spec_tasks = [t for t in task_state.tasks if t.status == "todo" and t.type.endswith("_spec")]
        for task in spec_tasks:
            reminders.append({
                "type": "spec_task",
                "task_id": task.id,
                "task_type": task.type,
                "message": f"Spec task pending: {task.title}",
            })

        # Stale review tasks (> 48 hours)
        review_tasks = [t for t in task_state.tasks if t.status == "review"]
        now = datetime.now()
        for task in review_tasks:
            if task.run.started_at:
                try:
                    started = datetime.fromisoformat(task.run.started_at)
                    hours_in_review = (now - started).total_seconds() / 3600
                    if hours_in_review > 48:
                        reminders.append({
                            "type": "stale_review",
                            "task_id": task.id,
                            "hours_in_review": int(hours_in_review),
                            "message": f"Review task stale for {int(hours_in_review)}h: {task.title}",
                        })
                except Exception:
                    pass

        # Failed tasks (with retries exhausted)
        failed_tasks = [t for t in task_state.tasks if t.status == "todo" and t.run.attempts >= 3 and t.run.last_error]
        for task in failed_tasks:
            reminders.append({
                "type": "failed_task",
                "task_id": task.id,
                "task_type": task.type,
                "attempts": task.run.attempts,
                "message": f"Task failed {task.run.attempts} times: {task.title}",
            })

        # Blocked tasks (dependencies not met)
        blocked_tasks = []
        completed_ids = {t.id for t in task_state.tasks if t.status == "done"}
        for task in task_state.tasks:
            if task.status == "todo" and task.depends_on:
                missing_deps = [d for d in task.depends_on if d not in completed_ids]
                if missing_deps:
                    blocked_tasks.append((task, missing_deps))
        
        for task, missing_deps in blocked_tasks[:5]:  # Limit to first 5
            reminders.append({
                "type": "blocked_task",
                "task_id": task.id,
                "task_type": task.type,
                "missing_deps": missing_deps,
                "message": f"Task blocked by {len(missing_deps)} dependencies: {task.title}",
            })

        return reminders

    def _count_open_reddit_reply_tasks(self, task_state: TaskState) -> int:
        """Count open Reddit reply tasks (todo/in_progress/review)."""
        open_statuses = {"todo", "in_progress", "review"}
        return len(
            [
                t
                for t in task_state.tasks
                if t.type == "reddit_reply" and t.status in open_statuses
            ]
        )

    def _notify_macos_reddit_opportunities(self, website_id: str, new_count: int) -> bool:
        """Send a macOS user notification for new Reddit opportunities."""
        if new_count <= 0:
            return False
        if sys.platform != "darwin":
            return False
        if not shutil.which("osascript"):
            return False

        title = self._escape_applescript(f"Reddit opportunities: {website_id}")
        body = self._escape_applescript(
            f"{new_count} new draft replies ready. Open dashboard and bulk review reddit_reply tasks."
        )
        script = f'display notification "{body}" with title "{title}"'

        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except Exception:
            return False

    @staticmethod
    def _escape_applescript(value: str) -> str:
        """Escape string content for AppleScript string literals."""
        return value.replace("\\", "\\\\").replace('"', '\\"')

    def _build_attention_summary(
        self,
        task_state: TaskState,
        due_results: list[DueRuleResult],
    ) -> dict[str, Any]:
        """Build comprehensive attention summary for display."""
        now = datetime.now()
        
        # Count by category
        overdue_rules = [d for d in due_results if d.overdue_level != "none"]
        manual_tasks = [t for t in task_state.tasks if t.execution_mode == "manual" and t.status in {"todo", "in_progress"}]
        spec_tasks = [t for t in task_state.tasks if t.status == "todo" and t.type.endswith("_spec")]
        
        # Stale review tasks
        stale_reviews = []
        for task in task_state.tasks:
            if task.status == "review" and task.run.started_at:
                try:
                    started = datetime.fromisoformat(task.run.started_at)
                    hours_in_review = (now - started).total_seconds() / 3600
                    if hours_in_review > 48:
                        stale_reviews.append(task)
                except Exception:
                    pass
        
        # High priority ready tasks
        ready_tasks = [t for t in task_state.tasks if t.status == "todo" and not t.depends_on]
        high_priority_ready = [t for t in ready_tasks if t.priority in ("critical", "high")]
        
        return {
            "overdue_rules_count": len(overdue_rules),
            "overdue_rules_warn": len([d for d in overdue_rules if d.overdue_level == "warn"]),
            "overdue_rules_error": len([d for d in overdue_rules if d.overdue_level == "error"]),
            "manual_tasks_count": len(manual_tasks),
            "spec_tasks_count": len(spec_tasks),
            "stale_reviews_count": len(stale_reviews),
            "high_priority_ready_count": len(high_priority_ready),
            "total_attention_needed": len(overdue_rules) + len(manual_tasks) + len(spec_tasks) + len(stale_reviews),
            "top_priority": self._compute_top_priority(overdue_rules, manual_tasks, spec_tasks, stale_reviews),
        }

    def _compute_top_priority(
        self,
        overdue_rules: list[DueRuleResult],
        manual_tasks: list,
        spec_tasks: list,
        stale_reviews: list,
    ) -> str | None:
        """Compute the top priority attention item."""
        # Priority order: error-level overdue > manual > spec > stale review > warn-level overdue
        
        error_overdue = [d for d in overdue_rules if d.overdue_level == "error"]
        if error_overdue:
            return f"{len(error_overdue)} rule(s) critically overdue"
        
        if manual_tasks:
            return f"{len(manual_tasks)} manual task(s) need attention"
        
        if spec_tasks:
            return f"{len(spec_tasks)} spec task(s) pending"
        
        if stale_reviews:
            return f"{len(stale_reviews)} review(s) stale"
        
        warn_overdue = [d for d in overdue_rules if d.overdue_level == "warn"]
        if warn_overdue:
            return f"{len(warn_overdue)} rule(s) overdue"
        
        return None

    def _is_quiet_hours(self, now: datetime, config: SchedulerConfig) -> bool:
        """Check if current time is within quiet hours."""
        try:
            current_time = now.time()
            quiet_start = datetime.strptime(config.quiet_hours_start, "%H:%M").time()
            quiet_end = datetime.strptime(config.quiet_hours_end, "%H:%M").time()

            if quiet_start <= quiet_end:
                return quiet_start <= current_time <= quiet_end
            else:
                # Crosses midnight (e.g., 22:00 - 07:00)
                return current_time >= quiet_start or current_time <= quiet_end
        except Exception:
            return False

    def _get_timezone(self, timezone_str: str | None) -> ZoneInfo | None:
        """Get timezone from config or system default."""
        if timezone_str:
            try:
                return ZoneInfo(timezone_str)
            except Exception:
                pass
        try:
            # Try system timezone
            import time
            return ZoneInfo(time.tzname[0])
        except Exception:
            return None

    def _load_scheduler_state(self, repo_root: Path) -> SchedulerState:
        """Load scheduler state from project automation dir."""
        state_path = repo_root / ".github" / "automation" / "scheduler_state.json"
        if state_path.exists():
            try:
                data = json.loads(state_path.read_text())
                if isinstance(data, dict):
                    return SchedulerState.from_dict(data)
            except Exception:
                pass
        return SchedulerState()

    def _save_scheduler_state(self, repo_root: Path, state: SchedulerState) -> None:
        """Save scheduler state to project automation dir."""
        state_path = repo_root / ".github" / "automation" / "scheduler_state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state.to_dict(), indent=2))

    def _write_status_files(self, cycle_result: GlobalCycleResult, started_dt: datetime) -> None:
        """Write monitoring status files for SwiftBar."""
        # Global status
        global_status = {
            "last_started_at": cycle_result.started_at,
            "last_finished_at": cycle_result.finished_at,
            "last_result": cycle_result.result,
            "last_exit_code": 0 if cycle_result.result == "ok" else 1,
            "last_duration_sec": int((datetime.now() - started_dt).total_seconds()),
            "project_count": len(cycle_result.project_results),
            "due_count": sum(len([d for d in p.due_rules if d.is_due]) for p in cycle_result.project_results),
            "overdue_count": sum(
                len([d for d in p.due_rules if d.overdue_level != "none"])
                for p in cycle_result.project_results
            ),
            "manual_attention_count": sum(len(p.reminders) for p in cycle_result.project_results),
            "last_top_alert": self._compute_top_alert(cycle_result),
            "last_error": cycle_result.errors[0] if cycle_result.errors else None,
            "runs": {
                "total": sum(1 for p in cycle_result.project_results),
                "successes": len([p for p in cycle_result.project_results if p.error is None]),
                "failures": len([p for p in cycle_result.project_results if p.error is not None]),
            },
        }
        
        global_path = self.monitoring_dir / "status.json"
        global_path.parent.mkdir(parents=True, exist_ok=True)
        global_path.write_text(json.dumps(global_status, indent=2))

        # Per-project status
        projects_dir = self.monitoring_dir / "projects"
        projects_dir.mkdir(parents=True, exist_ok=True)

        for project_result in cycle_result.project_results:
            # Get attention summary from orchestrator result
            attention_summary = project_result.orchestrator_result.get("attention_summary", {})
            
            project_status = {
                "website_id": project_result.website_id,
                "due_rules": [
                    {
                        "rule_id": r.rule.id,
                        "next_due_at": r.next_due_at.isoformat(),
                        "is_due": r.is_due,
                        "overdue_level": r.overdue_level,
                    }
                    for r in project_result.due_rules
                ],
                "open_manual_count": len([t for t in project_result.reminders if t.get("type") == "manual_task"]),
                "open_spec_count": len([t for t in project_result.reminders if t.get("type") == "spec_task"]),
                "open_review_count": len([t for t in project_result.reminders if t.get("type") == "stale_review"]),
                "tasks_created_this_cycle": len([t for t in project_result.tasks_created if t.success]),
                "orchestrator_processed": project_result.orchestrator_result.get("processed", 0),
                "orchestrator_succeeded": project_result.orchestrator_result.get("succeeded", 0),
                "orchestrator_failed": project_result.orchestrator_result.get("failed", 0),
                "orchestrator_blocked": project_result.orchestrator_result.get("blocked", 0),
                "new_reddit_opportunities": project_result.orchestrator_result.get("new_reddit_opportunities", 0),
                "attention_summary": attention_summary,
                "top_priority": attention_summary.get("top_priority"),
            }
            
            project_path = projects_dir / f"{project_result.website_id}.json"
            project_path.write_text(json.dumps(project_status, indent=2))

    def _compute_top_alert(self, cycle_result: GlobalCycleResult) -> str | None:
        """Compute the top-level alert message for display."""
        if cycle_result.errors:
            return f"Errors: {len(cycle_result.errors)}"
        
        overdue = sum(
            len([d for d in p.due_rules if d.overdue_level != "none"])
            for p in cycle_result.project_results
        )
        if overdue:
            return f"Overdue: {overdue}"
        
        manual = sum(len(p.reminders) for p in cycle_result.project_results)
        if manual:
            return f"Needs attention: {manual}"
        
        if cycle_result.total_tasks_created:
            return f"Created: {cycle_result.total_tasks_created} tasks"
        
        return None
