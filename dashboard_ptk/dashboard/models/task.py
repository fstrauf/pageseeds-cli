"""
Task model - represents a single task in the workflow
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Task:
    """A single task."""
    id: str
    type: str
    title: str
    phase: str
    status: str
    priority: str = "medium"
    
    # Relationships
    depends_on: list[str] = field(default_factory=list)
    spawns_tasks: list = field(default_factory=list)
    parent_task: Optional[str] = None
    
    # I/O
    input_artifact: Optional[str] = None
    output_artifact: Optional[str] = None
    output_investigation: Optional[str] = None
    output_research: Optional[str] = None
    result_path: Optional[str] = None
    
    # Metadata
    category: Optional[str] = None
    implementation_mode: str = "auto"  # "auto", "spec", "direct"
    execution_mode: str = "manual"  # "automatic", "batchable", "manual", "spec"
    spec_file: Optional[str] = None
    notes: Optional[str] = None
    post_id: Optional[str] = None  # For Reddit reply tasks
    url: Optional[str] = None  # Full URL for reference
    subreddit: Optional[str] = None  # Subreddit name (e.g., 'budgeting')
    post_date: Optional[str] = None  # Original Reddit post date (YYYY-MM-DD)
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    action_command: Optional[str] = None
    metadata: dict = field(default_factory=dict)  # Custom task parameters
    workflow_key: Optional[str] = None
    agent_policy: str = "optional"  # "none", "required", "optional"
    artifacts: list = field(default_factory=list)  # Structured artifact refs
    run: dict = field(default_factory=dict)  # attempts/error/provider metadata

    def __post_init__(self):
        """Normalize legacy fields into schema-v4-friendly shapes."""
        if isinstance(self.depends_on, str):
            self.depends_on = [self.depends_on] if self.depends_on else []
        elif not isinstance(self.depends_on, list):
            self.depends_on = []
        else:
            self.depends_on = [str(dep) for dep in self.depends_on if dep]
        if not self.workflow_key:
            self.workflow_key = self.type
    
    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        depends = data.get("depends_on", [])
        if isinstance(depends, str):
            depends = [depends] if depends else []
        elif not isinstance(depends, list):
            depends = []

        artifacts = data.get("artifacts", [])
        if not isinstance(artifacts, list):
            artifacts = []

        run = data.get("run", {})
        if not isinstance(run, dict):
            run = {}

        return cls(
            id=data.get("id", ""),
            type=data.get("type", ""),
            title=data.get("title", "Untitled"),
            phase=data.get("phase", "implementation"),
            status=data.get("status", "todo"),
            priority=data.get("priority", "medium"),
            depends_on=depends,
            spawns_tasks=data.get("spawns_tasks", []),
            parent_task=data.get("parent_task"),
            input_artifact=data.get("input_artifact"),
            output_artifact=data.get("output_artifact"),
            output_investigation=data.get("output_investigation"),
            output_research=data.get("output_research"),
            result_path=data.get("result_path"),
            category=data.get("category"),
            implementation_mode=data.get("implementation_mode", "auto"),
            execution_mode=data.get("execution_mode", "manual"),
            spec_file=data.get("spec_file"),
            notes=data.get("notes"),
            post_id=data.get("post_id"),
            url=data.get("url"),
            subreddit=data.get("subreddit"),
            post_date=data.get("post_date"),
            created_at=data.get("created_at"),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            action_command=data.get("action", {}).get("command") if isinstance(data.get("action"), dict) else None,
            metadata=data.get("metadata", {}),
            workflow_key=data.get("workflow_key") or data.get("type"),
            agent_policy=data.get("agent_policy", "optional"),
            artifacts=artifacts,
            run=run,
        )
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "title": self.title,
            "phase": self.phase,
            "status": self.status,
            "priority": self.priority,
            "depends_on": self.depends_on,
            "spawns_tasks": self.spawns_tasks,
            "parent_task": self.parent_task,
            "input_artifact": self.input_artifact,
            "output_artifact": self.output_artifact,
            "output_investigation": self.output_investigation,
            "output_research": self.output_research,
            "result_path": self.result_path,
            "category": self.category,
            "implementation_mode": self.implementation_mode,
            "execution_mode": self.execution_mode,
            "spec_file": self.spec_file,
            "notes": self.notes,
            "post_id": self.post_id,
            "url": self.url,
            "subreddit": self.subreddit,
            "post_date": self.post_date,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "action": {"command": self.action_command} if self.action_command else None,
            "metadata": self.metadata,
            "workflow_key": self.workflow_key or self.type,
            "agent_policy": self.agent_policy,
            "artifacts": self.artifacts,
            "run": self.run,
        }
    
    def is_unlocked(self, completed_task_ids: set) -> bool:
        if not self.depends_on:
            return True
        return all(dep in completed_task_ids for dep in self.depends_on)
    
    def display_status(self) -> str:
        icons = {
            "todo": "○",
            "in_progress": "◐",
            "review": "◑",
            "done": "✓",
            "blocked": "✗"
        }
        return f"{icons.get(self.status, '?')} {self.status}"
