"""SEO content operations for automation-mcp"""

import json
import re
import difflib
import os
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional

def _detect_repo_root() -> Path:
    env_root = os.environ.get('WORKSPACE_ROOT') or os.environ.get('AUTOMATION_REPO_ROOT')
    if env_root:
        return Path(env_root).expanduser().resolve()

    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / 'WEBSITES_REGISTRY.json').exists() and (parent / 'mcp').exists():
            return parent

    raise RuntimeError('Could not detect repo root; set WORKSPACE_ROOT')


REPO_ROOT = _detect_repo_root()


def _get_project_path(website_path: str) -> Path:
    """Get absolute path to project"""
    return REPO_ROOT / website_path


def _load_articles_json(website_path: str) -> Dict[str, Any]:
    """Load articles.json for a project"""
    project_path = _get_project_path(website_path)
    articles_file = project_path / "articles.json"
    
    if not articles_file.exists():
        return {"articles": []}
    
    with open(articles_file, 'r') as f:
        return json.load(f)


def _save_articles_json(website_path: str, data: Dict[str, Any]):
    """Save articles.json for a project"""
    project_path = _get_project_path(website_path)
    articles_file = project_path / "articles.json"
    
    with open(articles_file, 'w') as f:
        json.dump(data, f, indent=2)


