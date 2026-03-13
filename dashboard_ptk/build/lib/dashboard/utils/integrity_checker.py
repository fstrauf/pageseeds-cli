"""
Integrity checking for articles and content.

Validates articles.json, content files, and system state.
"""
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console

from .errors import (
    DuplicateIdError,
    DuplicateDateError,
    DuplicateSlugError,
    FileExistsError,
    ArticlesJsonError,
    ValidationError,
    IntegrityError,
)

console = Console()


class IntegrityChecker:
    """Checks system integrity and validates article data."""
    
    def __init__(self, articles_json_path: Path, content_dir: Optional[Path] = None):
        self.articles_json_path = articles_json_path
        self.content_dir = content_dir
    
    def check_all(self, raise_on_error: bool = False) -> list[str]:
        """
        Run all integrity checks.
        
        Args:
            raise_on_error: If True, raise IntegrityError if issues found
        
        Returns:
            List of issue descriptions
        
        Raises:
            IntegrityError: If raise_on_error=True and issues found
        """
        issues = []
        
        # Check articles.json exists and is valid
        if not self.articles_json_path.exists():
            issues.append("articles.json not found")
            if raise_on_error:
                raise IntegrityError(issues)
            return issues
        
        try:
            data = json.loads(self.articles_json_path.read_text())
            articles = data.get("articles", [])
        except json.JSONDecodeError as e:
            if raise_on_error:
                raise ArticlesJsonError(f"Invalid JSON: {e}")
            return [f"articles.json is invalid: {e}"]
        except Exception as e:
            if raise_on_error:
                raise ArticlesJsonError(str(e))
            return [f"articles.json error: {e}"]
        
        # Run all checks
        issues.extend(self._check_duplicate_ids(articles, raise_on_error))
        issues.extend(self._check_duplicate_dates(articles, raise_on_error))
        issues.extend(self._check_next_id(data, articles, raise_on_error))
        issues.extend(self._check_file_existence(articles, raise_on_error))
        issues.extend(self._check_slug_alignment(articles, raise_on_error))
        
        if raise_on_error and issues:
            raise IntegrityError(issues)
        
        return issues
    
    def _check_duplicate_ids(self, articles: list, raise_on_error: bool = False) -> list[str]:
        """Check for duplicate article IDs (data integrity issue)."""
        issues = []
        ids = [a.get("id") for a in articles if a.get("id")]
        id_counts = Counter(ids)
        duplicates = [id for id, count in id_counts.items() if count > 1]
        
        if duplicates:
            # Check if these are published articles (can't easily fix)
            published_dups = []
            fixable_dups = []
            
            for dup_id in duplicates:
                dup_articles = [a for a in articles if a.get("id") == dup_id]
                all_published = all(
                    a.get("status") == "published" or 
                    a.get("published_date", "") < datetime.now().strftime("%Y-%m-%d")
                    for a in dup_articles
                )
                if all_published:
                    published_dups.append(dup_id)
                else:
                    fixable_dups.append(dup_id)
            
            if fixable_dups:
                issues.append(f"Duplicate IDs found: {fixable_dups} (needs fix)")
            if published_dups:
                issues.append(f"Duplicate IDs (published - manual check needed): {published_dups}")
            
            if raise_on_error:
                raise IntegrityError(issues)
        
        return issues
    
    def _check_duplicate_dates(self, articles: list, raise_on_error: bool = False) -> list[str]:
        """Check for duplicate publish dates (only for future dates)."""
        from datetime import datetime, timedelta
        
        issues = []
        
        # Get tomorrow's date (past dates are already published, can't change)
        today = datetime.now().date()
        tomorrow = today + timedelta(days=1)
        
        # Only check dates from tomorrow onwards
        dates = [a.get("published_date") for a in articles if a.get("published_date")]
        date_counts = Counter(dates)
        dup_dates = {d: c for d, c in date_counts.items() if c > 1}
        
        # Filter to only future dates (not yet published)
        future_dup_dates = {}
        for date_str, count in dup_dates.items():
            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
                if date_obj >= tomorrow:
                    future_dup_dates[date_str] = count
            except ValueError:
                continue
        
        for date, count in list(future_dup_dates.items())[:3]:
            issues.append(f"Date {date} has {count} articles (scheduling conflict)")
        
        if len(future_dup_dates) > 3:
            issues.append(f"... and {len(future_dup_dates) - 3} more scheduling conflicts")
        
        if future_dup_dates and raise_on_error:
            raise IntegrityError(issues)
        
        return issues
    
    def _check_next_id(self, data: dict, articles: list, raise_on_error: bool = False) -> list[str]:
        """Check if nextArticleId is correct."""
        issues = []
        
        if not articles:
            return issues
        
        max_id = max(a.get("id", 0) for a in articles)
        expected_next = max_id + 1
        actual_next = data.get("nextArticleId")
        
        if actual_next != expected_next:
            issues.append(f"nextArticleId should be {expected_next}, found {actual_next}")
            if raise_on_error:
                raise IntegrityError(issues)
        
        return issues
    
    def _check_file_existence(self, articles: list, raise_on_error: bool = False) -> list[str]:
        """Check if content files exist for tracked articles."""
        issues = []
        
        if not self.content_dir:
            return issues
        
        missing = []
        for article in articles:
            file_path = article.get("file", "")
            if file_path:
                # Handle ./content/ prefix
                if file_path.startswith("./content/"):
                    filename = file_path.replace("./content/", "")
                else:
                    filename = Path(file_path).name
                
                full_path = self.content_dir / filename
                if not full_path.exists():
                    missing.append(f"ID {article.get('id')}: {filename}")
        
        if missing:
            issues.append(f"{len(missing)} content files missing (showing first 3):")
            for m in missing[:3]:
                issues.append(f"  {m}")
            if raise_on_error:
                raise IntegrityError(issues)
        
        return issues
    
    def _check_slug_alignment(self, articles: list, raise_on_error: bool = False) -> list[str]:
        """Check if url_slug matches filename for all articles."""
        issues = []
        
        mismatches = []
        for article in articles:
            url_slug = str(article.get("url_slug") or "").strip()
            file_path = str(article.get("file") or "").strip()
            
            if not url_slug or not file_path:
                continue
            
            filename = Path(file_path).name
            filename_slug = filename.replace(".mdx", "").replace(".md", "")
            filename_slug_clean = re.sub(r'^\d+_', '', filename_slug)
            
            if url_slug != filename_slug_clean:
                mismatches.append(article.get("id"))
        
        if mismatches:
            issues.append(f"{len(mismatches)} slug/filename mismatches (IDs: {mismatches[:5]}...)")
            if raise_on_error:
                raise IntegrityError(issues)
        
        return issues
    
    def validate_new_article(self, title: str, proposed_date: str, 
                            next_id: int, content_dir: Path,
                            raise_on_error: bool = False) -> tuple[bool, str]:
        """
        Validate before creating a new article.
        
        Args:
            title: Article title
            proposed_date: Proposed publish date (YYYY-MM-DD)
            next_id: Proposed article ID
            content_dir: Content directory path
            raise_on_error: If True, raise exception instead of returning (False, msg)
        
        Returns:
            tuple[bool, str]: (is_valid, error_message or "")
        
        Raises:
            DuplicateIdError, DuplicateDateError, DuplicateSlugError,
            FileExistsError, ArticlesJsonError, ValidationError
        """
        # Check articles.json is readable
        try:
            data = json.loads(self.articles_json_path.read_text())
            articles = data.get("articles", [])
        except json.JSONDecodeError as e:
            if raise_on_error:
                raise ArticlesJsonError(f"Invalid JSON: {e}")
            return False, f"Cannot read articles.json: {e}"
        except Exception as e:
            if raise_on_error:
                raise ArticlesJsonError(str(e))
            return False, f"Cannot read articles.json: {e}"
        
        # Check ID not already used
        existing_ids = {a.get("id") for a in articles}
        if next_id in existing_ids:
            if raise_on_error:
                raise DuplicateIdError(next_id)
            return False, f"ID {next_id} already exists"
        
        # Check date not already taken
        for article in articles:
            if article.get("published_date") == proposed_date:
                existing_id = article.get("id")
                if raise_on_error:
                    raise DuplicateDateError(proposed_date, existing_id)
                return False, f"Date {proposed_date} already taken by ID {existing_id}"
        
        # Check filename wouldn't conflict
        slug = re.sub(r'[^\w\s-]', '', title).strip().lower()
        slug = re.sub(r'[-\s]+', '_', slug)
        filename = f"{next_id:03d}_{slug}.mdx"
        
        if (content_dir / filename).exists():
            if raise_on_error:
                raise FileExistsError(str(content_dir / filename))
            return False, f"Content file already exists: {filename}"
        
        # Check slug unique
        url_slug = re.sub(r'^\d+_', '', filename.replace('.mdx', ''))
        for article in articles:
            if article.get("url_slug") == url_slug:
                if raise_on_error:
                    raise DuplicateSlugError(url_slug)
                return False, f"URL slug '{url_slug}' already exists"
        
        return True, ""
