"""
Article management utilities (legacy compatibility layer).

This module re-exports from the refactored modules for backward compatibility.
New code should import from the specific modules directly:

  from dashboard.utils.date_manager import DateManager
  from dashboard.utils.integrity_checker import IntegrityChecker
  from dashboard.utils.content_sync import ContentSync
  from dashboard.utils.article_manager_refactored import ArticleManager
  from dashboard.utils.errors import DuplicateIdError, DuplicateDateError
"""
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