def get_articles_summary(website_path: str) -> Dict[str, Any]:
    """Get summary statistics for articles"""
    data = _load_articles_json(website_path)
    articles = data.get("articles", [])
    
    if not articles:
        return {
            "website_path": website_path,
            "total_articles": 0,
            "max_id": 0,
            "next_id": 1,
            "status_counts": {}
        }
    
    # Calculate stats
    ids = [a.get("id", 0) for a in articles if a.get("id")]
    max_id = max(ids) if ids else 0
    
    status_counts = {}
    for article in articles:
        status = article.get("status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    
    return {
        "website_path": website_path,
        "total_articles": len(articles),
        "max_id": max_id,
        "next_id": max_id + 1,
        "status_counts": status_counts
    }


def get_next_article_id(website_path: str) -> int:
    """Get next available article ID"""
    summary = get_articles_summary(website_path)
    return summary["next_id"]


def filter_new_keywords(website_path: str, keywords: List[str]) -> Dict[str, Any]:
    """Filter keywords against existing articles"""
    data = _load_articles_json(website_path)
    articles = data.get("articles", [])
    
    # Get existing target keywords
    existing_keywords = set()
    for article in articles:
        if article.get("target_keyword"):
            existing_keywords.add(article["target_keyword"].lower())
    
    # Check each keyword
    new_keywords = []
    matches = []
    
    for kw in keywords:
        kw_lower = kw.lower()
        if kw_lower in existing_keywords:
            matches.append({
                "input_keyword": kw,
                "matched_existing_keyword": kw,
                "match_type": "exact"
            })
        else:
            new_keywords.append(kw)
    
    return {
        "website_path": website_path,
        "total_articles": len(articles),
        "existing_unique_keywords": len(existing_keywords),
        "input_keywords": len(keywords),
        "new_keywords": new_keywords,
        "matches": matches
    }


def append_draft_articles(website_path: str, drafts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Append draft articles to articles.json"""
    data = _load_articles_json(website_path)
    articles = data.get("articles", [])
    
    added = 0
    skipped = 0
    
    for draft in drafts:
        # Check for duplicates
        target_kw = draft.get("target_keyword", "").lower()
        is_duplicate = False
        
        for article in articles:
            if article.get("target_keyword", "").lower() == target_kw:
                is_duplicate = True
                break
        
        if is_duplicate:
            skipped += 1
            continue
        
        # Assign ID
        next_id = get_next_article_id(website_path) + added
        draft["id"] = next_id
        draft["status"] = "draft"
        draft["created_at"] = datetime.now().isoformat()
        
        articles.append(draft)
        added += 1
    
    data["articles"] = articles
    _save_articles_json(website_path, data)
    
    return {
        "website_path": website_path,
        "added": added,
        "skipped": skipped,
        "total_articles": len(articles)
    }


def get_articles_by_keyword(website_path: str, keyword: str) -> Dict[str, Any]:
    """Find articles by keyword"""
    data = _load_articles_json(website_path)
    articles = data.get("articles", [])
    
    keyword_lower = keyword.lower()
    matches = []
    
    for article in articles:
        # Exact match
        if article.get("target_keyword", "").lower() == keyword_lower:
            matches.append(article)
            continue
        
        # Check title
        if keyword_lower in article.get("title", "").lower():
            matches.append(article)
            continue
        
        # Check content
        if keyword_lower in article.get("content", "").lower():
            matches.append(article)
    
    return {
        "website_path": website_path,
        "keyword": keyword,
        "matches": matches,
        "count": len(matches)
    }


def get_articles_index(website_path: str, status: str = "") -> List[Dict[str, Any]]:
    """Get index of articles"""
    data = _load_articles_json(website_path)
    articles = data.get("articles", [])
    
    if status:
        articles = [a for a in articles if a.get("status") == status]
    
    # Return minimal fields
    index = []
    for article in articles:
        index.append({
            "id": article.get("id"),
            "title": article.get("title"),
            "target_keyword": article.get("target_keyword"),
            "status": article.get("status"),
            "file": article.get("file"),
            "published_date": article.get("published_date")
        })
    
    return index


def validate_content(website_path: str) -> Dict[str, Any]:
    """Validate content files"""
    project_path = _get_project_path(website_path)
    content_dir = project_path / "content"
    
    if not content_dir.exists():
        return {"error": f"Content directory not found: {content_dir}"}
    
    issues = []
    files_checked = 0
    
    for md_file in content_dir.glob("*.md"):
        files_checked += 1
        content = md_file.read_text()
        
        # Check for duplicate H1
        h1_matches = re.findall(r'^# (.+)$', content, re.MULTILINE)
        if len(h1_matches) > 1:
            issues.append({
                "file": str(md_file.name),
                "issue": "duplicate_h1",
                "details": f"Found {len(h1_matches)} H1 headings"
            })
    
    return {
        "website_path": website_path,
        "files_checked": files_checked,
        "issues_found": len(issues),
        "issues": issues
    }


def clean_content(website_path: str) -> Dict[str, Any]:
    """Clean content files"""
    # Stub implementation
    return {
        "website_path": website_path,
        "files_cleaned": 0,
        "note": "Stub implementation"
    }


def analyze_dates(website_path: str) -> Dict[str, Any]:
    """Analyze date distribution"""
    data = _load_articles_json(website_path)
    articles = data.get("articles", [])
    
    today = date.today()
    issues = []
    
    for article in articles:
        pub_date = article.get("published_date")
        if not pub_date:
            issues.append({
                "article_id": article.get("id"),
                "issue": "missing_date"
            })
            continue
        
        try:
            article_date = datetime.strptime(pub_date, "%Y-%m-%d").date()
            if article_date > today:
                issues.append({
                    "article_id": article.get("id"),
                    "issue": "future_date",
                    "date": pub_date
                })
        except:
            issues.append({
                "article_id": article.get("id"),
                "issue": "invalid_date",
                "date": pub_date
            })
    
    return {
        "website_path": website_path,
        "total_articles": len(articles),
        "issues_found": len(issues),
        "issues": issues
    }


def fix_dates(website_path: str) -> Dict[str, Any]:
    """Fix date distribution issues"""
    # Stub implementation
    return {
        "website_path": website_path,
        "articles_fixed": 0,
        "note": "Stub implementation"
    }


def test_distribution(website_path: str) -> Dict[str, Any]:
    """Test date distribution"""
    # Stub implementation
    return {
        "website_path": website_path,
        "distribution": "even",
        "note": "Stub implementation"
    }


def get_next_content_task(website_path: str) -> Optional[Dict[str, Any]]:
    """Get next content task"""
    data = _load_articles_json(website_path)
    articles = data.get("articles", [])
    
    # Find first draft article
    for article in articles:
        if article.get("status") == "draft":
            return {
                "id": article.get("id"),
                "title": article.get("title"),
                "target_keyword": article.get("target_keyword"),
                "status": "draft"
            }
    
    return None


def plan_content_article(website_path: str, task_id: int) -> Dict[str, Any]:
    """Plan article metadata"""
    data = _load_articles_json(website_path)
    articles = data.get("articles", [])
    
    for article in articles:
        if article.get("id") == task_id:
            return {
                "id": task_id,
                "title": article.get("title"),
                "target_keyword": article.get("target_keyword"),
                "slug": article.get("slug", ""),
                "file": article.get("file", ""),
                "planned": True
            }
    
    return {"error": f"Article with id {task_id} not found"}


def publish_article_and_complete_task(website_path: str, article_data: Dict[str, Any]) -> Dict[str, Any]:
    """Publish article and mark complete"""
    data = _load_articles_json(website_path)
    articles = data.get("articles", [])
    
    article_id = article_data.get("id")
    
    for i, article in enumerate(articles):
        if article.get("id") == article_id:
            articles[i]["status"] = "published"
            articles[i]["published_at"] = datetime.now().isoformat()
            break
    
    data["articles"] = articles
    _save_articles_json(website_path, data)
    
    return {
        "success": True,
        "article_id": article_id,
        "action": "published"
    }


def ops_schedule_apply(website_id: str, auto_fix: bool = True) -> Dict[str, Any]:
    """Apply scheduling"""
    return {
        "website_id": website_id,
        "scheduled": True,
        "auto_fix": auto_fix,
        "note": "Stub implementation"
    }


def ops_sync_and_optimize(website_id: str, auto_fix: bool = True, 
                         auto_deploy: bool = False, dry_run: bool = False) -> Dict[str, Any]:
    """Sync and optimize"""
    return {
        "website_id": website_id,
        "synced": True,
        "auto_fix": auto_fix,
        "auto_deploy": auto_deploy,
        "dry_run": dry_run,
        "note": "Stub implementation"
    }
