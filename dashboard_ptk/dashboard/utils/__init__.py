"""
Dashboard utilities for project and article management.

This package provides utilities for:
- Project configuration management
- Article lifecycle (creation, validation, syncing)
- Content directory operations
- Git workflows
"""

# New unified article store (recommended)
from .article_store import ArticleStore, Article, SyncResult

# Task generator
from .task_generator import TaskGenerator, TaskSuggestion, format_time_since

# Article management (legacy - maintained for compatibility)
from .date_manager import DateManager
from .integrity_checker import IntegrityChecker
from .content_sync import ContentSync
from .article_manager_refactored import ArticleManager, generate_url_slug
from .errors import (
    ArticleError,
    DuplicateIdError,
    DuplicateDateError,
    DuplicateSlugError,
    FileExistsError,
    ValidationError,
    ContentNotFoundError,
    ArticlesJsonError,
    IntegrityError,
    SyncError,
    DateAllocationError,
)

__all__ = [
    # New unified article store (recommended)
    "ArticleStore",
    "Article",
    "SyncResult",
    
    # Task generator
    "TaskGenerator",
    "TaskSuggestion",
    "format_time_since",
    
    # Article management (legacy)
    "ArticleManager",
    "generate_url_slug",
    "DateManager",
    "IntegrityChecker",
    "ContentSync",
    
    # Errors
    "ArticleError",
    "DuplicateIdError",
    "DuplicateDateError",
    "DuplicateSlugError",
    "FileExistsError",
    "ValidationError",
    "ContentNotFoundError",
    "ArticlesJsonError",
    "IntegrityError",
    "SyncError",
    "DateAllocationError",
]
