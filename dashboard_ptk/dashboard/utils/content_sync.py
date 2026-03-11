"""
Content file system operations.

Handles reading/writing content files and syncing with articles.json.
"""
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console

from ..engine.content_locator import resolve_content_dir
from .errors import (
    ArticlesJsonError,
    SyncError,
    ContentNotFoundError,
)

console = Console()


class ContentSync:
    """Manages content file operations and syncing."""
    
    def __init__(self, articles_json_path: Path, content_dir: Path):
        self.articles_json_path = articles_json_path
        self.content_dir = content_dir
    
    def find_content_dir(self, repo_root: Path) -> Optional[Path]:
        """Find the content directory using the shared content locator."""
        resolution = resolve_content_dir(
            repo_root=repo_root,
            include_empty_auto_fallback=False,
        )
        return resolution.selected if resolution.selected_has_markdown else None
    
    def build_filename(self, article_id: int, title: str) -> str:
        """Build filename from article ID and title."""
        slug = re.sub(r'[^\w\s-]', '', title).strip().lower()
        slug = re.sub(r'[-\s]+', '_', slug)
        return f"{article_id:03d}_{slug}.mdx"
    
    def extract_frontmatter(self, content_path: Path) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """Extract title, date, description from frontmatter."""
        try:
            content = content_path.read_text()
            lines = content.split('\n')
            
            if lines[0].strip() != '---':
                return None, None, None
            
            title = date = description = None
            
            for line in lines[1:]:
                if line.strip() == '---':
                    break
                if line.startswith('title:'):
                    title = line.split(':', 1)[1].strip().strip('"').strip("'")
                elif line.startswith('date:'):
                    date = line.split(':', 1)[1].strip().strip('"').strip("'")
                elif line.startswith('description:'):
                    description = line.split(':', 1)[1].strip().strip('"').strip("'")
            
            return title, date, description
        except Exception:
            return None, None, None
    
    def sync_with_directory(self, dry_run: bool = True, raise_on_error: bool = False) -> dict:
        """
        Sync articles.json with content directory.
        
        Args:
            dry_run: If True, don't make changes
            raise_on_error: If True, raise exceptions instead of returning error dict
        
        Returns:
            Dict with 'added', 'removed', 'next_id_updated'
        
        Raises:
            ArticlesJsonError, SyncError, ContentNotFoundError
        """
        result = {
            "added": [],
            "removed": [],
            "next_id_updated": False,
            "error": None
        }
        
        try:
            data = json.loads(self.articles_json_path.read_text())
            articles = data.get("articles", [])
        except json.JSONDecodeError as e:
            if raise_on_error:
                raise ArticlesJsonError(f"Invalid JSON: {e}")
            result["error"] = f"Could not read articles.json: {e}"
            return result
        except Exception as e:
            if raise_on_error:
                raise ArticlesJsonError(str(e))
            result["error"] = f"Could not read articles.json: {e}"
            return result
        
        # Get all content files
        if not self.content_dir or not self.content_dir.exists():
            if raise_on_error:
                raise ContentNotFoundError(str(self.content_dir))
            result["error"] = f"Content directory not found: {self.content_dir}"
            return result
        
        content_files = list(self.content_dir.glob("*.mdx")) + list(self.content_dir.glob("*.md"))
        content_filenames = {f.name for f in content_files}
        
        # Build lookup
        file_to_article = {}
        id_to_article = {}
        for a in articles:
            if a.get("file"):
                fname = Path(a["file"]).name
                file_to_article[fname] = a
            if a.get("id"):
                id_to_article[a["id"]] = a
        
        # Find untracked files
        for content_file in content_files:
            fname = content_file.name
            if fname not in file_to_article:
                # Extract metadata
                title, date, desc = self.extract_frontmatter(content_file)
                word_count = len(content_file.read_text().split())
                
                # Extract ID from filename
                match = re.match(r'^(\d+)_(.+?)\.mdx?$', fname)
                if match:
                    file_id = int(match.group(1))
                    
                    # Check for ID conflict
                    if file_id in id_to_article:
                        continue  # Skip - need manual resolution
                    
                    new_article = {
                        "id": file_id,
                        "title": title or f"Article {file_id}",
                        "url_slug": re.sub(r'^\d+_', '', fname.replace('.mdx', '').replace('.md', '')),
                        "file": f"./content/{fname}",
                        "target_keyword": "",
                        "keyword_difficulty": "",
                        "target_volume": 0,
                        "published_date": date or datetime.now().strftime('%Y-%m-%d'),
                        "word_count": word_count,
                        "status": "published",
                        "content_gaps_addressed": [],
                        "estimated_traffic_monthly": ""
                    }
                    
                    result["added"].append({
                        "id": file_id,
                        "filename": fname,
                        "title": new_article["title"]
                    })
                    
                    if not dry_run:
                        articles.append(new_article)
                        id_to_article[file_id] = new_article
                        file_to_article[fname] = new_article
        
        # Find orphaned entries
        for fname, article in list(file_to_article.items()):
            if fname not in content_filenames:
                result["removed"].append({
                    "id": article.get("id"),
                    "filename": fname
                })
                if not dry_run:
                    articles.remove(article)
        
        # Update nextArticleId
        if not dry_run and articles:
            max_id = max(a["id"] for a in articles)
            if data.get("nextArticleId") != max_id + 1:
                data["nextArticleId"] = max_id + 1
                result["next_id_updated"] = True
        
        # Save if changes made
        if not dry_run and (result["added"] or result["removed"] or result["next_id_updated"]):
            try:
                self.articles_json_path.write_text(json.dumps(data, indent=2))
            except Exception as e:
                if raise_on_error:
                    raise SyncError("save", str(e))
                result["error"] = f"Could not save articles.json: {e}"
        
        return result
    
    def add_article_entry(self, article_id: int, title: str, filename: str,
                         publish_date: str, word_count: int,
                         target_keyword: str = "", raise_on_error: bool = False) -> bool:
        """
        Add new article entry to articles.json.
        
        Args:
            article_id: Article ID
            title: Article title
            filename: Content filename
            publish_date: Publish date (YYYY-MM-DD)
            word_count: Word count
            target_keyword: Target SEO keyword
            raise_on_error: If True, raise exception on failure
        
        Returns:
            True on success, False on failure (unless raise_on_error=True)
        
        Raises:
            ArticlesJsonError, SyncError
        """
        try:
            data = json.loads(self.articles_json_path.read_text())
            articles = data.get("articles", [])
            
            # Generate slug from filename
            slug = filename.replace(".mdx", "").replace(".md", "")
            slug = re.sub(r'^\d+_', '', slug)
            
            new_article = {
                "id": article_id,
                "title": title,
                "url_slug": slug,
                "file": f"./content/{filename}",
                "target_keyword": target_keyword or slug.replace("_", " "),
                "keyword_difficulty": "",
                "target_volume": 0,
                "published_date": publish_date,
                "word_count": word_count,
                "status": "draft",
                "content_gaps_addressed": [],
                "estimated_traffic_monthly": ""
            }
            
            articles.append(new_article)
            data["articles"] = articles
            
            if "statistics" in data:
                data["statistics"]["total_articles"] = len(articles)
                data["statistics"]["last_updated"] = datetime.now().strftime('%Y-%m-%d')
            
            self.articles_json_path.write_text(json.dumps(data, indent=2))
            console.print(f"[green]✓ Updated articles.json (ID: {article_id})[/green]")
            return True
            
        except json.JSONDecodeError as e:
            if raise_on_error:
                raise ArticlesJsonError(f"Invalid JSON: {e}")
            console.print(f"[yellow]⚠ Could not read articles.json: {e}[/yellow]")
            return False
        except Exception as e:
            if raise_on_error:
                raise SyncError("add_entry", str(e))
            console.print(f"[yellow]⚠ Could not update articles.json: {e}[/yellow]")
            return False
