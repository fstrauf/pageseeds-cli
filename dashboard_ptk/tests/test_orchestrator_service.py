"""Tests for orchestrator loop behavior and run artifacts."""
from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dashboard.engine.orchestrator import OrchestratorService


@dataclass
class _Task:
    id: str
    type: str
    title: str
    phase: str
    status: str = "todo"
    priority: str = "medium"
    created_at: str = ""
    completed_at: str | None = None

    def is_unlocked(self, _completed_ids: set) -> bool:
        return True


class _TaskList:
    def __init__(self, repo_root: Path, tasks: list[_Task]):
        self.project = type("Project", (), {"website_id": "test"})()
        self.automation_dir = repo_root / ".github" / "automation"
        self.automation_dir.mkdir(parents=True, exist_ok=True)
        self.task_results_dir = self.automation_dir / "task_results"
        self.task_results_dir.mkdir(parents=True, exist_ok=True)
        self.tasks = tasks

    def load(self) -> None:
        return None

    def save(self) -> None:
        return None

    def get_ready(self) -> list[_Task]:
        return [task for task in self.tasks if task.status == "todo"]


class _Executor:
    def execute_task(self, task: _Task) -> bool:
        task.status = "done"
        task.completed_at = datetime.now().isoformat()
        return True


class _RunnerWithContext:
    def __init__(self):
        self.context_history: list[dict] = []

    def set_execution_context(self, context: dict) -> None:
        self.context_history.append(dict(context))


def test_orchestrator_stops_when_only_policy_blocked_tasks_remain() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir) / "repo"
        repo_root.mkdir(parents=True, exist_ok=True)

        # Two tasks: collect_gsc is allowed and should run first, research_keywords blocked by default policy.
        tasks = [
            _Task(
                id="T-1",
                type="collect_gsc",
                title="Collect GSC",
                phase="collection",
                priority="high",
                created_at="2026-03-01T00:00:00",
            ),
            _Task(
                id="T-2",
                type="research_keywords",
                title="Research keywords",
                phase="research",
                priority="medium",
                created_at="2026-03-01T00:01:00",
            ),
        ]
        task_list = _TaskList(repo_root, tasks)
        project = type("Project", (), {"repo_root": str(repo_root), "website_id": "test"})()
        service = OrchestratorService(
            task_list=task_list,
            project=project,
            executor=_Executor(),
            runners={},
        )

        result = service.run(max_steps=5, reddit_autopost=False)

        assert result.status == "paused"
        assert result.reason == "no_policy_eligible_tasks"
        assert result.processed == 1
        assert result.succeeded == 1
        assert result.blocked >= 1

        summary_json = Path(result.summary_json)
        summary_md = Path(result.summary_markdown)
        events_path = Path(result.events_path)
        assert summary_json.exists()
        assert summary_md.exists()
        assert events_path.exists()
        assert "Orchestration Run" in summary_md.read_text()


def test_orchestrator_sets_non_interactive_runner_context() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir) / "repo"
        repo_root.mkdir(parents=True, exist_ok=True)

        tasks = [
            _Task(
                id="T-1",
                type="collect_gsc",
                title="Collect GSC",
                phase="collection",
                priority="high",
                created_at="2026-03-01T00:00:00",
            ),
        ]
        task_list = _TaskList(repo_root, tasks)
        project = type("Project", (), {"repo_root": str(repo_root), "website_id": "test"})()
        runner = _RunnerWithContext()
        service = OrchestratorService(
            task_list=task_list,
            project=project,
            executor=_Executor(),
            runners={"collection": runner},
        )

        result = service.run(max_steps=1, reddit_autopost=False)

        assert result.processed == 1
        assert runner.context_history, "expected execution context updates"
        assert any(ctx.get("non_interactive") is True for ctx in runner.context_history)
        assert runner.context_history[-1] == {}


if __name__ == "__main__":
    test_orchestrator_stops_when_only_policy_blocked_tasks_remain()
    test_orchestrator_sets_non_interactive_runner_context()
    print("ok")
