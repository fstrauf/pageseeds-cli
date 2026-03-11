"""Tests for scheduler service cycle execution."""
from __future__ import annotations

import json
import inspect
import importlib.util
import os
import sys
import tempfile
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dashboard.engine.scheduler_service import SchedulerService, GlobalCycleResult, ProjectCycleResult
from dashboard.engine.types import SchedulerConfig


class TestSchedulerServiceCycle:
    """Test full scheduler cycle execution."""

    def test_scheduler_service_loads_projects(self):
        """SchedulerService loads projects from config file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            projects_config = Path(tmpdir) / "projects.json"
            output_dir = Path(tmpdir) / "output"
            
            # Write test projects config
            projects = {
                "site1": {
                    "website_id": "site1",
                    "repo_root": "/tmp/site1",
                    "name": "Site 1"
                },
                "site2": {
                    "website_id": "site2", 
                    "repo_root": "/tmp/site2",
                    "name": "Site 2"
                }
            }
            projects_config.write_text(json.dumps(projects, indent=2))
            
            service = SchedulerService(
                projects_config_path=projects_config,
                output_dir=output_dir,
            )
            
            loaded = service._load_projects()
            
            assert len(loaded) == 2
            assert "site1" in loaded
            assert "site2" in loaded

    def test_scheduler_service_handles_missing_config(self):
        """SchedulerService handles missing projects config gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            projects_config = Path(tmpdir) / "nonexistent.json"
            output_dir = Path(tmpdir) / "output"
            
            service = SchedulerService(
                projects_config_path=projects_config,
                output_dir=output_dir,
            )
            
            loaded = service._load_projects()
            
            assert loaded == {}

    def test_scheduler_service_handles_list_format_projects(self):
        """SchedulerService handles projects config as list format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            projects_config = Path(tmpdir) / "projects.json"
            output_dir = Path(tmpdir) / "output"
            
            # Write projects config as list (alternative format)
            projects = [
                {"website_id": "site1", "repo_root": "/tmp/site1"},
                {"website_id": "site2", "repo_root": "/tmp/site2"},
            ]
            projects_config.write_text(json.dumps(projects, indent=2))
            
            service = SchedulerService(
                projects_config_path=projects_config,
                output_dir=output_dir,
            )
            
            loaded = service._load_projects()
            
            assert len(loaded) == 2
            assert "site1" in loaded
            assert "site2" in loaded

    def test_global_cycle_result_to_dict(self):
        """GlobalCycleResult can be serialized to dict."""
        from datetime import datetime
        
        project_result = ProjectCycleResult(
            website_id="test_site",
            preflight_ok=True,
            due_rules=[],
            tasks_created=[],
            orchestrator_run=False,
        )
        
        result = GlobalCycleResult(
            started_at=datetime.now().isoformat(),
            finished_at=datetime.now().isoformat(),
            result="ok",
            project_results=[project_result],
            total_tasks_created=0,
            total_orchestrator_runs=0,
            errors=[],
        )
        
        data = result.to_dict()
        
        assert data["result"] == "ok"
        assert data["total_tasks_created"] == 0
        assert len(data["project_results"]) == 1
        assert data["project_results"][0]["website_id"] == "test_site"

    def test_project_cycle_result_to_dict(self):
        """ProjectCycleResult can be serialized to dict."""
        from dashboard.engine.scheduler_service import DueRuleResult, TaskCreationResult
        from dashboard.engine.types import SchedulerRule
        from datetime import datetime
        
        rule = SchedulerRule("test_rule", "test_task", "create_task", 168)
        due_result = DueRuleResult(
            rule=rule,
            is_due=True,
            next_due_at=datetime.now(),
            reason="Test reason",
            overdue_level="none",
        )
        
        task_result = TaskCreationResult(
            rule_id="test_rule",
            success=True,
            task_id="task_123",
            message="Created successfully",
        )
        
        project_result = ProjectCycleResult(
            website_id="test_site",
            preflight_ok=True,
            due_rules=[due_result],
            tasks_created=[task_result],
            orchestrator_run=True,
            orchestrator_result={"processed": 1},
            reminders=[{"type": "test", "message": "Test reminder"}],
        )
        
        data = project_result.to_dict()
        
        assert data["website_id"] == "test_site"
        assert data["preflight_ok"] is True
        assert len(data["due_rules"]) == 1
        assert len(data["tasks_created"]) == 1
        assert data["orchestrator_run"] is True
        assert len(data["reminders"]) == 1

    def test_run_orchestrator_builds_runner_registry(self):
        """Scheduler orchestrator path should build concrete runners."""
        if importlib.util.find_spec("rich") is None:
            return
        if importlib.util.find_spec("prompt_toolkit") is None:
            return

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / ".github" / "automation").mkdir(parents=True, exist_ok=True)
            (repo_root / ".github" / "automation" / "task_list.json").write_text(
                json.dumps({"schema_version": 4, "version": "4.0", "project_id": "test", "tasks": [], "metadata": {}})
            )

            service = SchedulerService(
                projects_config_path=Path("/tmp/test.json"),
                output_dir=Path(tmpdir) / "output",
            )

            captured: dict[str, dict] = {}

            class FakeExecutionEngine:
                def __init__(self, task_list, project, runners):
                    captured["executor_runners"] = runners

            class FakeOrchestratorService:
                def __init__(self, task_list, project, executor, runners):
                    captured["orchestrator_runners"] = runners

                def run(self, max_steps=0):
                    return SimpleNamespace(
                        run_id="run_1",
                        status="complete",
                        reason="no_ready_tasks",
                        processed=0,
                        succeeded=0,
                        failed=0,
                        blocked=0,
                    )

            with patch("dashboard.engine.executor.ExecutionEngine", FakeExecutionEngine), patch(
                "dashboard.engine.orchestrator.OrchestratorService", FakeOrchestratorService
            ):
                result = service._run_orchestrator(
                    repo_root=repo_root,
                    policy=SimpleNamespace(max_steps_per_run=1),
                    automation_dir=repo_root / ".github" / "automation",
                    website_id="test",
                )

            assert result["status"] == "complete"
            assert captured["executor_runners"], "Expected non-empty runner registry"
            assert "collection" in captured["executor_runners"]
            assert captured["orchestrator_runners"] == captured["executor_runners"]


class TestSchedulerStatusOutput:
    """Test scheduler status file output."""

    def test_status_files_written_after_cycle(self):
        """Status files are written after cycle completes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            projects_config = Path(tmpdir) / "projects.json"
            output_dir = Path(tmpdir) / "output"
            
            # Create minimal projects config with non-existent paths
            # (cycle will fail preflight but should still write status)
            projects = {"test_site": {"repo_root": "/nonexistent/path"}}
            projects_config.write_text(json.dumps(projects))
            
            service = SchedulerService(
                projects_config_path=projects_config,
                output_dir=output_dir,
            )
            
            from datetime import datetime
            result = GlobalCycleResult(
                started_at=datetime.now().isoformat(),
                finished_at=datetime.now().isoformat(),
                result="error",
                project_results=[],
                total_tasks_created=0,
                total_orchestrator_runs=0,
                errors=["Test error"],
            )
            
            service._write_status_files(result, datetime.now())
            
            # Check global status file was written
            global_status = output_dir / "monitoring" / "seo_scheduler" / "status.json"
            assert global_status.exists()
            
            data = json.loads(global_status.read_text())
            assert data["last_result"] == "error"
            assert data["last_error"] == "Test error"

    def test_global_status_schema(self):
        """Global status file follows expected schema."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "output"
            
            service = SchedulerService(
                projects_config_path=Path("/tmp/test.json"),
                output_dir=output_dir,
            )
            
            from datetime import datetime
            result = GlobalCycleResult(
                started_at="2024-01-01T00:00:00",
                finished_at="2024-01-01T00:01:00",
                result="ok",
                project_results=[],
                total_tasks_created=3,
                total_orchestrator_runs=2,
                errors=[],
            )
            
            started = datetime.now()
            service._write_status_files(result, started)
            
            global_status = output_dir / "monitoring" / "seo_scheduler" / "status.json"
            data = json.loads(global_status.read_text())
            
            # Check required fields per PLAN.md schema
            assert "last_started_at" in data
            assert "last_finished_at" in data
            assert "last_result" in data
            assert "last_exit_code" in data
            assert "last_duration_sec" in data
            assert "project_count" in data
            assert "due_count" in data
            assert "overdue_count" in data
            assert "manual_attention_count" in data
            assert "last_top_alert" in data
            assert "runs" in data
            assert data["runs"]["total"] >= 0
            assert data["runs"]["successes"] >= 0
            assert data["runs"]["failures"] >= 0

    def test_project_status_schema(self):
        """Per-project status file follows expected schema."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "output"
            
            service = SchedulerService(
                projects_config_path=Path("/tmp/test.json"),
                output_dir=output_dir,
            )
            
            from datetime import datetime
            from dashboard.engine.scheduler_service import DueRuleResult
            from dashboard.engine.types import SchedulerRule
            
            rule = SchedulerRule("test_rule", "test_task", "create_task", 168)
            due_result = DueRuleResult(
                rule=rule,
                is_due=True,
                next_due_at=datetime.now(),
                reason="Test",
                overdue_level="warn",
            )
            
            project_result = ProjectCycleResult(
                website_id="test_site",
                preflight_ok=True,
                due_rules=[due_result],
                tasks_created=[],
                orchestrator_run=True,
                orchestrator_result={"processed": 5, "succeeded": 4, "failed": 1, "blocked": 0},
                reminders=[{"type": "manual_task"}, {"type": "spec_task"}],
            )
            
            result = GlobalCycleResult(
                started_at="2024-01-01T00:00:00",
                finished_at="2024-01-01T00:01:00",
                result="ok",
                project_results=[project_result],
                total_tasks_created=0,
                total_orchestrator_runs=0,
                errors=[],
            )
            
            service._write_status_files(result, datetime.now())
            
            project_status = output_dir / "monitoring" / "seo_scheduler" / "projects" / "test_site.json"
            assert project_status.exists()
            
            data = json.loads(project_status.read_text())
            
            # Check required fields per PLAN.md schema
            assert data["website_id"] == "test_site"
            assert "due_rules" in data
            assert len(data["due_rules"]) == 1
            assert "next_due_at" in data["due_rules"][0]
            assert "is_due" in data["due_rules"][0]
            assert "overdue_level" in data["due_rules"][0]
            assert "open_manual_count" in data
            assert "open_spec_count" in data
            assert "open_review_count" in data
            assert "tasks_created_this_cycle" in data
            assert "orchestrator_processed" in data
            assert "orchestrator_succeeded" in data
            assert "orchestrator_failed" in data
            assert "orchestrator_blocked" in data
            assert "new_reddit_opportunities" in data


