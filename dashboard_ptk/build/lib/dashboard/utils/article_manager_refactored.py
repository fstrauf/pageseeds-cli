"""
Article management - Refactored facade.

Delegates to specialized classes:
- DateManager: Date allocation and scheduling
- IntegrityChecker: Validation and integrity checks
- ContentSync: File system operations
"""
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console

from ..engine.content_locator import resolve_content_dir
from .date_manager import DateManager
from .integrity_checker import IntegrityChecker
from .content_sync import ContentSync

console = Console()


def generate_url_slug(filename: str) -> str:
    """Generate url_slug from filename."""
    import re
    basename = Path(filename).name
    basename = basename.replace(".mdx", "").replace(".md", "")
    slug = re.sub(r'^\d+_', '', basename)
    return slug


class ArticleManager:
    """
    Facade for article management operations.
    
    Delegates to specialized classes for specific concerns.
    """
    
    def __init__(self, website_id: str):
        self.website_id = website_id
        self._repo_root: Optional[Path] = None
        self._articles_json: Optional[Path] = None
        self._content_dir: Optional[Path] = None
        
        # Lazy-loaded delegates
        self._date_mgr: Optional[DateManager] = None
        self._integrity: Optional[IntegrityChecker] = None
        self._sync: Optional[ContentSync] = None
    
    def _init_paths(self, repo_root: Optional[Path] = None):
        """Initialize paths if not already done."""
        from ..config import get_repo_root
        root = repo_root or get_repo_root()
        
        # Reinitialize if repo_root changed or paths not set
        if self._repo_root and self._repo_root != root:
            # Clear cached paths when switching projects
            self._articles_json = None
            self._content_dir = None
            self._date_mgr = None
            self._integrity = None
            self._sync = None
        
        if self._articles_json and self._content_dir:
            return
        
        self._repo_root = root
        
        # Find articles.json
        automation_dir = root / ".github" / "automation"
        self._articles_json = automation_dir / "articles.json"
        
        # Find content directory
        self._content_dir = self._find_content_dir(root)
    
    def _find_content_dir(self, root: Path) -> Optional[Path]:
        """Find content directory via shared resolver (configured override + fallback order)."""
        resolution = resolve_content_dir(
            repo_root=root,
            website_id=self.website_id,
            include_empty_auto_fallback=True,
        )
        return resolution.selected
    
    def _get_date_mgr(self) -> DateManager:
        """Lazy-load DateManager."""
        if not self._date_mgr:
            self._date_mgr = DateManager(self._articles_json)
        return self._date_mgr
    
    def _get_integrity(self) -> IntegrityChecker:
        """Lazy-load IntegrityChecker."""
        if not self._integrity:
            self._integrity = IntegrityChecker(self._articles_json, self._content_dir)
        return self._integrity
    
    def _get_sync(self) -> ContentSync:
        """Lazy-load ContentSync."""
        if not self._sync:
            self._sync = ContentSync(self._articles_json, self._content_dir)
        return self._sync
    
    # === Public API ===
    
    def get_articles_json_path(self, repo_root: Optional[Path] = None) -> Optional[Path]:
        """Get path to articles.json."""
        self._init_paths(repo_root)
        return self._articles_json
    
    def get_content_dir(self, repo_root: Optional[Path] = None) -> Optional[Path]:
        """Get content directory."""
        self._init_paths(repo_root)
        return self._content_dir
    
    def get_next_id(self, repo_root: Optional[Path] = None) -> int:
        """Get next available article ID."""
        self._init_paths(repo_root)
        
        try:
            import json
            data = json.loads(self._articles_json.read_text())
            articles = data.get("articles", [])
            if articles:
                return max(a.get("id", 0) for a in articles) + 1
        except Exception:
            pass
        return 1
    
    def get_next_available_date(self, repo_root: Optional[Path] = None) -> datetime:
        """Get next available date for scheduling."""
        self._init_paths(repo_root)
        return self._get_date_mgr().get_next_available_date()
    
    def get_latest_date(self, repo_root: Optional[Path] = None, 
                       include_drafts: bool = True) -> tuple[Optional[datetime], list]:
        """Get most recent article date."""
        self._init_paths(repo_root)
        return self._get_date_mgr().get_latest_date(include_drafts)
    
    def get_available_slots(self, count: int = 4) -> list[str]:
        """Get next N available date slots."""
        return self._get_date_mgr().get_available_slots(count)
    
    def validate_new_article(self, title: str, proposed_date: str,
                            repo_root: Optional[Path] = None) -> tuple[bool, str]:
        """Validate before creating new article."""
        self._init_paths(repo_root)
        
        next_id = self.get_next_id(repo_root)
        return self._get_integrity().validate_new_article(
            title, proposed_date, next_id, self._content_dir
        )
    
    def check_integrity(self, repo_root: Optional[Path] = None) -> list[str]:
        """Run all integrity checks."""
        self._init_paths(repo_root)
        return self._get_integrity().check_all()
    
    def build_filename(self, article_id: int, title: str) -> str:
        """Build filename from ID and title."""
        return self._get_sync().build_filename(article_id, title)
    
    def add_article(self, article_id: int, title: str, filename: str,
                   publish_date: str, word_count: int,
                   target_keyword: str = "",
                   repo_root: Optional[Path] = None) -> bool:
        """Add article entry to articles.json."""
        self._init_paths(repo_root)
        return self._get_sync().add_article_entry(
            article_id, title, filename, publish_date, word_count, target_keyword
        )
    
    def sync_with_content_dir(self, repo_root: Optional[Path] = None,
                             dry_run: bool = True) -> dict:
        """Sync articles.json with content directory."""
        self._init_paths(repo_root)
        return self._get_sync().sync_with_directory(dry_run)
    
    # === Legacy methods (for backward compatibility) ===
    
    def check_slug_alignment(self, repo_root: Optional[Path] = None) -> list[dict]:
        """Check slug alignment (legacy method)."""
        import json
        import re
        
        self._init_paths(repo_root)
        mismatches = []
        
        try:
            data = json.loads(self._articles_json.read_text())
            articles = data.get("articles", [])
            
            for article in articles:
                url_slug = str(article.get("url_slug") or "").strip()
                file_path = str(article.get("file") or "").strip()
                
                if not url_slug or not file_path:
                    continue
                
                filename = Path(file_path).name
                expected = generate_url_slug(filename)
                
                if url_slug != expected:
                    mismatches.append({
                        "id": article.get("id"),
                        "url_slug": url_slug,
                        "filename": filename,
                        "expected_slug": expected,
                    })
        except Exception:
            pass
        
        return mismatches
    
    def repair_slugs(self, repo_root: Optional[Path] = None, 
                    dry_run: bool = True) -> dict:
        """Repair slug mismatches."""
        import json
        
        self._init_paths(repo_root)
        
        result = {"fixed": [], "unchanged": 0, "total": 0, "error": None}
        
        try:
            data = json.loads(self._articles_json.read_text())
            articles = data.get("articles", [])
            
            for article in articles:
                filename = Path(article.get("file", "")).name
                expected = generate_url_slug(filename)
                
                if article.get("url_slug") != expected:
                    result["fixed"].append({
                        "id": article.get("id"),
                        "old_slug": article.get("url_slug"),
                        "new_slug": expected,
                    })
                    if not dry_run:
                        article["url_slug"] = expected
            
            result["unchanged"] = len(articles) - len(result["fixed"])
            result["total"] = len(articles)
            
            if not dry_run and result["fixed"]:
                self._articles_json.write_text(json.dumps(data, indent=2))
                console.print(f"[green]✓ Fixed {len(result['fixed'])} slug(s)[/green]")
        
        except Exception as e:
            result["error"] = str(e)
        
        return result
    
    def find_existing(self, search_title: str, 
                     repo_root: Optional[Path] = None) -> Optional[dict]:
        """Find existing article by title."""
        import json
        
        self._init_paths(repo_root)
        
        try:
            data = json.loads(self._articles_json.read_text())
            articles = data.get("articles", [])
            
            search_clean = search_title
            if search_clean.lower().startswith("optimize:"):
                search_clean = search_clean.split(":", 1)[1].strip()
            
            search_lower = search_clean.lower()
            search_words = set(search_lower.split())
            
            best_match = None
            best_score = 0
            
            for article in articles:
                title = article.get("title", "").lower()
                url_slug = article.get("url_slug", "").lower()
                
                # Normalize for comparison (hyphens vs underscores)
                search_normalized = search_lower.replace("-", "_").replace(" ", "_")
                url_slug_normalized = url_slug.replace("-", "_").replace(" ", "_")
                
                score = 0
                if search_lower in title or title in search_lower:
                    score += 100
                
                title_words = set(title.split())
                overlap = len(search_words & title_words)
                score += overlap * 10
                
                # Direct url_slug match
                if search_lower in url_slug or url_slug in search_lower:
                    score += 50
                
                # Normalized url_slug match (handles hyphen/underscore differences)
                if search_normalized == url_slug_normalized:
                    score += 75
                elif search_normalized in url_slug_normalized or url_slug_normalized in search_normalized:
                    score += 40
                
                if score > best_score and score >= 20:
                    best_score = score
                    best_match = article
            
            return best_match
            
        except Exception:
            return None

    def update_word_count(self, article_id: int, word_count: int,
                          repo_root: Optional[Path] = None) -> bool:
        """Update word count for an article in articles.json."""
        import json
        
        self._init_paths(repo_root)
        
        try:
            data = json.loads(self._articles_json.read_text())
            articles = data.get("articles", [])
            
            for article in articles:
                if article.get("id") == article_id:
                    article["word_count"] = word_count
                    break
            
            self._articles_json.write_text(json.dumps(data, indent=2))
            return True
            
        except Exception:
            return False
