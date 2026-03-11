"""Persistent task store backed by schema-v4 task_list.json."""
from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .migration import migrate_file_in_place
from .types import MigrationError, TaskState


class TaskStore:
    """Load/save task state with migration and atomic writes."""

    def __init__(self, task_list_path: Path, project_id: str):
        self.task_list_path = task_list_path
        self.project_id = project_id
        self.task_list_path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> TaskState:
        """Load task state, migrating legacy schemas as needed."""
        try:
            return migrate_file_in_place(self.task_list_path, project_id=self.project_id)
        except Exception as exc:
            raise MigrationError(f"Failed to load task state: {exc}") from exc

    def save(self, state: TaskState) -> None:
        """Save task state atomically."""
        payload = state.to_dict()
        payload["schema_version"] = 4
        payload["version"] = "4.0"
        payload["project_id"] = state.project_id or self.project_id
        payload["last_updated"] = datetime.now().isoformat()

        temp = self.task_list_path.with_suffix(".tmp")
        temp.write_text(json.dumps(payload, indent=2))
        temp.replace(self.task_list_path)

    @contextmanager
    def transaction(self):
        """Transactional state writer with rollback on failure."""
        state = self.load()
        backup = None

        if self.task_list_path.exists():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup = self.task_list_path.with_name(f"{self.task_list_path.stem}.txn_{timestamp}.json")
            backup.write_text(self.task_list_path.read_text())

        try:
            yield state
            self.save(state)
        except Exception:
            if backup and backup.exists():
                backup.replace(self.task_list_path)
            raise