class TestSchedulerReminders:
    """Test reminder building logic."""

    def _create_task_state_with_tasks(self, task_defs: list[dict]) -> "TaskState":
        """Helper to create TaskState with given tasks."""
        from dashboard.engine.types import TaskState, TaskRecord
        
        task_state = TaskState()
        for defn in task_defs:
            task = TaskRecord(
                id=defn["id"],
                type=defn["type"],
                title=defn.get("title", "Untitled"),
                phase=defn.get("phase", "implementation"),
                status=defn.get("status", "todo"),
                execution_mode=defn.get("execution_mode", "manual"),
            )
            task_state.tasks.append(task)
        return task_state

    def test_build_reminders_detects_manual_tasks(self):
        """Reminders include manual execution mode tasks."""
        service = SchedulerService(
            projects_config_path=Path("/tmp/test.json"),
            output_dir=Path("/tmp/output"),
        )
        
        task_state = self._create_task_state_with_tasks([
            {"id": "manual1", "type": "custom_task", "status": "todo", "execution_mode": "manual", "title": "Manual Task"},
            {"id": "auto1", "type": "auto_task", "status": "todo", "execution_mode": "automatic", "title": "Auto Task"},
        ])
        
        reminders = service._build_reminders(task_state, [], SchedulerConfig.default())
        
        manual_reminders = [r for r in reminders if r.get("type") == "manual_task"]
        assert len(manual_reminders) == 1
        assert manual_reminders[0]["task_id"] == "manual1"

    def test_build_reminders_detects_spec_tasks(self):
        """Reminders include spec-type tasks."""
        service = SchedulerService(
            projects_config_path=Path("/tmp/test.json"),
            output_dir=Path("/tmp/output"),
        )
        
        task_state = self._create_task_state_with_tasks([
            {"id": "spec1", "type": "content_spec", "status": "todo", "execution_mode": "manual", "title": "Spec Task"},
            {"id": "normal", "type": "normal_task", "status": "todo", "execution_mode": "manual", "title": "Normal Task"},
        ])
        
        reminders = service._build_reminders(task_state, [], SchedulerConfig.default())
        
        spec_reminders = [r for r in reminders if r.get("type") == "spec_task"]
        assert len(spec_reminders) == 1
        assert spec_reminders[0]["task_id"] == "spec1"


