"""Task state migration helpers (v3 -> v4)."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .types import ArtifactRef, MigrationError, RunMetadata, TaskRecord, TaskState


def infer_agent_policy(task_type: str) -> str:
    """Infer task agent policy for migrated tasks."""
    if task_type in {
        "write_article",
        "optimize_article",
        "content_strategy",
        "technical_fix",
        "cluster_and_link",
        "content_cleanup",
        "research_keywords",
        "custom_keyword_research",
        "investigate_gsc",
        "investigate_posthog",
        "reddit_opportunity_search",
        "reddit_reply",
    }:
        return "required"
    if task_type.startswith("fix_"):
        return "optional"
    return "none"


def build_artifacts_from_legacy(task: dict[str, Any]) -> list[ArtifactRef]:
    """Convert legacy artifact fields into structured artifact refs."""
    artifacts: list[ArtifactRef] = []

    mapping = {
        "input_artifact": "input",
        "output_artifact": "output",
        "output_investigation": "investigation",
        "output_research": "research",
        "result_path": "result",
        "spec_file": "spec",
    }

    for legacy_key, artifact_key in mapping.items():
        value = task.get(legacy_key)
        if isinstance(value, str) and value.strip():
            file_type = "json"
            if value.endswith(".md"):
                file_type = "markdown"
            elif value.endswith(".txt"):
                file_type = "text"
            artifacts.append(
                ArtifactRef(
                    key=artifact_key,
                    path=value,
                    type=file_type,
                    source="migration",
                )
            )

    return artifacts


def migrate_task_v3_to_v4(task: dict[str, Any]) -> TaskRecord:
    """Convert one v3 task item to schema-v4 TaskRecord."""
    depends = task.get("depends_on")
    depends_on: list[str]
    if isinstance(depends, list):
        depends_on = [str(dep) for dep in depends if dep]
    elif isinstance(depends, str) and depends:
        depends_on = [depends]
    else:
        depends_on = []

    run = RunMetadata(
        attempts=0,
        provider="kimi",
        started_at=task.get("started_at"),
        completed_at=task.get("completed_at"),
    )

    legacy_raw = dict(task)

    # Extract metadata, ensuring it's a dict
    metadata = task.get("metadata", {}) if isinstance(task.get("metadata"), dict) else {}
    
    # For custom_keyword_research tasks without custom_themes, add a migration marker
    # This helps the runner identify legacy tasks that need manual theme input
    task_type = str(task.get("type", ""))
    if task_type == "custom_keyword_research" and "custom_themes" not in metadata:
        metadata["_migrated_legacy_task"] = True
        metadata["custom_themes"] = []  # Empty list as placeholder

    record = TaskRecord(
        id=str(task.get("id", "")),
        type=task_type,
        title=str(task.get("title", "Untitled")),
        phase=str(task.get("phase", "implementation")),
        status=str(task.get("status", "todo")),
        priority=str(task.get("priority", "medium")),
        depends_on=depends_on,
        spawns_tasks=[str(item) for item in task.get("spawns_tasks", []) if item],
        parent_task=task.get("parent_task"),
        workflow_key=task.get("workflow_key") or task.get("type"),
        execution_mode=str(task.get("execution_mode", task.get("implementation_mode", "manual"))),
        agent_policy=str(task.get("agent_policy", infer_agent_policy(task_type))),
        artifacts=build_artifacts_from_legacy(task),
        run=run,
        metadata=metadata,
        raw=legacy_raw,
    )

    # Prefer migrated values over legacy in raw payload.
    for key in (
        "depends_on",
        "spawns_tasks",
        "workflow_key",
        "execution_mode",
        "agent_policy",
        "artifacts",
        "run",
    ):
        record.raw.pop(key, None)

    return record


def migrate_state_data(raw_data: dict[str, Any], project_id: str) -> TaskState:
    """Migrate arbitrary task_list payload to schema-v4 state."""
    if not isinstance(raw_data, dict):
        raise MigrationError("task_list payload must be a JSON object")

    schema_version = raw_data.get("schema_version")
    version = str(raw_data.get("version", ""))

    if schema_version == 4 or version.startswith("4"):
        state = TaskState.from_dict(raw_data)
        if not state.project_id:
            state.project_id = project_id
        return state

    tasks_payload = raw_data.get("tasks", [])
    if not isinstance(tasks_payload, list):
        raise MigrationError("task_list payload has invalid 'tasks' format")

    migrated_tasks = [migrate_task_v3_to_v4(task) for task in tasks_payload if isinstance(task, dict)]

    metadata = raw_data.get("metadata", {}) if isinstance(raw_data.get("metadata"), dict) else {}
    metadata.setdefault("migrated_from", version or "legacy")
    metadata.setdefault("migrated_at", datetime.now().isoformat())
    metadata.setdefault("next_task_sequence", metadata.get("next_task_sequence", 1))

    state = TaskState(
        schema_version=4,
        version="4.0",
        project_id=str(raw_data.get("project_id") or project_id),
        last_updated=str(raw_data.get("last_updated", datetime.now().isoformat())),
        tasks=migrated_tasks,
        metadata=metadata,
    )
    return state


def backup_legacy_file(task_list_path: Path) -> Path | None:
    """Create a one-time backup before schema migration."""
    if not task_list_path.exists():
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = task_list_path.with_name(f"{task_list_path.stem}.v3.backup_{timestamp}.json")
    backup_path.write_text(task_list_path.read_text())
    return backup_path


def migrate_file_in_place(task_list_path: Path, project_id: str) -> TaskState:
    """Read, migrate, and write task_list.json as schema-v4 with backup."""
    if not task_list_path.exists():
        state = TaskState(project_id=project_id, metadata={"next_task_sequence": 1})
        task_list_path.parent.mkdir(parents=True, exist_ok=True)
        task_list_path.write_text(json.dumps(state.to_dict(), indent=2))
        return state

    raw_data = json.loads(task_list_path.read_text())
    if raw_data.get("schema_version") == 4 or str(raw_data.get("version", "")).startswith("4"):
        return TaskState.from_dict(raw_data)

    backup_legacy_file(task_list_path)
    state = migrate_state_data(raw_data, project_id=project_id)
    task_list_path.write_text(json.dumps(state.to_dict(), indent=2))
    return state
