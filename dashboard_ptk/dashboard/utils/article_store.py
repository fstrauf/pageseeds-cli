"""
Unified ArticleStore - Single source of truth for article management.

Design principles:
1. Content files are primary - articles.json is derived/cache
2. Automatic two-way sync with conflict resolution
3. Deterministic operations - same input always produces same output
4. Dry-run by default - safe to inspect before applying changes
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from rich.console import Console

from ..engine.frontmatter_dates import update_frontmatter_date

console = Console()


@dataclass
class Article:
    """Represents an article with all its metadata."""
    id: int
    title: str
    url_slug: str
    filename: str  # Just the filename, not full path
    published_date: str  # YYYY-MM-DD format
    status: str  # "draft" or "published"
    word_count: int = 0
    target_keyword: str = ""
    keyword_difficulty: str = ""
    target_volume: int = 0
    content_gaps_addressed: list = field(default_factory=list)
    estimated_traffic_monthly: str = ""
    
    # Tracking fields (not persisted to JSON)
    file_exists: bool = True
    date_synced: bool = True  # True if file date matches JSON date
    
    @property
    def file_path(self) -> str:
        """Return the relative file path for articles.json."""
        return f"./content/{self.filename}"
    
    @property
    def date_obj(self) -> datetime:
        """Return parsed date as datetime object."""
        return datetime.strptime(self.published_date, "%Y-%m-%d")
    
    def to_dict(self) -> dict:
        """Convert to articles.json format."""
        return {
            "id": self.id,
            "title": self.title,
            "url_slug": self.url_slug,
            "file": self.file_path,
            "target_keyword": self.target_keyword,
            "keyword_difficulty": self.keyword_difficulty,
            "target_volume": self.target_volume,
            "published_date": self.published_date,
            "word_count": self.word_count,
            "status": self.status,
            "content_gaps_addressed": self.content_gaps_addressed,
            "estimated_traffic_monthly": self.estimated_traffic_monthly,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> Article:
        """Create Article from articles.json format."""
        file_path = data.get("file", "")
        filename = Path(file_path).name if file_path else ""
        
        return cls(
            id=data.get("id", 0),
            title=data.get("title", ""),
            url_slug=data.get("url_slug", ""),
            filename=filename,
            published_date=data.get("published_date", ""),
            status=data.get("status", "published"),
            word_count=data.get("word_count", 0),
            target_keyword=data.get("target_keyword", ""),
            keyword_difficulty=data.get("keyword_difficulty", ""),
            target_volume=data.get("target_volume", 0),
            content_gaps_addressed=data.get("content_gaps_addressed", []),
            estimated_traffic_monthly=data.get("estimated_traffic_monthly", ""),
        )


@dataclass
class SyncResult:
    """Result of a sync operation."""
    added: list[Article] = field(default_factory=list)
    removed: list[Article] = field(default_factory=list)
    date_fixed: list[dict] = field(default_factory=list)  # {article, old_date, new_date}
    slug_fixed: list[dict] = field(default_factory=list)  # {article, old_slug, new_slug}
    duplicates_found: list[list[Article]] = field(default_factory=list)
    collisions_found: list[dict] = field(default_factory=list)  # {date, articles}
    errors: list[str] = field(default_factory=list)
    
    @property
    def has_changes(self) -> bool:
        return bool(
            self.added or self.removed or self.date_fixed or self.slug_fixed
        )
    
    @property
    def has_issues(self) -> bool:
        return bool(
            self.duplicates_found or self.collisions_found or self.errors
        )


class ArticleStore:
    """
    Unified store for article management.
    
    Content files are the source of truth. articles.json is a cache
    that gets rebuilt from files when needed.
    """
    
    # Regex patterns for frontmatter parsing
    FRONTMATTER_RE = re.compile(r'^---\s*\n(.*?)\n---', re.DOTALL | re.MULTILINE)
    DATE_LINE_RE = re.compile(r'^date:\s*["\']?(\d{4}-\d{2}-\d{2})["\']?\s*$', re.MULTILINE | re.IGNORECASE)
    TITLE_LINE_RE = re.compile(r'^title:\s*["\']?(.+?)["\']?\s*$', re.MULTILINE)
    DESC_LINE_RE = re.compile(r'^description:\s*["\']?(.+?)["\']?\s*$', re.MULTILINE)
    
    def __init__(self, repo_root: Path, website_id: str = ""):
        self.repo_root = Path(repo_root)
        self.website_id = website_id
        self.automation_dir = self.repo_root / ".github" / "automation"
        self.articles_json_path = self.automation_dir / "articles.json"
        self.content_dir: Optional[Path] = None
        
        # Find content directory
        self._locate_content_dir()
    
    def _locate_content_dir(self) -> bool:
        """Find the content directory."""
        from ..engine.content_locator import resolve_content_dir
        
        resolution = resolve_content_dir(
            repo_root=self.repo_root,
            website_id=self.website_id,
            include_empty_auto_fallback=True,
        )
        self.content_dir = resolution.selected
        return self.content_dir is not None
    
    # === Scanning - Build canonical state from files ===
    
    def scan(self) -> list[Article]:
        """
        Scan content directory and build canonical article list from files.
        
        Returns:
            List of Article objects built from actual content files.
        """
        if not self.content_dir or not self.content_dir.exists():
            return []
        
        articles = []
        for content_file in sorted(self.content_dir.glob("*.md*")):
            article = self._parse_content_file(content_file)
            if article:
                articles.append(article)
        
        # Sort by ID for consistency
        articles.sort(key=lambda a: a.id)
        return articles
    
    def _parse_content_file(self, filepath: Path) -> Optional[Article]:
        """Parse a single content file into an Article."""
        try:
            content = filepath.read_text()
        except Exception:
            return None
        
        # Extract ID from filename (support patterns: 059_name.mdx, name.mdx, 2024-01-01-name.mdx)
        filename = filepath.name
        file_id = self._extract_id_from_filename(filename)
        
        # Extract frontmatter
        frontmatter = self._extract_frontmatter(content)
        if not frontmatter:
            # No frontmatter - create minimal article
            slug = self._filename_to_slug(filename)
            return Article(
                id=file_id,
                title=slug.replace("_", " ").title(),
                url_slug=slug,
                filename=filename,
                published_date=datetime.now().strftime("%Y-%m-%d"),
                status="published",
                word_count=len(content.split()),
            )
        
        # Parse frontmatter fields
        date = self._parse_date_from_frontmatter(frontmatter) or datetime.now().strftime("%Y-%m-%d")
        title = self._parse_title_from_frontmatter(frontmatter) or self._filename_to_slug(filename).replace("_", " ").title()
        description = self._parse_description_from_frontmatter(frontmatter) or ""
        
        # Generate slug from filename (not title - filename is source of truth)
        url_slug = self._filename_to_slug(filename)
        
        # Determine status from date (future = draft, past = published)
        try:
            pub_date = datetime.strptime(date, "%Y-%m-%d")
            status = "draft" if pub_date > datetime.now() else "published"
        except ValueError:
            status = "published"
        
        return Article(
            id=file_id,
            title=title,
            url_slug=url_slug,
            filename=filename,
            published_date=date,
            status=status,
            word_count=len(content.split()),
            target_keyword=description[:50] if description else "",
        )
    
    def _extract_id_from_filename(self, filename: str) -> int:
        """Extract numeric ID from filename."""
        # Pattern 1: 059_name.mdx -> 59
        match = re.match(r'^(\d+)_.+\.mdx?$', filename)
        if match:
            return int(match.group(1))
        
        # Pattern 2: 2025-01-15-name.mdx -> hash of date
        match = re.match(r'^(\d{4})-(\d{2})-(\d{2})-.+\.mdx?$', filename)
        if match:
            # Use date as pseudo-ID: YYYYMMDD
            return int(f"{match.group(1)}{match.group(2)}{match.group(3)}")
        
        # Pattern 3: name.mdx -> hash of name
        name_hash = sum(ord(c) for c in filename) % 100000
        return 90000 + name_hash  # Use high range to avoid collisions
    
    def _filename_to_slug(self, filename: str) -> str:
        """Convert filename to url_slug."""
        # Remove extension
        base = filename.replace(".mdx", "").replace(".md", "")
        # Remove ID prefix (059_ or 2025-01-01-)
        base = re.sub(r'^\d+_', '', base)
        base = re.sub(r'^\d{4}-\d{2}-\d{2}-', '', base)
        return base
    
    def _extract_frontmatter(self, content: str) -> Optional[str]:
        """Extract frontmatter section from content."""
        match = self.FRONTMATTER_RE.match(content)
        if match:
            return match.group(1)
        return None
    
    def _parse_date_from_frontmatter(self, frontmatter: str) -> Optional[str]:
        """Parse date field from frontmatter."""
        match = self.DATE_LINE_RE.search(frontmatter)
        if match:
            return match.group(1)
        return None
    
    def _parse_title_from_frontmatter(self, frontmatter: str) -> Optional[str]:
        """Parse title field from frontmatter."""
        match = self.TITLE_LINE_RE.search(frontmatter)
        if match:
            title = match.group(1).strip()
            # Remove surrounding quotes if present
            if (title.startswith('"') and title.endswith('"')) or \
               (title.startswith("'") and title.endswith("'")):
                title = title[1:-1]
            return title
        return None
    
    def _parse_description_from_frontmatter(self, frontmatter: str) -> Optional[str]:
        """Parse description field from frontmatter."""
        match = self.DESC_LINE_RE.search(frontmatter)
        if match:
            return match.group(1).strip().strip('"').strip("'")
        return None
    
    # === Loading/Saving articles.json ===
    
    def load_json(self) -> list[Article]:
        """Load articles from articles.json."""
        if not self.articles_json_path.exists():
            return []
        
        try:
            data = json.loads(self.articles_json_path.read_text())
            articles_data = data.get("articles", [])
            return [Article.from_dict(a) for a in articles_data]
        except (json.JSONDecodeError, Exception):
            return []
    
    def save_json(self, articles: list[Article]) -> bool:
        """Save articles to articles.json."""
        try:
            self.automation_dir.mkdir(parents=True, exist_ok=True)
            
            # Calculate next ID
            next_id = 1
            if articles:
                next_id = max(a.id for a in articles) + 1
            
            data = {
                "articles": [a.to_dict() for a in articles],
                "nextArticleId": next_id,
                "statistics": {
                    "total_articles": len(articles),
                    "last_updated": datetime.now().strftime("%Y-%m-%d"),
                }
            }
            
            self.articles_json_path.write_text(json.dumps(data, indent=2))
            return True
        except Exception as e:
            console.print(f"[red]Error saving articles.json: {e}[/red]")
            return False
    
    # === Validation ===
    
    def validate(self, articles: list[Article]) -> SyncResult:
        """
        Validate articles list and return issues found.
        
        Checks for:
        - Duplicate IDs
        - Duplicate dates
        - Missing content files
        """
        result = SyncResult()
        
        # Check for duplicate IDs
        id_map: dict[int, list[Article]] = {}
        for article in articles:
            if article.id not in id_map:
                id_map[article.id] = []
            id_map[article.id].append(article)
        
        duplicates = [arts for arts in id_map.values() if len(arts) > 1]
        if duplicates:
            result.duplicates_found = duplicates
        
        # Check for duplicate dates (only future dates matter)
        today = datetime.now().date()
        tomorrow = today + timedelta(days=1)
        
        date_map: dict[str, list[Article]] = {}
        for article in articles:
            try:
                art_date = datetime.strptime(article.published_date, "%Y-%m-%d").date()
                if art_date >= tomorrow:
                    if article.published_date not in date_map:
                        date_map[article.published_date] = []
                    date_map[article.published_date].append(article)
            except ValueError:
                pass
        
        collisions = [{"date": d, "articles": arts} for d, arts in date_map.items() if len(arts) > 1]
        if collisions:
            result.collisions_found = collisions
        
        # Check for missing content files
        if self.content_dir:
            for article in articles:
                filepath = self.content_dir / article.filename
                if not filepath.exists():
                    article.file_exists = False
                    result.errors.append(f"Missing file for ID {article.id}: {article.filename}")
        
        return result
    
    # === Two-Way Sync ===
    
    def sync(self, dry_run: bool = True, prefer: str = "files") -> SyncResult:
        """
        Perform two-way sync between content files and articles.json.
        
        Args:
            dry_run: If True, don't make changes
            prefer: "files" or "json" - which source to prefer for conflicts
        
        Returns:
            SyncResult with details of what changed
        """
        result = SyncResult()
        
        # Get state from both sources
        file_articles = {a.filename: a for a in self.scan()}
        json_articles = {a.filename: a for a in self.load_json()}
        
        merged: dict[str, Article] = {}
        
        # Process all filenames from both sources
        all_filenames = set(file_articles.keys()) | set(json_articles.keys())
        
        for filename in all_filenames:
            file_art = file_articles.get(filename)
            json_art = json_articles.get(filename)
            
            if file_art and not json_art:
                # New file not in JSON
                merged[filename] = file_art
                result.added.append(file_art)
                
            elif json_art and not file_art:
                # JSON entry for missing file
                result.removed.append(json_art)
                # Don't add to merged
                
            elif file_art and json_art:
                # Both exist - merge with conflict resolution
                merged_art, date_fixed, slug_fixed = self._merge_articles(
                    file_art, json_art, prefer
                )
                merged[filename] = merged_art
                
                if date_fixed:
                    result.date_fixed.append(date_fixed)
                if slug_fixed:
                    result.slug_fixed.append(slug_fixed)
        
        # Update file dates if needed (and not dry_run)
        if not dry_run:
            for fix in result.date_fixed:
                article = fix["article"]
                new_date = fix["new_date"]
                self._update_file_date(article.filename, new_date)
        
        # Save merged state
        final_articles = list(merged.values())
        final_articles.sort(key=lambda a: a.id)
        
        if not dry_run:
            self.save_json(final_articles)
        
        # Run validation on merged state
        validation = self.validate(final_articles)
        result.duplicates_found = validation.duplicates_found
        result.collisions_found = validation.collisions_found
        result.errors = validation.errors
        
        return result
    
    def _merge_articles(self, file_art: Article, json_art: Article, 
                        prefer: str) -> tuple[Article, Optional[dict], Optional[dict]]:
        """
        Merge two article representations.
        
        Returns:
            (merged_article, date_fix_dict or None, slug_fix_dict or None)
        """
        date_fixed = None
        slug_fixed = None
        
        # Start with file article as base
        merged = Article(
            id=file_art.id,
            title=json_art.title if json_art.title else file_art.title,  # Prefer JSON title (may have been edited)
            url_slug=file_art.url_slug,  # File slug is derived from filename - always correct
            filename=file_art.filename,
            published_date=file_art.published_date,  # Default to file date
            status=file_art.status,
            word_count=file_art.word_count,
        )
        
        # Preserve JSON metadata
        merged.target_keyword = json_art.target_keyword
        merged.keyword_difficulty = json_art.keyword_difficulty
        merged.target_volume = json_art.target_volume
        merged.content_gaps_addressed = json_art.content_gaps_addressed
        merged.estimated_traffic_monthly = json_art.estimated_traffic_monthly
        
        # Handle date conflicts
        if file_art.published_date != json_art.published_date:
            if prefer == "files":
                # File wins - JSON will be updated
                merged.published_date = file_art.published_date
                merged.date_synced = True
                # Track that JSON will be updated (file date replaces JSON date)
                date_fixed = {
                    "article": merged,
                    "old_date": json_art.published_date,
                    "new_date": file_art.published_date,
                    "direction": "json_updated",
                }
            else:
                # JSON wins - file will be updated
                merged.published_date = json_art.published_date
                merged.date_synced = False
                date_fixed = {
                    "article": merged,
                    "old_date": file_art.published_date,
                    "new_date": json_art.published_date,
                    "direction": "file_updated",
                }
        
        # Handle slug conflicts (shouldn't happen if filenames match)
        if file_art.url_slug != json_art.url_slug:
            # File always wins for slug
            merged.url_slug = file_art.url_slug
            slug_fixed = {
                "article": merged,
                "old_slug": json_art.url_slug,
                "new_slug": file_art.url_slug,
            }
        
        return merged, date_fixed, slug_fixed
    
    def _update_file_date(self, filename: str, new_date: str) -> bool:
        """Update the date in a content file's frontmatter."""
        if not self.content_dir:
            return False
        
        filepath = self.content_dir / filename
        if not filepath.exists():
            return False
        
        try:
            content = filepath.read_text()
            updated_content, changed = update_frontmatter_date(content, new_date)
            if changed:
                filepath.write_text(updated_content)
                return True
        except Exception as e:
            console.print(f"[yellow]Warning: Could not update date in {filename}: {e}[/yellow]")
        
        return False
    
    # === Repair Operations ===
    
    def repair(self, dry_run: bool = True) -> SyncResult:
        """
        Repair all fixable issues.
        
        Fixes:
        - Slug mismatches
        - Date mismatches (uses file dates)
        - Adds missing articles from files
        - Removes orphaned JSON entries
        """
        # First run a sync with files preferred
        result = self.sync(dry_run=dry_run, prefer="files")
        
        # Additional repairs could go here
        
        return result
    
    def fix_duplicate_ids(self, articles: list[Article], dry_run: bool = True) -> list[Article]:
        """
        Fix duplicate IDs by reassigning new IDs to duplicates.
        
        Returns:
            List of articles with fixed IDs
        """
        seen_ids: set[int] = set()
        next_id = max((a.id for a in articles), default=0) + 1
        
        fixed_articles = []
        for article in articles:
            if article.id in seen_ids:
                # Assign new ID
                old_id = article.id
                article.id = next_id
                next_id += 1
                
                # Would need to rename file too - skip for now
                # This is complex because it affects URLs
                console.print(f"[yellow]Duplicate ID {old_id} would need rename to {article.id}[/yellow]")
            else:
                seen_ids.add(article.id)
            
            fixed_articles.append(article)
        
        return fixed_articles
    
    def redistribute_dates(self, articles: list[Article], 
                           start_date: Optional[str] = None,
                           dry_run: bool = True) -> list[Article]:
        """
        Redistribute dates for articles with collisions.
        
        Assigns 2-day gaps between articles, starting from start_date.
        """
        if not start_date:
            start_date = datetime.now().strftime("%Y-%m-%d")
        
        current_date = datetime.strptime(start_date, "%Y-%m-%d")
        
        # Sort by current date
        sorted_articles = sorted(articles, key=lambda a: a.date_obj)
        
        result = []
        for article in sorted_articles:
            new_art = Article(
                id=article.id,
                title=article.title,
                url_slug=article.url_slug,
                filename=article.filename,
                published_date=current_date.strftime("%Y-%m-%d"),
                status=article.status,
                word_count=article.word_count,
                target_keyword=article.target_keyword,
            )
            result.append(new_art)
            
            # Update file if not dry_run
            if not dry_run:
                self._update_file_date(article.filename, new_art.published_date)
            
            current_date += timedelta(days=2)
        
        return result
    
    # === Utility Methods ===
    
    def get_next_id(self) -> int:
        """Get next available article ID."""
        articles = self.load_json()
        if not articles:
            return 1
        return max(a.id for a in articles) + 1
    
    def get_next_available_date(self) -> str:
        """
        Get next available publish date.
        
        STRATEGY: Prefer dates in the past over future dates.
        1. First, look for gaps in the past (between existing articles)
        2. Only if no past gaps exist, use future dates
        """
        from .date_manager import DateManager
        
        # Use DateManager for consistent logic
        date_mgr = DateManager(self.articles_json_path)
        next_date = date_mgr.get_next_available_date()
        return next_date.strftime("%Y-%m-%d")
    
    def get_latest_date(self, include_drafts: bool = True) -> Optional[datetime]:
        """Get the most recent article date."""
        articles = self.load_json()
        if not articles:
            return None
        
        dates = []
        for a in articles:
            if a.status == "draft" and not include_drafts:
                continue
            try:
                dates.append(a.date_obj)
            except ValueError:
                pass
        
        return max(dates) if dates else None
    
    def build_filename(self, article_id: int, title: str) -> str:
        """Build filename from ID and title."""
        slug = re.sub(r'[^\w\s-]', '', title).strip().lower()
        slug = re.sub(r'[-\s]+', '_', slug)
        return f"{article_id:03d}_{slug}.mdx"
