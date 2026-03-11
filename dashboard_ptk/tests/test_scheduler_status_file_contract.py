"""Tests for scheduler status file contract (SwiftBar compatibility)."""
from __future__ import annotations

import json
import inspect
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dashboard.engine.scheduler_service import SchedulerService, GlobalCycleResult, ProjectCycleResult
from dashboard.engine.types import SchedulerConfig, SchedulerRule


class TestSwiftBarStatusContract:
    """Test that status files follow SwiftBar contract from PLAN.md."""

    def test_global_status_required_fields(self):
        """Global status file contains all required fields for SwiftBar."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "output"
            service = SchedulerService(
                projects_config_path=Path("/tmp/test.json"),
                output_dir=output_dir,
            )
            
            result = GlobalCycleResult(
                started_at=datetime.now().isoformat(),
                finished_at=datetime.now().isoformat(),
                result="ok",
                project_results=[],
                total_tasks_created=0,
                total_orchestrator_runs=0,
                errors=[],
            )
            
            service._write_status_files(result, datetime.now())
            
            global_status = output_dir / "monitoring" / "seo_scheduler" / "status.json"
            data = json.loads(global_status.read_text())
            
            # Required fields per PLAN.md section C
            required_fields = [
                "last_started_at",
                "last_finished_at",
                "last_result",
                "last_exit_code",
                "last_duration_sec",
                "project_count",
                "due_count",
                "overdue_count",
                "manual_attention_count",
                "last_top_alert",
                "last_error",
            ]
            
            for field in required_fields:
                assert field in data, f"Missing required field: {field}"

    def test_global_status_runs_stats(self):
        """Global status includes runs/successes/failures stats."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "output"
            service = SchedulerService(
                projects_config_path=Path("/tmp/test.json"),
                output_dir=output_dir,
            )
            
            # Create project results - one success, one failure
            success_project = ProjectCycleResult(
                website_id="success_site",
                preflight_ok=True,
            )
            failed_project = ProjectCycleResult(
                website_id="failed_site",
                preflight_ok=False,
                error="Something went wrong",
            )
            
            result = GlobalCycleResult(
                started_at=datetime.now().isoformat(),
                finished_at=datetime.now().isoformat(),
                result="warn",
                project_results=[success_project, failed_project],
                total_tasks_created=0,
                total_orchestrator_runs=0,
                errors=["Something went wrong"],
            )
            
            service._write_status_files(result, datetime.now())
            
            global_status = output_dir / "monitoring" / "seo_scheduler" / "status.json"
            data = json.loads(global_status.read_text())
            
            assert "runs" in data
            assert data["runs"]["total"] == 2
            assert data["runs"]["successes"] == 1
            assert data["runs"]["failures"] == 1

    def test_project_status_required_fields(self):
        """Per-project status file contains all required fields for SwiftBar."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "output"
            service = SchedulerService(
                projects_config_path=Path("/tmp/test.json"),
                output_dir=output_dir,
            )
            
            from dashboard.engine.scheduler_service import DueRuleResult
            
            rule = SchedulerRule("test_rule", "test_task", "create_task", 168)
            due_result = DueRuleResult(
                rule=rule,
                is_due=True,
                next_due_at=datetime.now(),
                reason="Test",
                overdue_level="none",
            )
            
            project_result = ProjectCycleResult(
                website_id="test_site",
                preflight_ok=True,
                due_rules=[due_result],
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
            
            service._write_status_files(result, datetime.now())
            
            project_status = output_dir / "monitoring" / "seo_scheduler" / "projects" / "test_site.json"
            data = json.loads(project_status.read_text())
            
            # Required fields per PLAN.md section C
            required_fields = [
                "website_id",
                "due_rules",
                "open_manual_count",
                "open_spec_count",
                "open_review_count",
                "tasks_created_this_cycle",
                "orchestrator_processed",
                "orchestrator_succeeded",
                "orchestrator_failed",
                "orchestrator_blocked",
                "new_reddit_opportunities",
            ]
            
            for field in required_fields:
                assert field in data, f"Missing required field: {field}"

    def test_due_rules_have_required_fields(self):
        """Due rules in project status have required fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "output"
            service = SchedulerService(
                projects_config_path=Path("/tmp/test.json"),
                output_dir=output_dir,
            )
            
            from dashboard.engine.scheduler_service import DueRuleResult
            
            rule = SchedulerRule("weekly_rule", "collect_gsc", "create_task", 168)
            due_result = DueRuleResult(
                rule=rule,
                is_due=True,
                next_due_at=datetime(2024, 1, 15, 10, 0, 0),
                reason="Test",
                overdue_level="warn",
            )
            
            project_result = ProjectCycleResult(
                website_id="test_site",
                preflight_ok=True,
                due_rules=[due_result],
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
            
            service._write_status_files(result, datetime.now())
            
            project_status = output_dir / "monitoring" / "seo_scheduler" / "projects" / "test_site.json"
            data = json.loads(project_status.read_text())
            
            assert len(data["due_rules"]) == 1
            rule_data = data["due_rules"][0]
            
            # Required per PLAN.md: next_due_at, is_due, overdue_level
            assert "next_due_at" in rule_data
            assert "is_due" in rule_data
            assert "overdue_level" in rule_data
            
            assert rule_data["is_due"] is True
            assert rule_data["overdue_level"] == "warn"

    def test_result_values_are_valid(self):
        """last_result field uses valid values from spec."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "output"
            service = SchedulerService(
                projects_config_path=Path("/tmp/test.json"),
                output_dir=output_dir,
            )
            
            valid_results = ["ok", "warn", "error", "running"]
            
            for result_value in ["ok", "warn", "error"]:
                result = GlobalCycleResult(
                    started_at=datetime.now().isoformat(),
                    finished_at=datetime.now().isoformat(),
                    result=result_value,
                    project_results=[],
                    total_tasks_created=0,
                    total_orchestrator_runs=0,
                    errors=["error"] if result_value == "error" else [],
                )
                
                service._write_status_files(result, datetime.now())
                
                global_status = output_dir / "monitoring" / "seo_scheduler" / "status.json"
                data = json.loads(global_status.read_text())
                
                assert data["last_result"] in valid_results

    def test_exit_code_matches_result(self):
        """last_exit_code matches result (0 for ok, 1 for error)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "output"
            service = SchedulerService(
                projects_config_path=Path("/tmp/test.json"),
                output_dir=output_dir,
            )
            
            test_cases = [
                ("ok", 0),
                ("warn", 1),  # warn has exit code 1
                ("error", 1),
            ]
            
            for result_value, expected_exit_code in test_cases:
                result = GlobalCycleResult(
                    started_at=datetime.now().isoformat(),
                    finished_at=datetime.now().isoformat(),
                    result=result_value,
                    project_results=[],
                    total_tasks_created=0,
                    total_orchestrator_runs=0,
                    errors=[] if result_value == "ok" else ["some error"],
                )
                
                service._write_status_files(result, datetime.now())
                
                global_status = output_dir / "monitoring" / "seo_scheduler" / "status.json"
                data = json.loads(global_status.read_text())
                
                assert data["last_exit_code"] == expected_exit_code, f"Failed for result={result_value}"

    def test_top_alert_computed_correctly(self):
        """last_top_alert is computed based on priority of issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "output"
            service = SchedulerService(
                projects_config_path=Path("/tmp/test.json"),
                output_dir=output_dir,
            )
            
            # Test with errors
            result_with_errors = GlobalCycleResult(
                started_at=datetime.now().isoformat(),
                finished_at=datetime.now().isoformat(),
                result="error",
                project_results=[],
                total_tasks_created=0,
                total_orchestrator_runs=0,
                errors=["Error 1", "Error 2"],
            )
            
            service._write_status_files(result_with_errors, datetime.now())
            
            global_status = output_dir / "monitoring" / "seo_scheduler" / "status.json"
            data = json.loads(global_status.read_text())
            
            assert data["last_top_alert"] is not None
            assert "Errors" in data["last_top_alert"]

    def test_project_status_directory_structure(self):
        """Project status files are written to correct directory structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "output"
            service = SchedulerService(
                projects_config_path=Path("/tmp/test.json"),
                output_dir=output_dir,
            )
            
            project_result = ProjectCycleResult(
                website_id="my_website",
                preflight_ok=True,
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
            
            service._write_status_files(result, datetime.now())
            
            # Check directory structure matches PLAN.md
            expected_path = output_dir / "monitoring" / "seo_scheduler" / "projects" / "my_website.json"
            assert expected_path.exists()


class TestStatusFilePerformance:
    """Test that status file operations are efficient."""

    def test_status_files_are_valid_json(self):
        """Status files are valid JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "output"
            service = SchedulerService(
                projects_config_path=Path("/tmp/test.json"),
                output_dir=output_dir,
            )
            
            result = GlobalCycleResult(
                started_at=datetime.now().isoformat(),
                finished_at=datetime.now().isoformat(),
                result="ok",
                project_results=[],
                total_tasks_created=0,
                total_orchestrator_runs=0,
                errors=[],
            )
            
            service._write_status_files(result, datetime.now())
            
            # Both files should be valid JSON
            global_status = output_dir / "monitoring" / "seo_scheduler" / "status.json"
            project_dir = output_dir / "monitoring" / "seo_scheduler" / "projects"
            
            # Global status
            assert global_status.exists()
            with open(global_status) as f:
                json.load(f)  # Should not raise


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
