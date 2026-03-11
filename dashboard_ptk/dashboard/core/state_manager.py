"""
StateManager - Centralized state management with auto-save and validation

This module provides robust state management for the task dashboard,
ensuring all changes are persisted and validated.
"""
import json
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ..engine.content_locator import resolve_content_dir
from ..models import Task, Project
from ..utils.articles import ArticleManager


class StateError(Exception):
    """Raised when state operation fails."""
    pass


class StateManager:
    """
    Centralized state manager for all dashboard operations.
    
    Features:
    - Auto-save on all state changes
    - Atomic operations (all-or-nothing)
    - Validation before save
    - Backup on critical operations
    - Consistent error handling
    """
    
    def __init__(self, project: Project):
        self.project = project
        self.path_resolver = PathResolver(project)
        self.validator = TaskValidator()
        
        # Initialize paths
        self.automation_dir = self.path_resolver.automation_dir
        self.task_list_path = self.path_resolver.task_list_path
        
        # In-memory state
        self._tasks: list[Task] = []
        self._metadata: dict = {}
        self._dirty = False  # Track if changes need saving
        
        # Load initial state
        self._load()
    
    @property
    def tasks(self) -> list[Task]:
        """Get current tasks (read-only reference)."""
        return self._tasks.copy()
    
    @property
    def metadata(self) -> dict:
        """Get metadata copy."""
        return self._metadata.copy()
    
    def _load(self) -> None:
        """Load state from disk."""
        if not self.task_list_path.exists():
            self._tasks = []
            self._metadata = {"next_task_sequence": 1}
            self._dirty = True
            self._save()
            return
        
        try:
            data = json.loads(self.task_list_path.read_text())
            self._tasks = [Task.from_dict(t) for t in data.get("tasks", [])]
            self._metadata = data.get("metadata", {})
            self._dirty = False
            
            # Validate loaded state
            self._validate_state()
            
        except Exception as e:
            raise StateError(f"Failed to load state: {e}")
    
    def _save(self, force: bool = False) -> None:
        """Save state to disk if dirty or forced."""
        if not self._dirty and not force:
            return
        
        try:
            # Ensure directory exists
            self.automation_dir.mkdir(parents=True, exist_ok=True)
            
            # Validate before save
            self._validate_state()
            
            # Build data
            data = {
                "version": "3.0",
                "project_id": self.project.website_id,
                "last_updated": datetime.now().isoformat(),
                "tasks": [t.to_dict() for t in self._tasks],
                "metadata": self._metadata
            }
            
            # Atomic write (write to temp, then rename)
            temp_path = self.task_list_path.with_suffix('.tmp')
            temp_path.write_text(json.dumps(data, indent=2))
            temp_path.replace(self.task_list_path)
            
            self._dirty = False
            
        except Exception as e:
            raise StateError(f"Failed to save state: {e}")
    
    def _validate_state(self) -> None:
        """Validate current state."""
        # Check for duplicate IDs
        ids = [t.id for t in self._tasks]
        if len(ids) != len(set(ids)):
            from collections import Counter
            dups = {id_: c for id_, c in Counter(ids).items() if c > 1}
            raise StateError(f"Duplicate task IDs found: {dups}")
        
        # Validate each task
        for task in self._tasks:
            self.validator.validate_task(task)
    
    def _backup(self) -> Path:
        """Create timestamped backup of current state."""
        if not self.task_list_path.exists():
            return None
        
        backup_name = f"task_list_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        backup_path = self.automation_dir / backup_name
        backup_path.write_text(self.task_list_path.read_text())
        return backup_path
    
    # Task Operations
    
    def create_task(self, task_type: str, title: str, phase: str, **kwargs) -> Task:
        """Create a new task with guaranteed unique ID."""
        # Get project code
        project_code = self._get_project_code()
        
        # Find next available sequence number
        existing_ids = {t.id for t in self._tasks}
        next_seq = self._metadata.get("next_task_sequence", 1)
        
        while f"{project_code}-{next_seq:03d}" in existing_ids:
            next_seq += 1
        
        task_id = f"{project_code}-{next_seq:03d}"
        self._metadata["next_task_sequence"] = next_seq + 1
        
        # Create task
        task = Task(
            id=task_id,
            type=task_type,
            title=title,
            phase=phase,
            status="todo",
            created_at=datetime.now().isoformat(),
            **kwargs
        )
        
        # Validate
        self.validator.validate_task(task)
        
        # Add and save
        self._tasks.append(task)
        self._dirty = True
        self._save()
        
        return task
    
    def update_task(self, task_id: str, **updates) -> Task:
        """Update task fields and auto-save."""
        task = self.get_task(task_id)
        if not task:
            raise StateError(f"Task not found: {task_id}")
        
        # Apply updates
        for key, value in updates.items():
            if hasattr(task, key):
                setattr(task, key, value)
            else:
                raise StateError(f"Invalid task attribute: {key}")
        
        # Validate and save
        self.validator.validate_task(task)
        self._dirty = True
        self._save()
        
        return task
    
    def update_task_status(self, task_id: str, status: str) -> Task:
        """Update task status with validation and auto-save."""
        valid_statuses = {"todo", "in_progress", "review", "done", "cancelled"}
        if status not in valid_statuses:
            raise StateError(f"Invalid status: {status}. Must be one of: {valid_statuses}")
        
        updates = {"status": status}
        if status in ("done", "review"):
            updates["completed_at"] = datetime.now().isoformat()
        
        return self.update_task(task_id, **updates)
    
    def delete_task(self, task_id: str) -> bool:
        """Delete task by ID (removes all if duplicates exist)."""
        original_count = len(self._tasks)
        self._tasks = [t for t in self._tasks if t.id != task_id]
        deleted = original_count - len(self._tasks)
        
        if deleted > 0:
            self._dirty = True
            self._save()
            return True
        return False
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """Get task by ID."""
        for task in self._tasks:
            if task.id == task_id:
                return task
        return None
    
    def get_tasks_by_status(self, status: str) -> list[Task]:
        """Get all tasks with given status."""
        return [t for t in self._tasks if t.status == status]
    
    def get_ready_tasks(self) -> list[Task]:
        """Get tasks ready to start (unlocked dependencies)."""
        completed = {t.id for t in self._tasks if t.status == "done"}
        return [t for t in self._tasks 
                if t.status == "todo" and t.is_unlocked(completed)]
    
    # Atomic Operations
    
    @contextmanager
    def atomic(self):
        """
        Context manager for atomic operations.
        
        Usage:
            with state.atomic():
                state.create_task(...)
                state.update_task(...)
                # Both succeed or both fail
        """
        backup = self._backup()
        try:
            yield self
            self._save(force=True)
        except Exception:
            # Restore backup on failure
            if backup and backup.exists():
                backup.replace(self.task_list_path)
                self._load()
            raise
    
    # Batch Operations
    
    def reset_all(self, preserve_reddit: bool = True) -> dict:
        """Reset all tasks with backup."""
        backup = self._backup()
        
        try:
            # Count what we're deleting
            counts = {
                "tasks": len(self._tasks),
                "artifacts": 0,
                "results": 0,
                "specs": 0
            }
            
            # Preserve Reddit tasks if requested
            if preserve_reddit:
                reddit_tasks = [t for t in self._tasks if t.type.startswith("reddit_") and t.status == "done"]
                self._tasks = reddit_tasks
                counts["tasks"] -= len(reddit_tasks)
            else:
                self._tasks = []
            
            # Reset metadata
            self._metadata = {"next_task_sequence": 1}
            
            # Delete artifacts, specs, results
            for item in self.path_resolver.artifacts_dir.iterdir():
                if item.is_file():
                    item.unlink()
                    counts["artifacts"] += 1
                elif item.is_dir():
                    import shutil
                    shutil.rmtree(item)
                    counts["artifacts"] += 1
            
            for item in self.path_resolver.specs_dir.iterdir():
                if item.is_file():
                    item.unlink()
                    counts["specs"] += 1
            
            for item in self.path_resolver.task_results_dir.iterdir():
                if item.is_dir():
                    import shutil
                    shutil.rmtree(item)
                    counts["results"] += 1
            
            self._dirty = True
            self._save()
            
            return counts
            
        except Exception as e:
            # Restore on failure
            if backup and backup.exists():
                backup.replace(self.task_list_path)
                self._load()
            raise StateError(f"Reset failed: {e}")
    
    def _get_project_code(self) -> str:
        """Get 3-letter project code."""
        code_map = {
            "coffee": "COF",
            "coffee-site": "COF",
            "examplesite": "EXA",
            "myproject": "MYP",
        }
        project_id = self.project.website_id.lower()
        if project_id in code_map:
            return code_map[project_id]
        
        # Auto-generate
        cleaned = ''.join(c for c in project_id if c.isalpha())
        if len(cleaned) >= 3:
            return cleaned[:3].upper()
        elif cleaned:
            return cleaned.upper().ljust(3, 'X')
        return "TSK"


