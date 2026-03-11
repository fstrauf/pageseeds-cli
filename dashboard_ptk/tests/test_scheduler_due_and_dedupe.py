"""Tests for scheduler due evaluation and deduplication."""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta
import inspect
from pathlib import Path
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dashboard.engine.scheduler_service import SchedulerService
from dashboard.engine.types import (
    SchedulerConfig,
    SchedulerRule,
    SchedulerState,
    SchedulerStats,
    RuleState,
    TaskRecord,
    TaskState,
)


class TestSchedulerDueEvaluation:
    """Test due rule evaluation logic."""

    def test_rule_is_due_when_never_run(self):
        """Rule is due when it has never been run before."""
        config = SchedulerConfig.default()
        state = SchedulerState()
        task_state = TaskState()
        
        service = SchedulerService(
            projects_config_path=Path("/tmp/test.json"),
            output_dir=Path("/tmp/output"),
        )
        
        now = datetime.now()
        rule = SchedulerRule("test_rule", "test_task", "create_task", 168)
        config.rules = [rule]
        
        results = service._evaluate_due_rules(config.rules, state, task_state, now, config)
        
        assert len(results) == 1
        assert results[0].is_due is True
        assert results[0].rule.id == "test_rule"

    def test_rule_not_due_within_cadence(self):
        """Rule is not due when run within cadence period."""
        config = SchedulerConfig.default()
        state = SchedulerState()
        task_state = TaskState()
        
        # Set last run to 1 hour ago (within 168h cadence)
        rule_state = RuleState()
        rule_state.last_task_created_at = (datetime.now() - timedelta(hours=1)).isoformat()
        state.rules["test_rule"] = rule_state
        
        service = SchedulerService(
            projects_config_path=Path("/tmp/test.json"),
            output_dir=Path("/tmp/output"),
        )
        
        now = datetime.now()
        rule = SchedulerRule("test_rule", "test_task", "create_task", 168)
        config.rules = [rule]
        
        results = service._evaluate_due_rules(config.rules, state, task_state, now, config)
        
        assert len(results) == 1
        assert results[0].is_due is False

    def test_rule_due_after_cadence(self):
        """Rule is due when cadence period has elapsed."""
        config = SchedulerConfig.default()
        state = SchedulerState()
        task_state = TaskState()
        
        # Set last run to 200 hours ago (beyond 168h cadence)
        rule_state = RuleState()
        rule_state.last_task_created_at = (datetime.now() - timedelta(hours=200)).isoformat()
        state.rules["test_rule"] = rule_state
        
        service = SchedulerService(
            projects_config_path=Path("/tmp/test.json"),
            output_dir=Path("/tmp/output"),
        )
        
        now = datetime.now()
        rule = SchedulerRule("test_rule", "test_task", "create_task", 168)
        config.rules = [rule]
        
        results = service._evaluate_due_rules(config.rules, state, task_state, now, config)
        
        assert len(results) == 1
        assert results[0].is_due is True

    def test_disabled_rule_never_due(self):
        """Disabled rule is never marked as due."""
        config = SchedulerConfig.default()
        state = SchedulerState()
        task_state = TaskState()
        
        service = SchedulerService(
            projects_config_path=Path("/tmp/test.json"),
            output_dir=Path("/tmp/output"),
        )
        
        now = datetime.now()
        rule = SchedulerRule("test_rule", "test_task", "create_task", 168, enabled=False)
        config.rules = [rule]
        
        results = service._evaluate_due_rules(config.rules, state, task_state, now, config)
        
        assert len(results) == 1
        assert results[0].is_due is False
        assert "disabled" in results[0].reason.lower()

    def test_quiet_hours_deferral(self):
        """Rule is deferred during quiet hours."""
        config = SchedulerConfig.default()
        config.quiet_hours_start = "22:00"
        config.quiet_hours_end = "07:00"
        state = SchedulerState()
        task_state = TaskState()
        
        service = SchedulerService(
            projects_config_path=Path("/tmp/test.json"),
            output_dir=Path("/tmp/output"),
        )
        
        # Simulate 23:00 (within quiet hours)
        now = datetime.now().replace(hour=23, minute=0, second=0, microsecond=0)
        rule = SchedulerRule("test_rule", "test_task", "create_task", 168)
        config.rules = [rule]
        
        results = service._evaluate_due_rules(config.rules, state, task_state, now, config)
        
        assert len(results) == 1
        assert results[0].is_due is False
        assert "quiet hours" in results[0].reason.lower()

    def test_overdue_level_calculation(self):
        """Overdue level is calculated correctly based on hours overdue."""
        config = SchedulerConfig.default()
        config.overdue_warn_after_hours = 48
        config.overdue_error_after_hours = 168
        state = SchedulerState()
        task_state = TaskState()
        
        service = SchedulerService(
            projects_config_path=Path("/tmp/test.json"),
            output_dir=Path("/tmp/output"),
        )
        
        now = datetime.now()
        
        # Test cases: (hours_overdue, expected_level)
        test_cases = [
            (0, "none"),      # Not overdue
            (24, "none"),     # Within warn threshold
            (72, "warn"),     # Beyond warn threshold
            (200, "error"),   # Beyond error threshold
        ]
        
        for hours_overdue, expected_level in test_cases:
            rule_state = RuleState()
            # Set last run so that next_due_at is hours_overdue in the past
            rule_state.last_task_created_at = (now - timedelta(hours=168 + hours_overdue)).isoformat()
            state.rules["test_rule"] = rule_state
            
            rule = SchedulerRule("test_rule", "test_task", "create_task", 168)
            config.rules = [rule]
            
            results = service._evaluate_due_rules(config.rules, state, task_state, now, config)
            
            assert len(results) == 1
            assert results[0].overdue_level == expected_level, f"Failed for hours_overdue={hours_overdue}"

    def test_reminder_only_mode_uses_reminder_anchor(self):
        """Reminder-only mode uses last_reminder_at as anchor."""
        config = SchedulerConfig.default()
        state = SchedulerState()
        task_state = TaskState()
        
        # Set last reminder to 200 hours ago (beyond 72h cadence)
        rule_state = RuleState()
        rule_state.last_reminder_at = (datetime.now() - timedelta(hours=200)).isoformat()
        rule_state.last_task_created_at = (datetime.now() - timedelta(hours=1)).isoformat()  # Recent task
        state.rules["test_rule"] = rule_state
        
        service = SchedulerService(
            projects_config_path=Path("/tmp/test.json"),
            output_dir=Path("/tmp/output"),
        )
        
        now = datetime.now()
        rule = SchedulerRule("test_rule", "test_task", "reminder_only", 72)
        config.rules = [rule]
        
        results = service._evaluate_due_rules(config.rules, state, task_state, now, config)
        
        assert len(results) == 1
        assert results[0].is_due is True  # Due because reminder anchor is old


