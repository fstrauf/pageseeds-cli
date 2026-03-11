"""Tests for schema migration and task store v4 persistence."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dashboard.engine.task_store import TaskStore


def test_v3_to_v4_migration_roundtrip() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        task_list_path = Path(tmp) / "task_list.json"
        legacy = {
            "version": "3.0",
            "project_id": "coffee",
            "tasks": [
                {
                    "id": "COF-001",
                    "type": "write_article",
                    "title": "Write article: test",
                    "phase": "implementation",
                    "status": "todo",
                    "depends_on": "COF-000",
                    "input_artifact": "artifacts/in.json",
                }
            ],
            "metadata": {"next_task_sequence": 2},
        }
        task_list_path.write_text(json.dumps(legacy, indent=2))

        store = TaskStore(task_list_path, project_id="coffee")
        state = store.load()

        assert state.schema_version == 4
        assert state.version == "4.0"
        assert len(state.tasks) == 1
        task = state.tasks[0]
        assert task.depends_on == ["COF-000"]
        assert task.workflow_key == "write_article"
        assert task.agent_policy in {"required", "optional", "none"}
        assert task.artifacts

        persisted = json.loads(task_list_path.read_text())
        assert persisted["schema_version"] == 4
        assert isinstance(persisted["tasks"][0]["depends_on"], list)


if __name__ == "__main__":
    test_v3_to_v4_migration_roundtrip()
    print("ok")