class PathResolver:
    """Consistent path resolution for all dashboard operations."""
    
    def __init__(self, project: Project):
        self.project = project
        self.repo_root = Path(project.repo_root)
        self.automation_dir = self.repo_root / ".github" / "automation"
        
        # Standard paths
        self.task_list_path = self.automation_dir / "task_list.json"
        self.artifacts_dir = self.automation_dir / "artifacts"
        self.specs_dir = self.automation_dir / "specs"
        self.task_results_dir = self.automation_dir / "task_results"
        self.reddit_dir = self.automation_dir / "reddit"
        
    def get_content_dir(self) -> Optional[Path]:
        """Find content directory using the shared content locator."""
        resolution = resolve_content_dir(
            repo_root=self.repo_root,
            website_id=self.project.website_id,
            include_empty_auto_fallback=False,
        )
        return resolution.selected if resolution.selected_has_markdown else None
    
    def get_articles_json_path(self) -> Optional[Path]:
        """Find articles.json in standard locations."""
        path = self.automation_dir / "articles.json"
        if path.exists():
            return path
        return None


class TaskValidator:
    """Validation for tasks and state."""
    
    VALID_STATUSES = {"todo", "in_progress", "review", "done", "cancelled"}
    VALID_PHASES = {"collection", "investigation", "research", "implementation", "verification"}
    
    def validate_task(self, task: Task) -> None:
        """Validate a single task."""
        errors = []
        
        if not task.id:
            errors.append("Task ID is required")
        
        if task.status not in self.VALID_STATUSES:
            errors.append(f"Invalid status: {task.status}")
        
        if task.phase not in self.VALID_PHASES:
            errors.append(f"Invalid phase: {task.phase}")
        
        if not task.title:
            errors.append("Task title is required")
        
        if errors:
            raise StateError(f"Task validation failed: {', '.join(errors)}")
