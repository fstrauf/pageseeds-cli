"""
Task Generator - Auto-create tasks based on time since last run.

This module provides intelligent task generation that suggests new tasks
based on when certain steps were last completed. It's automation-assisted
but user-controlled - suggestions are presented for confirmation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from rich.console import Console

console = Console()


# Default intervals (in days) for each task type
DEFAULT_INTERVALS = {
    "collect_gsc": 7,           # Weekly GSC collection
    "collect_posthog": 7,       # Weekly PostHog collection
    "investigate_gsc": 7,       # After GSC collection
    "investigate_posthog": 7,   # After PostHog collection
    "research_keywords": 30,    # Monthly keyword research
    # NOTE: custom_keyword_research is intentionally excluded - manually triggered only
    "reddit_search": 3,         # Every 3 days
    "write_article": 1,         # Daily if drafts needed
    "publish_content": 1,       # Daily if drafts ready
    "cluster_and_link": 7,      # Weekly linking check
    "indexing_diagnostics": 14, # Bi-weekly
}


@dataclass
class TaskSuggestion:
    """A suggested task with context."""
    task_type: str
    title: str
    phase: str
    priority: str
    reason: str  # Why this task is suggested
    days_since_last: Optional[int] = None
    last_completed: Optional[str] = None
    depends_on: list[str] = field(default_factory=list)
    category: Optional[str] = None
    
    # For display
    icon: str = "📋"
    
    def __post_init__(self):
        # Set icon based on task type
        icon_map = {
            "collect_": "📊",
            "investigate_": "🔍",
            "research_": "🧠",
            "reddit_": "🤖",
            "write_": "✍️",
            "publish_": "🚀",
            "cluster_and_link": "🔗",
            "indexing_": "📈",
        }
        for prefix, icon in icon_map.items():
            if self.task_type.startswith(prefix) or prefix in self.task_type:
                self.icon = icon
                break


class TaskGenerator:
    """
    Generate task suggestions based on time since last run.
    
    Analyzes existing tasks and suggests new ones when enough time
    has passed since the last completion of each task type.
    """
    
    def __init__(self, task_list, intervals: Optional[dict] = None):
        """
        Initialize task generator.
        
        Args:
            task_list: TaskList instance with existing tasks
            intervals: Optional custom intervals (task_type -> days)
        """
        self.task_list = task_list
        self.intervals = intervals or DEFAULT_INTERVALS.copy()
    
    def analyze(self) -> list[TaskSuggestion]:
        """
        Analyze existing tasks and generate suggestions.
        
        Returns:
            List of task suggestions sorted by priority
        """
        suggestions = []
        
        # Load all tasks
        tasks = self.task_list.tasks if hasattr(self.task_list, 'tasks') else []
        
        # Check each task type
        for task_type, interval_days in self.intervals.items():
            suggestion = self._check_task_type(task_type, interval_days, tasks)
            if suggestion:
                suggestions.append(suggestion)
        
        # Check for content-specific suggestions
        content_suggestions = self._check_content_needs(tasks)
        suggestions.extend(content_suggestions)
        
        # Sort by priority (high -> medium -> low) then by days since last
        priority_order = {"high": 0, "medium": 1, "low": 2}
        suggestions.sort(key=lambda s: (priority_order.get(s.priority, 1), -(s.days_since_last or 0)))
        
        return suggestions
    
    def _check_task_type(self, task_type: str, interval_days: int, tasks: list) -> Optional[TaskSuggestion]:
        """Check if a task type needs to be run."""
        # Find last completed task of this type
        last_completed = None
        last_date = None
        
        for task in tasks:
            if task.type == task_type and task.status == "done":
                completed_at = getattr(task, 'completed_at', None)
                if completed_at:
                    try:
                        completed_date = datetime.fromisoformat(completed_at.replace('Z', '+00:00'))
                        if last_date is None or completed_date > last_date:
                            last_date = completed_date
                            last_completed = task
                    except (ValueError, AttributeError):
                        pass
        
        # Check if there's an active (non-done) task of this type
        has_active = any(
            t.type == task_type and t.status not in ("done", "cancelled")
            for t in tasks
        )
        
        if has_active:
            return None  # Already have an active task
        
        # Calculate days since last run
        if last_date:
            days_since = (datetime.now() - last_date.replace(tzinfo=None)).days
        else:
            days_since = 999  # Never run
        
        # Check if interval has passed
        if days_since < interval_days:
            return None  # Not enough time passed
        
        # Create suggestion
        return self._create_suggestion(task_type, days_since, last_date)
    
    def _create_suggestion(self, task_type: str, days_since: int, last_date: Optional[datetime]) -> Optional[TaskSuggestion]:
        """Create a task suggestion based on type."""
        
        suggestions = {
            "collect_gsc": TaskSuggestion(
                task_type="collect_gsc",
                title="Collect Google Search Console data",
                phase="collection",
                priority="high" if days_since > 14 else "medium",
                reason=f"Last collected {days_since} days ago (recommended: weekly)",
                days_since_last=days_since,
                last_completed=last_date.isoformat() if last_date else None,
            ),
            "collect_posthog": TaskSuggestion(
                task_type="collect_posthog",
                title="Collect PostHog analytics data",
                phase="collection",
                priority="medium",
                reason=f"Last collected {days_since} days ago (recommended: weekly)",
                days_since_last=days_since,
                last_completed=last_date.isoformat() if last_date else None,
            ),
            "investigate_gsc": TaskSuggestion(
                task_type="investigate_gsc",
                title="Investigate GSC data for opportunities",
                phase="investigation",
                priority="high" if days_since > 14 else "medium",
                reason=f"Last investigated {days_since} days ago",
                days_since_last=days_since,
                last_completed=last_date.isoformat() if last_date else None,
                depends_on=[],  # Would need to check for collection task
            ),
            "investigate_posthog": TaskSuggestion(
                task_type="investigate_posthog",
                title="Investigate PostHog data for insights",
                phase="investigation",
                priority="medium",
                reason=f"Last investigated {days_since} days ago",
                days_since_last=days_since,
                last_completed=last_date.isoformat() if last_date else None,
            ),
            "research_keywords": TaskSuggestion(
                task_type="research_keywords",
                title="Research new keyword opportunities",
                phase="research",
                priority="medium",
                reason=f"Last researched {days_since} days ago (recommended: monthly)",
                days_since_last=days_since,
                last_completed=last_date.isoformat() if last_date else None,
            ),
            # NOTE: custom_keyword_research is intentionally excluded - manually triggered only
            "reddit_search": TaskSuggestion(
                task_type="reddit_search",
                title="Search Reddit for engagement opportunities",
                phase="research",
                priority="high" if days_since > 7 else "medium",
                reason=f"Last searched {days_since} days ago (recommended: every 3 days)",
                days_since_last=days_since,
                last_completed=last_date.isoformat() if last_date else None,
            ),
            "cluster_and_link": TaskSuggestion(
                task_type="cluster_and_link",
                title="Cluster and link articles",
                phase="implementation",
                priority="medium",
                reason=f"Last run {days_since} days ago (recommended: weekly)",
                days_since_last=days_since,
                last_completed=last_date.isoformat() if last_date else None,
            ),
            "indexing_diagnostics": TaskSuggestion(
                task_type="indexing_diagnostics",
                title="Run indexing diagnostics",
                phase="verification",
                priority="low",
                reason=f"Last run {days_since} days ago (recommended: bi-weekly)",
                days_since_last=days_since,
                last_completed=last_date.isoformat() if last_date else None,
            ),
        }
        
        return suggestions.get(task_type)
    
    def _check_content_needs(self, tasks: list) -> list[TaskSuggestion]:
        """Check for content-specific needs (publishing, linking, etc.)."""
        suggestions = []
        
        # Check for draft articles ready to publish
        # This would need to check articles.json for drafts
        # For now, skip - would require ArticleManager integration
        
        return suggestions
    
    def get_summary(self) -> dict:
        """Get summary of task status by type."""
        tasks = self.task_list.tasks if hasattr(self.task_list, 'tasks') else []
        
        summary = {}
        for task_type in self.intervals.keys():
            # Count by status
            by_status = {"todo": 0, "in_progress": 0, "review": 0, "done": 0, "cancelled": 0}
            last_completed = None
            
            for task in tasks:
                if task.type == task_type:
                    status = getattr(task, 'status', 'todo')
                    by_status[status] = by_status.get(status, 0) + 1
                    
                    if status == "done":
                        completed_at = getattr(task, 'completed_at', None)
                        if completed_at:
                            try:
                                completed_date = datetime.fromisoformat(completed_at.replace('Z', '+00:00'))
                                if last_completed is None or completed_date > last_completed:
                                    last_completed = completed_date
                            except (ValueError, AttributeError):
                                pass
            
            # Calculate days since
            days_since = None
            if last_completed:
                days_since = (datetime.now() - last_completed.replace(tzinfo=None)).days
            
            summary[task_type] = {
                "counts": by_status,
                "last_completed": last_completed.isoformat() if last_completed else None,
                "days_since": days_since,
                "interval": self.intervals.get(task_type, 7),
                "overdue": days_since is not None and days_since > self.intervals.get(task_type, 7),
            }
        
        return summary


def format_time_since(days: int) -> str:
    """Format days into human-readable string."""
    if days == 0:
        return "today"
    elif days == 1:
        return "yesterday"
    elif days < 7:
        return f"{days} days ago"
    elif days < 30:
        weeks = days // 7
        return f"{weeks} week{'s' if weeks > 1 else ''} ago"
    elif days < 365:
        months = days // 30
        return f"{months} month{'s' if months > 1 else ''} ago"
    else:
        years = days // 365
        return f"{years} year{'s' if years > 1 else ''} ago"
