"""
Task execution runners
"""
from __future__ import annotations

from .base import TaskRunner
from .collection import CollectionRunner
from .investigation import InvestigationRunner
from .research import ResearchRunner
from .content import ContentRunner
from .linking import LinkingRunner
from .cleanup import CleanupRunner
from .publishing import PublishingRunner
from .indexing import IndexingRunner
from .implementation import ImplementationRunner
from .reddit import RedditRunner
from .performance import PerformanceRunner


def build_runner_registry(task_list, project, session) -> dict[str, TaskRunner]:
    """Build the canonical runner registry for engine execution."""
    runners: dict[str, TaskRunner] = {
        "collection": CollectionRunner(task_list, project, session),
        "investigation": InvestigationRunner(task_list, project, session),
        "research": ResearchRunner(task_list, project, session),
        "content": ContentRunner(task_list, project, session),
        "linking": LinkingRunner(task_list, project, session),
        "cleanup": CleanupRunner(task_list, project, session),
        "publishing": PublishingRunner(task_list, project, session),
        "indexing": IndexingRunner(task_list, project, session),
        "reddit": RedditRunner(task_list, project, session),
        "performance": PerformanceRunner(task_list, project, session),
    }
    runners["implementation"] = ImplementationRunner(task_list, project, session, runners)
    return runners


__all__ = [
    "TaskRunner",
    "CollectionRunner", 
    "InvestigationRunner",
    "ResearchRunner",
    "ContentRunner",
    "LinkingRunner",
    "CleanupRunner",
    "PublishingRunner",
    "IndexingRunner",
    "ImplementationRunner",
    "RedditRunner",
    "PerformanceRunner",
    "build_runner_registry",
]
