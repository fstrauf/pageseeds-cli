"""Compatibility re-exports for project models.

The canonical project management implementation lives in dashboard.core.project_manager.
"""

from ..core.project_manager import Project, ProjectManager

__all__ = ["Project", "ProjectManager"]