class TestSchedulerTaskDeduplication:
    """Test task creation deduplication logic."""

    def test_no_task_created_when_open_task_exists(self):
        """No new task created when open task of same type exists."""
        config = SchedulerConfig.default()
        state = SchedulerState()
        
        # Create existing open task
        task_state = TaskState()
        existing_task = TaskRecord(
            id="existing_task",
            type="collect_gsc",
            title="Existing GSC Collection",
            phase="collection",
            status="todo",
        )
        task_state.tasks.append(existing_task)
        
        service = SchedulerService(
            projects_config_path=Path("/tmp/test.json"),
            output_dir=Path("/tmp/output"),
        )
        
        now = datetime.now()
        rule = SchedulerRule("test_rule", "collect_gsc", "create_task", 168)
        
        # Note: _create_task_for_rule is called within _process_project,
        # but we can test the deduplication logic directly
        result = service._create_task_for_rule(rule, task_state, None, state, now)
        
        assert result.success is False
        assert "exists" in result.message.lower()

    def test_task_created_when_no_open_task_exists(self):
        """New task created when no open task of same type exists."""
        import tempfile
        from dashboard.engine.task_store import TaskStore
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SchedulerConfig.default()
            state = SchedulerState()
            
            # No existing tasks
            task_list_path = Path(tmpdir) / "task_list.json"
            task_store = TaskStore(task_list_path, "test_project")
            task_state = TaskState()
            
            service = SchedulerService(
                projects_config_path=Path("/tmp/test.json"),
                output_dir=Path("/tmp/output"),
            )
            
            now = datetime.now()
            rule = SchedulerRule("test_rule", "collect_gsc", "create_task", 168)
            
            result = service._create_task_for_rule(rule, task_state, task_store, state, now)
            
            assert result.success is True
            assert result.task_id is not None

    def test_task_created_when_only_done_tasks_exist(self):
        """New task created when existing tasks are done/cancelled."""
        import tempfile
        from dashboard.engine.task_store import TaskStore
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SchedulerConfig.default()
            state = SchedulerState()
            
            # Create completed task
            task_list_path = Path(tmpdir) / "task_list.json"
            task_store = TaskStore(task_list_path, "test_project")
            task_state = TaskState()
            done_task = TaskRecord(
                id="done_task",
                type="collect_gsc",
                title="Done GSC Collection",
                phase="collection",
                status="done",
            )
            task_state.tasks.append(done_task)
            
            service = SchedulerService(
                projects_config_path=Path("/tmp/test.json"),
                output_dir=Path("/tmp/output"),
            )
            
            now = datetime.now()
            rule = SchedulerRule("test_rule", "collect_gsc", "create_task", 168)
            
            result = service._create_task_for_rule(rule, task_state, task_store, state, now)
            
            assert result.success is True
            assert result.task_id is not None

    def test_dedupe_respects_in_progress_and_review(self):
        """Dedupe considers in_progress and review as open statuses."""
        config = SchedulerConfig.default()
        state = SchedulerState()
        
        service = SchedulerService(
            projects_config_path=Path("/tmp/test.json"),
            output_dir=Path("/tmp/output"),
        )
        
        now = datetime.now()
        rule = SchedulerRule("test_rule", "collect_gsc", "create_task", 168)
        
        for status in ["in_progress", "review"]:
            task_state = TaskState()
            existing_task = TaskRecord(
                id=f"{status}_task",
                type="collect_gsc",
                title=f"{status} GSC Collection",
                phase="collection",
                status=status,
            )
            task_state.tasks.append(existing_task)
            
            result = service._create_task_for_rule(rule, task_state, None, state, now)
            
            assert result.success is False, f"Should not create task when {status} task exists"

    def test_reminder_only_rule_never_creates_task(self):
        """Reminder-only rules should emit reminders, not create tasks."""
        state = SchedulerState()
        task_state = TaskState()
        service = SchedulerService(
            projects_config_path=Path("/tmp/test.json"),
            output_dir=Path("/tmp/output"),
        )

        now = datetime.now()
        rule = SchedulerRule("test_rule", "research_keywords", "reminder_only", 168)
        result = service._create_task_for_rule(rule, task_state, None, state, now)

        assert result.success is False
        assert "does not create tasks" in result.message

    def test_emit_reminder_updates_rule_state(self):
        """Reminder emission should update reminder timestamps and status."""
        state = SchedulerState()
        service = SchedulerService(
            projects_config_path=Path("/tmp/test.json"),
            output_dir=Path("/tmp/output"),
        )

        now = datetime.now()
        rule = SchedulerRule("test_rule", "research_keywords", "reminder_only", 168)
        reminder = service._emit_reminder_for_rule(rule, state, now)

        assert reminder["type"] == "rule_reminder"
        rule_state = state.rules["test_rule"]
        assert rule_state.last_status == "reminded"
        assert rule_state.last_reminder_at == now.isoformat()


def _run_all_tests() -> None:
    module = sys.modules[__name__]
    ran = 0
    for _, cls in inspect.getmembers(module, inspect.isclass):
        if not cls.__name__.startswith("Test"):
            continue
        instance = cls()
        for name, _ in inspect.getmembers(cls, inspect.isfunction):
            if not name.startswith("test_"):
                continue
            getattr(instance, name)()
            ran += 1
    print(f"ok ({ran} tests)")


if __name__ == "__main__":
    _run_all_tests()