class TestSchedulerNotifications:
    """Tests for Reddit opportunity notification behavior."""

    def test_count_open_reddit_reply_tasks(self):
        from dashboard.engine.types import TaskState, TaskRecord

        service = SchedulerService(
            projects_config_path=Path("/tmp/test.json"),
            output_dir=Path("/tmp/output"),
        )

        task_state = TaskState(
            tasks=[
                TaskRecord(id="r1", type="reddit_reply", title="r1", phase="research", status="todo"),
                TaskRecord(id="r2", type="reddit_reply", title="r2", phase="research", status="in_progress"),
                TaskRecord(id="r3", type="reddit_reply", title="r3", phase="research", status="review"),
                TaskRecord(id="r4", type="reddit_reply", title="r4", phase="research", status="done"),
                TaskRecord(id="x1", type="collect_gsc", title="x1", phase="collection", status="todo"),
            ]
        )

        assert service._count_open_reddit_reply_tasks(task_state) == 3

    def test_notify_macos_skips_non_darwin(self):
        service = SchedulerService(
            projects_config_path=Path("/tmp/test.json"),
            output_dir=Path("/tmp/output"),
        )

        with patch("dashboard.engine.scheduler_service.sys.platform", "linux"):
            assert service._notify_macos_reddit_opportunities("coffee", 2) is False

    def test_notify_macos_invokes_osascript_on_darwin(self):
        service = SchedulerService(
            projects_config_path=Path("/tmp/test.json"),
            output_dir=Path("/tmp/output"),
        )

        with patch("dashboard.engine.scheduler_service.sys.platform", "darwin"), \
             patch("dashboard.engine.scheduler_service.shutil.which", return_value="/usr/bin/osascript"), \
             patch("dashboard.engine.scheduler_service.subprocess.run", return_value=SimpleNamespace(returncode=0)) as run_mock:
            sent = service._notify_macos_reddit_opportunities("coffee", 3)

        assert sent is True
        assert run_mock.call_count == 1
        cmd = run_mock.call_args.args[0]
        assert cmd[0] == "osascript"


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
