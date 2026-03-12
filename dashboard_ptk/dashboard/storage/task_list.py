"""
TaskList - Manages task persistence and operations
"""
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console

from ..config import PHASES, AUTONOMY_MODE_MAP, PROJECT_CODE_MAP
from ..engine import TaskState, TaskStore
from ..models import Task, Project

console = Console()


class TaskList:
    """Manages the task list for a project."""
    
    def __init__(
        self,
        project: Project,
        *,
        autonomy_mode_map: dict[str, str] | None = None,
        project_code_map: dict[str, str] | None = None,
    ):
        self.project = project
        self._autonomy_mode_map = autonomy_mode_map or AUTONOMY_MODE_MAP
        self._project_code_map = project_code_map or PROJECT_CODE_MAP
        self.automation_dir = Path(f"{project.repo_root}/.github/automation")
        self.task_list_path = self.automation_dir / "task_list.json"
        self.store = TaskStore(self.task_list_path, project_id=project.website_id)
        self.artifacts_dir = self.automation_dir / "artifacts"
        self.task_results_dir = self.automation_dir / "task_results"
        
        # Ensure directories exist
        self.automation_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(exist_ok=True)
        self.task_results_dir.mkdir(exist_ok=True)
        
        # Check gitignore
        self._check_gitignore()
        
        self.tasks: list[Task] = []
        self._metadata: dict = {}
        self._load_error: str | None = None
        self.load()
    
    def _check_gitignore(self):
        """Check if automation data is gitignored - now handled by preflight."""
        # Gitignore check moved to ProjectPreflight for interactive handling
        pass
    
    def load(self):
        """Load task list from file."""
        try:
            state = self.store.load()
            self.tasks = [Task.from_dict(task.to_dict()) for task in state.tasks]
            self._metadata = state.metadata or {}
            self._metadata.setdefault("next_task_sequence", 1)
            self._load_error = None
        except Exception as e:
            console.print(f"[red]Error loading task list: {e}[/red]")
            self._load_error = str(e)
            # Avoid wiping in-memory state on load failure.
            # A later save with partial state can destroy recoverable data.
            if not self.tasks:
                self._metadata = self._metadata or {"next_task_sequence": 1}
    
    def save(self):
        """Save task list to file."""
        if self._load_error and self.task_list_path.exists():
            raise RuntimeError(
                "Refusing to save task state because the last load failed. "
                f"Resolve load error first: {self._load_error}"
            )
        state = TaskState.from_dict(
            {
                "schema_version": 4,
                "version": "4.0",
                "project_id": self.project.website_id,
                "last_updated": datetime.now().isoformat(),
                "tasks": [t.to_dict() for t in self.tasks],
                "metadata": self._metadata,
            }
        )
        self.store.save(state)
    
    def get_metadata(self, key: str, default=None):
        """Get metadata value."""
        return self._metadata.get(key, default)
    
    def set_metadata(self, key: str, value):
        """Set metadata value."""
        self._metadata[key] = value
        self.save()
    
    def get_completed_ids(self) -> set:
        # Both done and failed tasks are considered "completed" for dependency unlocking
        # Failed tasks should not block dependent tasks indefinitely
        return {t.id for t in self.tasks if t.status in ("done", "failed")}
    
    def get_by_phase(self, phase: str) -> list[Task]:
        return [t for t in self.tasks if t.phase == phase]
    
    def get_by_status(self, status: str) -> list[Task]:
        return [t for t in self.tasks if t.status == status]
    
    def get_by_type(self, task_type: str) -> list[Task]:
        """Get tasks by type (supports wildcards like 'fix_*')."""
        if task_type.endswith('*'):
            prefix = task_type[:-1]
            return [t for t in self.tasks if t.type.startswith(prefix)]
        return [t for t in self.tasks if t.type == task_type]
    
    def get_ready_by_type(self, task_type: str) -> list[Task]:
        """Get ready tasks filtered by type."""
        completed = self.get_completed_ids()
        tasks = self.get_by_type(task_type)
        return [t for t in tasks if t.status == "todo" and t.is_unlocked(completed)]
    
    def get_unique_task_types(self) -> list[tuple[str, int]]:
        """Get all unique task types with counts of ready tasks.
        
        Returns list of (type, ready_count) tuples sorted by ready count descending.
        """
        completed = self.get_completed_ids()
        type_counts = {}
        
        for task in self.tasks:
            if task.status == "todo" and task.is_unlocked(completed):
                type_counts[task.type] = type_counts.get(task.type, 0) + 1
        
        # Sort by count descending, then alphabetically
        return sorted(type_counts.items(), key=lambda x: (-x[1], x[0]))
    
    def get_ready(self) -> list[Task]:
        completed = self.get_completed_ids()
        return [t for t in self.tasks if t.status == "todo" and t.is_unlocked(completed)]
    
    def get_progress(self) -> dict:
        total = len(self.tasks)
        if total == 0:
            return {"total": 0, "done": 0, "pct": 0}
        done = len([t for t in self.tasks if t.status == "done"])
        return {"total": total, "done": done, "pct": int(done / total * 100)}
    
    def get_current_phase(self) -> str:
        for phase in PHASES:
            phase_tasks = self.get_by_phase(phase)
            if not phase_tasks:
                continue
            
            if any(t.status == "in_progress" for t in phase_tasks):
                return phase
            
            completed = self.get_completed_ids()
            if any(t.status == "todo" and t.is_unlocked(completed) for t in phase_tasks):
                return phase
        
        return "complete" if self.tasks else "empty"
    
    def _get_autonomy_mode_for_type(self, task_type: str) -> str:
        """Get autonomy mode for a task type (for task creation)."""
        return self._autonomy_mode_map.get(task_type, "manual")
    
    def _get_project_code(self) -> str:
        """Get the short code for the current project.
        
        Uses project_id to derive a 3-letter code.
        Examples: coffee -> COF, coffee-site -> COF
        """
        project_id = self.project.website_id if self.project else "UNK"
        
        if project_id.lower() in self._project_code_map:
            return self._project_code_map[project_id.lower()]
        
        # Auto-generate code from project_id
        cleaned = ''.join(c for c in project_id if c.isalpha())
        if len(cleaned) >= 3:
            return cleaned[:3].upper()
        elif cleaned:
            return cleaned.upper().ljust(3, 'X')
        else:
            return "TSK"
    
    def create_task(self, task_type: str, title: str, phase: str, **kwargs) -> Task:
        """Create a new task with universal task numbering.
        
        Task IDs follow the format: {PROJECT_CODE}-{SEQUENCE_NUMBER}
        Example: COF-001, COF-002, etc.
        """
        now = datetime.now()
        
        # Get project short code from project_id
        project_code = self._get_project_code()
        
        # Get next sequence number from metadata
        next_seq = self._metadata.get("next_task_sequence", 1)
        
        # Ensure unique ID - increment until we find one not in use
        existing_ids = {t.id for t in self.tasks}
        while f"{project_code}-{next_seq:03d}" in existing_ids:
            next_seq += 1
        
        # Build task ID: COF-001
        task_id = f"{project_code}-{next_seq:03d}"
        
        # Increment sequence for next task
        self._metadata["next_task_sequence"] = next_seq + 1
        
        # Auto-set execution_mode if not provided
        if "execution_mode" not in kwargs:
            kwargs["execution_mode"] = self._get_autonomy_mode_for_type(task_type)
        
        depends = kwargs.pop("depends_on", [])
        if isinstance(depends, str):
            depends = [depends] if depends else []
        elif not isinstance(depends, list):
            depends = []

        workflow_key = kwargs.pop("workflow_key", task_type)
        agent_policy = kwargs.pop("agent_policy", "optional")

        task = Task(
            id=task_id,
            type=task_type,
            title=title,
            phase=phase,
            status="todo",
            created_at=now.isoformat(),
            workflow_key=workflow_key,
            agent_policy=agent_policy,
            depends_on=depends,
            **kwargs
        )
        self.tasks.append(task)
        self.save()
        return task
    
    def create_collection_task(self, source: str) -> Task:
        """Create a data collection task."""
        return self.create_task(
            task_type=f"collect_{source}",
            title=f"Collect {source.upper()} data",
            phase="collection",
            priority="high",
            action_command=f"pageseeds automation campaign collect --source {source}",
            output_artifact=f"artifacts/{source}_collection.json"
        )
    
    def create_investigation_task(self, source: str, collection_task: Task) -> Task:
        """Create an investigation task."""
        input_artifact = collection_task.output_artifact or f"artifacts/{source}_collection.json"
        return self.create_task(
            task_type=f"investigate_{source}",
            title=f"Investigate {source.upper()} findings",
            phase="investigation",
            priority="high",
            depends_on=[collection_task.id],
            input_artifact=input_artifact,
            output_investigation=f"task_results/inv_{source}_{datetime.now().strftime('%Y%m%d_%H%M%S')}/investigation.json"
        )
    
    def create_research_task(self, research_type: str) -> Task:
        """Create a research task."""
        return self.create_task(
            task_type=f"research_{research_type}",
            title=f"Research {research_type.replace('_', ' ').title()}",
            phase="research",
            priority="medium",
            output_research=f"task_results/res_{research_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}/research.json"
        )
    
    def create_custom_keyword_research_task(
        self,
        themes: list[str],
        criteria: str = "",
        exclude_terms: str = "",
        min_volume: int = 100,
        max_kd: int = 40
    ) -> Task:
        """Create a custom keyword research task with user-defined parameters.
        
        Args:
            themes: List of keyword themes to research
            criteria: Custom criteria/focus instructions (e.g., "focus on beginners")
            exclude_terms: Comma-separated terms to exclude
            min_volume: Minimum search volume threshold
            max_kd: Maximum keyword difficulty threshold
        
        Returns:
            Task: The created research task
        """
        themes_str = ", ".join(themes[:3])
        if len(themes) > 3:
            themes_str += f" (+{len(themes) - 3} more)"
        
        return self.create_task(
            task_type="custom_keyword_research",
            title=f"Custom research: {themes_str}",
            phase="research",
            priority="medium",
            output_research=f"task_results/res_custom_{datetime.now().strftime('%Y%m%d_%H%M%S')}/research.json",
            metadata={
                "custom_themes": themes,
                "custom_criteria": criteria,
                "exclude_terms": exclude_terms,
                "min_volume": min_volume,
                "max_kd": max_kd
            }
        )
    
    def create_reddit_opportunity_search(self) -> Task:
        """Create Reddit Stage 1: search opportunities + draft replies (batch)."""
        return self.create_task(
            task_type="reddit_opportunity_search",
            title=f"Reddit search: {self.project.website_id}",
            phase="research",
            priority="medium",
            category="reddit:search"
        )
    
    def create_reddit_reply_task(self, post_title: str, post_id: str, reply_text: str, 
                                  parent_artifact: str, severity: str = "medium",
                                  url: str = "", subreddit: str = "", 
                                  post_date: str = "") -> Task:
        """Create a task to post a single Reddit reply (human must execute)."""
        # Map severity to priority
        priority_map = {"CRITICAL": "critical", "HIGH": "high", "MEDIUM": "medium", "LOW": "low"}
        priority = priority_map.get(severity, "medium")
        
        return self.create_task(
            task_type="reddit_reply",
            title=f"Reply: {post_title[:45]}{'...' if len(post_title) > 45 else ''}",
            phase="implementation",
            priority=priority,
            category=f"reddit:reply:{severity.lower()}",
            input_artifact=parent_artifact,
            notes=reply_text,  # The drafted reply for human review
            post_id=post_id,  # Store Reddit post ID for auto-posting
            url=url,  # Store full URL as backup
            subreddit=subreddit,  # Store subreddit name
            post_date=post_date  # Store original post date for age checking
        )
    
    def reset_all(self, preserve_reddit: bool = True) -> dict:
        """Reset the entire project - clear all tasks, artifacts, and results.
        
        Args:
            preserve_reddit: If True, keep completed Reddit reply tasks (prevents duplicate posting)
        
        Returns:
            dict with counts of what was deleted
        """
        # Identify Reddit tasks to preserve (only completed ones to prevent dupes)
        reddit_tasks = []
        if preserve_reddit:
            # Only preserve posted (done) tasks, not skipped or pending ones
            reddit_tasks = [t for t in self.tasks if t.type.startswith("reddit_") and t.status == "done"]
            skipped_tasks = [t for t in self.tasks if t.type.startswith("reddit_") and t.status != "done"]
            if reddit_tasks:
                console.print(f"[dim]Preserving {len(reddit_tasks)} posted Reddit tasks (prevents duplicate posting)[/dim]")
            if skipped_tasks:
                console.print(f"[dim]Removing {len(skipped_tasks)} unposted Reddit tasks (will be rediscovered)[/dim]")
        
        counts = {
            "tasks": len(self.tasks) - len(reddit_tasks),
            "artifacts": 0,
            "results": 0,
            "specs": 0,
            "reddit_preserved": len(reddit_tasks)
        }
        
        # Clear tasks (except Reddit if preserving)
        self.tasks = reddit_tasks if preserve_reddit else []
        
        # Delete artifacts
        if self.artifacts_dir.exists():
            for item in self.artifacts_dir.iterdir():
                if item.is_file():
                    item.unlink()
                    counts["artifacts"] += 1
                elif item.is_dir():
                    shutil.rmtree(item)
                    counts["artifacts"] += 1
        
        # Delete task results
        if self.task_results_dir.exists():
            for item in self.task_results_dir.iterdir():
                if item.is_dir():
                    shutil.rmtree(item)
                    counts["results"] += 1
                elif item.is_file():
                    item.unlink()
                    counts["results"] += 1
        
        # Delete specs
        specs_dir = self.automation_dir / "specs"
        if specs_dir.exists():
            for item in specs_dir.iterdir():
                if item.is_file():
                    item.unlink()
                    counts["specs"] += 1
        
        # Save empty task list
        self.save()
        
        # Clean up ghost entries from articles.json
        counts["ghost_articles_cleaned"] = self._cleanup_ghost_articles()
        
        return counts
    
    def _cleanup_ghost_articles(self) -> int:
        """Remove draft articles with no content files from articles.json.
        
        Returns:
            Number of ghost entries removed
        """
        try:
            from ..utils.articles import ArticleManager
            from pathlib import Path
            article_mgr = ArticleManager(self.project.website_id)
            
            repo_root = Path(self.project.repo_root)
            articles_json = article_mgr.get_articles_json_path(repo_root)
            if not articles_json:
                return 0
            
            import json
            data = json.loads(articles_json.read_text())
            articles = data.get("articles", [])
            content_dir = article_mgr.get_content_dir(repo_root)
            
            filtered = []
            removed = 0
            
            for article in articles:
                # Check if it's a ghost entry:
                # - status is "draft" 
                # - word_count is 0 or empty
                # - no content file exists
                is_draft = article.get("status") == "draft"
                word_count = article.get("word_count", 0)
                has_no_words = word_count == 0 or word_count == ""
                
                if is_draft and has_no_words:
                    # Check if content file exists
                    file_path = article.get("file", "")
                    if file_path.startswith("./content/"):
                        filename = file_path.replace("./content/", "")
                        # Check in content dir
                        if content_dir:
                            full_path = content_dir / filename
                            if not full_path.exists():
                                # Ghost entry - no content file
                                filtered.append(article)  # Keep for now, will filter below
                                removed += 1
                                continue
                    # If we get here, either file exists or we can't verify - keep it
                    filtered.append(article)
                else:
                    filtered.append(article)
            
            # Actually filter out the ghosts
            if removed > 0:
                data["articles"] = [a for a in articles if not (
                    a.get("status") == "draft" and 
                    (a.get("word_count", 0) == 0 or a.get("word_count", 0) == "") and
                    content_dir and 
                    not (content_dir / a.get("file", "").replace("./content/", "")).exists()
                )]
                articles_json.write_text(json.dumps(data, indent=2))
                console.print(f"[dim]Cleaned {removed} ghost entries from articles.json[/dim]")
            
            return removed
            
        except Exception as e:
            console.print(f"[dim]Note: Could not cleanup ghost articles: {e}[/dim]")
            return 0
    
    def delete_task(self, task_id: str) -> bool:
        """Delete a task by ID.
        
        Args:
            task_id: The task ID to delete
            
        Returns:
            True if task(s) were deleted, False if not found
        """
        original_count = len(self.tasks)
        # Remove ALL tasks with this ID (handles duplicates)
        self.tasks = [t for t in self.tasks if t.id != task_id]
        deleted_count = original_count - len(self.tasks)
        
        if deleted_count > 0:
            self.save()
            return True
        return False
    
    def delete_tasks(self, task_ids: list[str]) -> dict:
        """Delete multiple tasks by ID.
        
        Args:
            task_ids: List of task IDs to delete
            
        Returns:
            Dict with 'deleted' (list of deleted IDs), 'not_found' (list), and 'skipped_done' (list of done tasks that couldn't be deleted)
        """
        original_count = len(self.tasks)
        deleted = []
        not_found = []
        skipped_done = []
        
        # Find done tasks that can't be deleted
        done_tasks = {t.id for t in self.tasks if t.status == "done"}
        
        for task_id in task_ids:
            if task_id in done_tasks:
                skipped_done.append(task_id)
            elif any(t.id == task_id for t in self.tasks):
                deleted.append(task_id)
            else:
                not_found.append(task_id)
        
        # Remove all deletable tasks (exclude done tasks)
        ids_to_delete = set(deleted)
        self.tasks = [t for t in self.tasks if t.id not in ids_to_delete]
        
        if deleted:
            self.save()
        
        return {
            "deleted": deleted,
            "not_found": not_found,
            "skipped_done": skipped_done,
            "count": len(deleted)
        }
