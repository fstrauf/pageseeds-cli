"""
Standardized error types for article management.

All errors include actionable fix suggestions and user-friendly messages.
"""


class ArticleError(Exception):
    """Base exception for all article-related errors."""
    
    def __init__(self, message: str, fix_suggestion: str = ""):
        super().__init__(message)
        self.message = message
        self.fix_suggestion = fix_suggestion
    
    def __str__(self) -> str:
        if self.fix_suggestion:
            return f"{self.message}\n  → {self.fix_suggestion}"
        return self.message


class DuplicateIdError(ArticleError):
    """Raised when attempting to create an article with an existing ID."""
    
    def __init__(self, article_id: int):
        super().__init__(
            message=f"Article ID {article_id} already exists",
            fix_suggestion=f"Use a higher ID or run sync to fix nextArticleId"
        )
        self.article_id = article_id


class DuplicateDateError(ArticleError):
    """Raised when attempting to assign a date that's already taken."""
    
    def __init__(self, date: str, existing_id: int):
        super().__init__(
            message=f"Date {date} is already assigned to article {existing_id}",
            fix_suggestion=f"Use --date YYYY-MM-DD to specify a different date"
        )
        self.date = date
        self.existing_id = existing_id


class DuplicateSlugError(ArticleError):
    """Raised when a URL slug already exists."""
    
    def __init__(self, slug: str):
        super().__init__(
            message=f"URL slug '{slug}' already exists",
            fix_suggestion="Choose a different title or manually specify a unique slug"
        )
        self.slug = slug


class FileExistsError(ArticleError):
    """Raised when attempting to create a file that already exists."""
    
    def __init__(self, filepath: str):
        super().__init__(
            message=f"File already exists: {filepath}",
            fix_suggestion="Remove the existing file or choose a different title"
        )
        self.filepath = filepath


class ValidationError(ArticleError):
    """Raised when article data fails validation."""
    
    def __init__(self, field: str, value: str, reason: str):
        super().__init__(
            message=f"Invalid {field}: '{value}' - {reason}",
            fix_suggestion=f"Check the {field} value and try again"
        )
        self.field = field
        self.value = value
        self.reason = reason


class ContentNotFoundError(ArticleError):
    """Raised when content directory or file cannot be found."""
    
    def __init__(self, path: str):
        super().__init__(
            message=f"Content not found: {path}",
            fix_suggestion="Ensure the repository is cloned and content directory exists"
        )
        self.path = path


class ArticlesJsonError(ArticleError):
    """Raised when articles.json cannot be read or is invalid."""
    
    def __init__(self, reason: str):
        super().__init__(
            message=f"articles.json error: {reason}",
            fix_suggestion="Check JSON syntax or restore from git"
        )
        self.reason = reason


class IntegrityError(ArticleError):
    """Raised when system integrity check fails."""
    
    def __init__(self, issues: list[str]):
        super().__init__(
            message=f"System integrity check failed: {len(issues)} issue(s) found",
            fix_suggestion="Run 'verify setup' to see details and auto-fix options"
        )
        self.issues = issues


class SyncError(ArticleError):
    """Raised when content directory sync fails."""
    
    def __init__(self, operation: str, detail: str):
        super().__init__(
            message=f"Sync failed during {operation}: {detail}",
            fix_suggestion="Check file permissions and try again"
        )
        self.operation = operation
        self.detail = detail


class DateAllocationError(ArticleError):
    """Raised when unable to allocate a valid date."""
    
    def __init__(self, reason: str):
        super().__init__(
            message=f"Could not allocate date: {reason}",
            fix_suggestion="Manually specify a date or check articles.json for date conflicts"
        )
        self.reason = reason
