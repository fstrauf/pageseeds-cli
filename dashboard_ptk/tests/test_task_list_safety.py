"""Tests for TaskList safety behavior on load failures."""
from __future__ import annotations

import json
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_task_list_refuses_save_after_load_error() -> None:
    if importlib.util.find_spec("rich") is None:
        print("skipped (rich not installed)")
        return

    from dashboard.models import Project
    from dashboard.storage import TaskList

    with tempfile.TemporaryDirectory() as tmp:
        repo_root = Path(tmp)
        automation_dir = repo_root / ".github" / "automation"
        automation_dir.mkdir(parents=True, exist_ok=True)
        task_list_path = automation_dir / "task_list.json"
        task_list_path.write_text("{not-valid-json")

        project = Project(name="Test", website_id="test", repo_root=str(repo_root))
        task_list = TaskList(project)

        assert task_list._load_error is not None
        try:
            task_list.save()
            raise AssertionError("Expected RuntimeError when saving after load failure")
        except RuntimeError as exc:
            assert "Refusing to save task state" in str(exc)


if __name__ == "__main__":
    test_task_list_refuses_save_after_load_error()
    print("ok")
