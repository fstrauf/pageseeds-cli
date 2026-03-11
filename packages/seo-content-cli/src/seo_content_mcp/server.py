"""SEO Content MCP Server - Main server implementation"""

import os
import json
from datetime import datetime, timedelta, date
from enum import Enum
from pathlib import Path
from typing import Any
import re
import difflib
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
from pydantic import BaseModel, Field

from .content_cleaner import ContentCleaner, format_cleaning_result
from .date_distributor import DateDistributor, format_date_analysis, format_date_fix
from .seo_ops import SEOOps


class SEOTools(str, Enum):
    """Available SEO content tools"""
    TEST_DISTRIBUTION = "seo_test_distribution"
    CLEAN_CONTENT = "seo_clean_content"
    VALIDATE_CONTENT = "seo_validate_content"
    ANALYZE_DATES = "seo_analyze_dates"
    FIX_DATES = "seo_fix_dates"
    FILTER_NEW_KEYWORDS = "seo_filter_new_keywords"
    GET_ARTICLES_SUMMARY = "seo_get_articles_summary"
    GET_NEXT_ARTICLE_ID = "seo_get_next_article_id"
    APPEND_DRAFT_ARTICLES = "seo_append_draft_articles"
    GET_ARTICLES_BY_KEYWORD = "seo_get_articles_by_keyword"
    GET_NEXT_CONTENT_TASK = "seo_get_next_content_task"
    PLAN_CONTENT_ARTICLE = "seo_plan_content_article"
    PUBLISH_ARTICLE_AND_COMPLETE_TASK = "seo_publish_article_and_complete_task"
    GET_ARTICLES_INDEX = "seo_get_articles_index"

    # Clustering & Linking (Step 3)
    SCAN_INTERNAL_LINKS = "seo_scan_internal_links"
    GENERATE_LINKING_PLAN = "seo_generate_linking_plan"
    ADD_ARTICLE_LINKS = "seo_add_article_links"
    GET_ARTICLE_CONTENT = "seo_get_article_content"
    UPDATE_BRIEF_LINKING_STATUS = "seo_update_brief_linking_status"
    BATCH_ADD_LINKS = "seo_batch_add_links"

    # SEO Ops (registry-driven, mirrors Flask UI)
    OPS_OVERVIEW = "seo_ops_overview"
    OPS_SITE_METRICS = "seo_ops_site_metrics"
    OPS_DRIFT = "seo_ops_drift"
    OPS_IMPORT_PREVIEW = "seo_ops_import_preview"
    OPS_IMPORT_APPLY = "seo_ops_import_apply"
    OPS_DATES_ANALYZE = "seo_ops_dates_analyze"
    OPS_SCHEDULE_PREVIEW = "seo_ops_schedule_preview"
    OPS_SCHEDULE_APPLY = "seo_ops_schedule_apply"
    OPS_REPORT_OVERVIEW_MARKDOWN = "seo_ops_report_overview_markdown"
    OPS_REPORT_SITE_MARKDOWN = "seo_ops_report_site_markdown"
    OPS_VALIDATE_INDEX = "seo_ops_validate_index"
    OPS_SYNC_AND_OPTIMIZE = "seo_ops_sync_and_optimize"


class DistributionResult(BaseModel):
    """Result of a date distribution test"""
    project_name: str
    article_count: int
    earliest_date: str
    today_date: str
    days_available: int
    days_per_article: int
    distribution: list[dict[str, Any]]


class KeywordMatch(BaseModel):
    """A match between an input keyword and an existing target keyword."""

    input_keyword: str
    matched_existing_keyword: str
    match_type: str = Field(
        description="One of: exact, canonical, fuzzy",
    )
    matched_article_ids: list[int] = Field(default_factory=list)


class KeywordFilterResult(BaseModel):
    """Result of filtering candidate keywords against existing target keywords."""

    website_path: str
    total_articles: int
    existing_unique_keywords: int
    input_keywords: int
    new_keywords: list[str]
    matches: list[KeywordMatch]


class ArticlesSummary(BaseModel):
    """Summary stats for a project's articles.json."""

    website_path: str
    total_articles: int
    max_id: int
    next_id: int
    articles_with_target_keywords: int
    existing_unique_keywords: int
    status_counts: dict[str, int]


class DraftArticleInput(BaseModel):
    """Input model for appending a new draft article."""

    title: str
    target_keyword: str
    keyword_difficulty: str | int | float | None = ""
    target_volume: int | None = 0
    estimated_traffic_monthly: str | int | None = ""
    content_gaps_addressed: list[str] = Field(default_factory=list)
    url_slug: str | None = None
    file: str | None = None


class AppendDraftResult(BaseModel):
    """Result of appending one or more draft articles."""

    website_path: str
    added_ids: list[int]
    added: list[dict[str, Any]]


class ArticleKeywordMatch(BaseModel):
    """An article that matches a queried keyword."""

    article_id: int
    title: str
    status: str
    target_keyword: str
    match_type: str  # exact|canonical|fuzzy
    score: float | None = None


class ArticlesByKeywordResult(BaseModel):
    website_path: str
    query_keyword: str
    normalized_query: str
    canonical_query: str
    matches: list[ArticleKeywordMatch]


class ContentTask(BaseModel):
    task_id: str
    priority: str
    status: str
    article_title: str | None = None
    cluster: str | None = None
    type: str | None = None
    fills_gap: str | None = None
    target_keyword: str | None = None
    target_keywords: list[str] = Field(default_factory=list)
    est_kd: str | None = None
    est_volume: str | None = None
    est_traffic: str | None = None
    links_to: str | None = None
    created_article_id: str | None = None
    notes: str | None = None


class PlannedContentArticle(BaseModel):
    website_path: str
    brief_path: str
    task: ContentTask
    article_id: int
    url_slug: str
    file: str
    published_date: str
    frontmatter: str


class PublishAndCompleteResult(BaseModel):
    website_path: str
    brief_path: str
    task_id: str
    article_id: int
    updated_articles_json: bool
    updated_brief: bool


class ArticleIndexItem(BaseModel):
    id: int
    title: str
    target_keyword: str
    status: str
    file: str
    url_slug: str | None = None
    published_date: str | None = None


class ArticlesIndexResult(BaseModel):
    website_path: str
    total: int
    items: list[ArticleIndexItem]


class SEOContentServer:
    """Server for SEO content management operations"""
    
    def __init__(self, workspace_root: str | None = None):
        """Initialize the server with workspace root path"""
        self.workspace_root = workspace_root or os.getcwd()
        self.cleaner = ContentCleaner(self.workspace_root)
        self.distributor = DateDistributor(self.workspace_root)
        
    def test_distribution(
        self,
        project_name: str,
        article_count: int,
        earliest_date: str
    ) -> DistributionResult:
        """
        Test date distribution for articles without making changes.
        
        This demonstrates how articles would be distributed across the date range
        from earliest_date to today, ensuring even spacing and no clustering.
        
        Args:
            project_name: Name of the project (e.g., "Coffee", "Expense")
            article_count: Number of articles to distribute
            earliest_date: Earliest date in YYYY-MM-DD format
            
        Returns:
            DistributionResult with preview of how articles would be distributed
        """
        # Parse dates
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        earliest = datetime.strptime(earliest_date, '%Y-%m-%d')
        earliest = earliest.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Calculate distribution
        days_available = (today - earliest).days + 1
        days_per_article = max(1, days_available // article_count)
        
        # Generate distribution
        distribution = []
        
        # Show representative samples (first 5, middle, last 5)
        show_indices = self._get_sample_indices(article_count)
        
        for index in show_indices:
            days_offset = index * days_per_article
            article_date = earliest + timedelta(days=days_offset)
            
            # Cap at today
            if article_date > today:
                article_date = today
            
            marker = ""
            if index == 0:
                marker = " (first)"
            elif index == article_count - 1:
                marker = " (last)"
            elif index == article_count // 2:
                marker = " (middle)"
                
            distribution.append({
                "article_number": index + 1,
                "date": article_date.strftime('%Y-%m-%d'),
                "marker": marker.strip() if marker else None
            })
        
        # Add ellipsis indicator if we're showing a subset
        if len(show_indices) < article_count:
            middle_idx = len(distribution) // 2
            distribution.insert(middle_idx, {
                "article_number": None,
                "date": "...",
                "marker": f"({article_count - len(show_indices)} more articles)"
            })
        
        return DistributionResult(
            project_name=project_name,
            article_count=article_count,
            earliest_date=earliest_date,
            today_date=today.strftime('%Y-%m-%d'),
            days_available=days_available,
            days_per_article=days_per_article,
            distribution=distribution
        )
    
    def _get_sample_indices(self, article_count: int) -> list[int]:
        """
        Get sample indices to show in distribution.
        Shows first 5, middle, and last 5 articles.
        """
        if article_count <= 12:
            # Show all if small
            return list(range(article_count))
        
        indices = set()
        
        # First 5
        for i in range(min(5, article_count)):
            indices.add(i)
        
        # Middle
        indices.add(article_count // 2)
        
        # Last 5
        for i in range(max(0, article_count - 5), article_count):
            indices.add(i)
        
        return sorted(list(indices))


def _normalize_keyword(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _canonicalize_keyword(text: str) -> str:
    normalized = _normalize_keyword(text)
    # Keep only letters/numbers/spaces to collapse punctuation variants.
    normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _load_articles_json(workspace_root: str, website_path: str) -> dict[str, Any]:
    articles_path = Path(workspace_root) / website_path / "articles.json"
    if not articles_path.exists():
        raise FileNotFoundError(f"articles.json not found at: {articles_path}")
    with articles_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _save_articles_json(workspace_root: str, website_path: str, data: dict[str, Any]) -> None:
    articles_path = Path(workspace_root) / website_path / "articles.json"
    articles_path.parent.mkdir(parents=True, exist_ok=True)
    with articles_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _slugify(text: str) -> str:
    s = _canonicalize_keyword(text)
    s = s.replace(" ", "-")
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "article"


def _resolve_brief_path(
    *,
    workspace_root: str,
    website_path: str,
    brief_path: str | None,
) -> Path:
    if brief_path:
        p = Path(brief_path)
        if p.is_absolute():
            return p
        return Path(workspace_root) / brief_path

    folder = Path(workspace_root) / website_path
    patterns = ["*_seo_content_brief.md", "*_sorted_content_brief.md", "*_content_brief.md"]
    candidates: list[Path] = []
    for pattern in patterns:
        candidates.extend(folder.glob(pattern))
    candidates = sorted(set(candidates))
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise FileNotFoundError(
            (
                f"No content brief found under {website_path}. "
                "Expected one of: '*_seo_content_brief.md', '*_sorted_content_brief.md', '*_content_brief.md'. "
                "Provide brief_path explicitly."
            )
        )
    raise FileNotFoundError(
        (
            f"Multiple content brief candidates found under {website_path}. "
            "Provide brief_path explicitly."
        )
    )


def _load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _save_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _parse_content_tasks_from_brief(brief_text: str) -> list[ContentTask]:
    # Very lightweight parser tailored to the repo's task format.
    # Tasks are under headings like: "### HIGH PRIORITY - ..." then blocks starting with "#### Task ID: X".
    priority = "UNKNOWN"
    tasks: list[ContentTask] = []

    lines = brief_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        m_pri = re.match(r"^###\s+([A-Z ]+PRIORITY)\b", line)
        if m_pri:
            priority = m_pri.group(1).strip()
            i += 1
            continue

        m_task = re.match(r"^####\s+Task ID:\s*(.+?)\s*$", line)
        if not m_task:
            i += 1
            continue

        task_id = m_task.group(1).strip()
        block_lines: list[str] = []
        i += 1
        while i < len(lines):
            l = lines[i]
            if l.strip().startswith("#### Task ID:"):
                break
            # Stop on horizontal divider between tasks.
            if l.strip() == "---" and block_lines:
                # keep the separator out
                i += 1
                break
            block_lines.append(l)
            i += 1

        def _field(name: str) -> str | None:
            # Matches: - **Name:** value
            pattern = rf"^\s*-\s*\*\*{re.escape(name)}\*\*:\s*(.*?)\s*$"
            for bl in block_lines:
                mm = re.match(pattern, bl)
                if mm:
                    return mm.group(1).strip()
            return None

        status = _field("Status") or ""
        article_title = _field("Article Title")
        cluster = _field("Cluster")
        type_ = _field("Type")
        fills_gap = _field("Fills Gap")
        target_keyword = _field("Target Keyword")
        target_keywords_raw = _field("Target Keywords")
        target_keywords = []
        if target_keywords_raw:
            target_keywords = [k.strip() for k in target_keywords_raw.split(",") if k.strip()]
        est_kd = None
        est_volume = None
        est_line = _field("Est. KD")
        if est_line and "|" in est_line:
            left, right = est_line.split("|", 1)
            est_kd = left.strip()
            est_volume = right.strip()
        else:
            # Alternative formatting in some briefs: "Est. KD:" line exists and "Est. Volume:" separate.
            est_kd = est_line
            vol = _field("Est. Volume")
            est_volume = vol

        est_traffic = _field("Est. Traffic")
        links_to = _field("Links To")

        created_article_id = (
            _field("Created Article ID")
            or _field("Created Article IDs")
            or _field("Created Article Id")
        )
        notes = _field("Notes")

        tasks.append(
            ContentTask(
                task_id=task_id,
                priority=priority,
                status=status,
                article_title=article_title,
                cluster=cluster,
                type=type_,
                fills_gap=fills_gap,
                target_keyword=target_keyword,
                target_keywords=target_keywords,
                est_kd=est_kd,
                est_volume=est_volume,
                est_traffic=est_traffic,
                links_to=links_to,
                created_article_id=created_article_id,
                notes=notes,
            )
        )

    return tasks


def _is_task_open(status: str) -> bool:
    s = (status or "").strip().lower()
    return "completed" not in s and "✅" not in s


def _safe_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        s = str(value).strip()
        if not s:
            return None
        return int(s)
    except Exception:
        return None


def _get_next_registry_draft_task(
    *,
    workspace_root: str,
    website_path: str,
    requested_priority: str,
) -> ContentTask:
    """Fallback task source when the brief has no structured Task IDs.

    Returns the oldest (lowest id) draft article from articles.json as a ContentTask.
    This prevents the agent from reaching for terminal/Python to discover draft work.
    """
    data = _load_articles_json(workspace_root, website_path)
    drafts: list[dict[str, Any]] = []
    for a in data.get("articles", []):
        if not isinstance(a, dict):
            continue
        st = str(a.get("status") or "").strip().lower()
        if st != "draft":
            continue
        aid = _safe_int(a.get("id"))
        if not aid or aid <= 0:
            continue
        drafts.append(a)

    drafts.sort(key=lambda x: int(x.get("id") or 0))
    if not drafts:
        raise ValueError("No draft articles found in articles.json")

    a0 = drafts[0]
    article_id = int(a0.get("id") or 0)
    title = str(a0.get("title") or "").strip() or f"Draft Article {article_id}"
    target_keyword = str(a0.get("target_keyword") or "").strip()

    return ContentTask(
        task_id=f"REGISTRY_DRAFT:{article_id}",
        priority=(requested_priority or "UNKNOWN"),
        status="draft",
        article_title=title,
        target_keyword=target_keyword,
        est_kd=str(a0.get("keyword_difficulty") or "").strip() or None,
        est_volume=str(a0.get("target_volume") or "").strip() or None,
        est_traffic=str(a0.get("estimated_traffic_monthly") or "").strip() or None,
        links_to=None,
        created_article_id=str(article_id),
        notes=(
            "Fallback task from articles.json draft registry. "
            f"File: {str(a0.get('file') or '').strip()}"
        ),
    )


def _get_next_content_task(
    *,
    workspace_root: str,
    website_path: str,
    brief_path: str | None,
    priority: str,
) -> tuple[Path, ContentTask]:
    brief_file = _resolve_brief_path(workspace_root=workspace_root, website_path=website_path, brief_path=brief_path)
    brief_text = _load_text(brief_file)
    tasks = _parse_content_tasks_from_brief(brief_text)

    def pri_norm(p: str) -> str:
        return (p or "").strip().upper()

    open_tasks = [t for t in tasks if _is_task_open(t.status)]
    desired = pri_norm(priority)

    # Prefer tasks matching the requested priority.
    for task in open_tasks:
        if desired and pri_norm(task.priority) == desired:
            return brief_file, task

    # If the brief contains tasks but none match the requested priority, take the first open task.
    if open_tasks:
        return brief_file, open_tasks[0]

    # Fallback: if the brief has no structured tasks, select a draft article from articles.json.
    fallback_task = _get_next_registry_draft_task(
        workspace_root=workspace_root,
        website_path=website_path,
        requested_priority=priority,
    )
    return brief_file, fallback_task


def _latest_published_date(data: dict[str, Any]) -> date | None:
    """Find the latest date among published AND ready_to_publish articles.

    Including ready_to_publish prevents batch-created articles from all
    receiving the same date (each successive plan sees the previous one).
    """
    latest: date | None = None
    today = datetime.utcnow().date()
    # Allow dates up to 30 days in the future (scheduled articles)
    max_future = today + timedelta(days=30)
    for a in data.get("articles", []):
        if not isinstance(a, dict):
            continue
        status = str(a.get("status") or "").strip().lower()
        if status not in ("published", "ready_to_publish"):
            continue
        ds = str(a.get("published_date") or "").strip()
        if not ds:
            continue
        try:
            d = datetime.strptime(ds, "%Y-%m-%d").date()
        except Exception:
            continue
        # Skip unreasonably far-future dates.
        if d > max_future:
            continue
        if latest is None or d > latest:
            latest = d
    return latest


def _all_article_dates(data: dict[str, Any]) -> set[str]:
    """Collect all published_date strings from articles.json."""
    dates: set[str] = set()
    for a in data.get("articles", []):
        if not isinstance(a, dict):
            continue
        ds = str(a.get("published_date") or "").strip()
        if ds:
            dates.add(ds)
    return dates


def _suggest_publish_date(*, latest: date | None, occupied: set[str] | None = None) -> str:
    """Suggest a publish date spaced 2 days after *latest*, skipping occupied dates.

    Allows dates up to 14 days in the future so that batch-created
    articles automatically receive staggered dates even when creating
    many articles in one session.
    """
    today = datetime.utcnow().date()
    occupied = occupied or set()
    if latest is None:
        d = today - timedelta(days=1)
    else:
        d = latest + timedelta(days=2)
    max_future = today + timedelta(days=14)
    # Walk forward until we find an unoccupied date (within limit).
    attempts = 0
    while d.strftime("%Y-%m-%d") in occupied and attempts < 60:
        d += timedelta(days=1)
        attempts += 1
    if d > max_future:
        # Fall back: walk backward from today to find a free slot.
        d = today
        attempts = 0
        while d.strftime("%Y-%m-%d") in occupied and attempts < 60:
            d -= timedelta(days=1)
            attempts += 1
    return d.strftime("%Y-%m-%d")


def _plan_content_article(
    *,
    workspace_root: str,
    website_path: str,
    brief_path: str | None,
    task_id: str | None,
    priority: str,
    extension: str,
) -> PlannedContentArticle:
    brief_file, task = _get_next_content_task(
        workspace_root=workspace_root,
        website_path=website_path,
        brief_path=brief_path,
        priority=priority,
    )
    if task_id and task.task_id != task_id:
        # If a specific task_id is requested, find it.
        tasks = _parse_content_tasks_from_brief(_load_text(brief_file))
        found = next((t for t in tasks if t.task_id == task_id), None)
        if not found:
            raise ValueError(f"Task ID '{task_id}' not found in brief")
        task = found

    articles_data = _load_articles_json(workspace_root, website_path)
    latest = _latest_published_date(articles_data)
    occupied = _all_article_dates(articles_data)
    published_date = _suggest_publish_date(latest=latest, occupied=occupied)

    # If the task is sourced from the registry draft list, keep its ID/file.
    forced_article_id: int | None = None
    if task.task_id.startswith("REGISTRY_DRAFT:"):
        forced_article_id = _safe_int(task.task_id.split(":", 1)[1])
    if forced_article_id is None:
        forced_article_id = _safe_int(task.created_article_id)

    existing_entry: dict[str, Any] | None = None
    if forced_article_id:
        for a in articles_data.get("articles", []):
            if not isinstance(a, dict):
                continue
            if int(a.get("id") or 0) == forced_article_id:
                existing_entry = a
                break

    if forced_article_id:
        article_id = forced_article_id
    else:
        summary = _articles_summary(workspace_root=workspace_root, website_path=website_path)
        article_id = summary.next_id

    title = (task.article_title or "").strip()
    if not title and existing_entry is not None:
        title = str(existing_entry.get("title") or "").strip()
    title = title or f"{task.task_id}"

    url_slug = None
    if existing_entry is not None:
        url_slug = (str(existing_entry.get("url_slug") or "").strip() or None)
    url_slug = url_slug or _slugify(title)

    # Preserve existing file path if present; otherwise generate based on requested extension.
    file_ref = None
    if existing_entry is not None:
        file_ref = (str(existing_entry.get("file") or "").strip() or None)
    if not file_ref:
        ext = (extension or "mdx").lstrip(".")
        file_ref = f"./content/{article_id:02d}_{url_slug.replace('-', '_')}.{ext}"

    keyword = (task.target_keyword or "").strip()
    if not keyword and task.target_keywords:
        keyword = task.target_keywords[0]
    if not keyword and existing_entry is not None:
        keyword = str(existing_entry.get("target_keyword") or "").strip()

    difficulty = ""
    if task.est_kd:
        # est_kd is like '**Est. KD:** 3' or '3'
        difficulty = re.sub(r"[^0-9.]", "", task.est_kd) or task.est_kd
    if not difficulty and existing_entry is not None:
        difficulty = str(existing_entry.get("keyword_difficulty") or "").strip()

    frontmatter = (
        "---\n"
        f"title: \"{title}\"\n"
        f"date: \"{published_date}\"\n"
        "summary: \"\"\n"
        f"keyword: \"{keyword}\"\n"
        f"difficulty: {difficulty if difficulty else ''}\n"
        "---\n"
    )

    return PlannedContentArticle(
        website_path=website_path,
        brief_path=str(brief_file),
        task=task,
        article_id=article_id,
        url_slug=url_slug,
        file=file_ref,
        published_date=published_date,
        frontmatter=frontmatter,
    )


def _upsert_article_entry(
    *,
    workspace_root: str,
    website_path: str,
    entry: dict[str, Any],
) -> None:
    data = _load_articles_json(workspace_root, website_path)
    articles = [a for a in data.get("articles", []) if isinstance(a, dict)]

    article_id = int(entry.get("id") or 0)
    if article_id <= 0:
        raise ValueError("Article id must be a positive integer")

    replaced = False
    for idx, a in enumerate(articles):
        if int(a.get("id") or 0) == article_id:
            articles[idx] = {**a, **entry}
            replaced = True
            break
    if not replaced:
        articles.append(entry)

    # Keep stable ordering by id.
    articles.sort(key=lambda x: int(x.get("id") or 0))
    data["articles"] = articles
    _save_articles_json(workspace_root, website_path, data)


def _complete_task_in_brief(
    *,
    brief_path: Path,
    task_id: str,
    article_id: int,
) -> bool:
    text = _load_text(brief_path)

    # Locate the task block by header.
    header = f"#### Task ID: {task_id}"
    pos = text.find(header)
    if pos < 0:
        return False

    # Work on the substring from the header to the next task header or end.
    next_pos = text.find("#### Task ID:", pos + len(header))
    block_end = next_pos if next_pos >= 0 else len(text)
    block = text[pos:block_end]

    # Update status line if present.
    block = re.sub(
        r"^\s*-\s*\*\*Status\*\*:\s*.*?$",
        "- **Status:** ✅ Completed",
        block,
        flags=re.MULTILINE,
    )

    # Update created article id line (singular/plural) or insert after Links To.
    if re.search(r"^\s*-\s*\*\*Created Article ID", block, flags=re.MULTILINE):
        block = re.sub(
            r"^\s*-\s*\*\*Created Article ID\*\*:\s*.*?$",
            f"- **Created Article ID:** {article_id}",
            block,
            flags=re.MULTILINE,
        )
    elif re.search(r"^\s*-\s*\*\*Created Article IDs\*\*:", block, flags=re.MULTILINE):
        block = re.sub(
            r"^\s*-\s*\*\*Created Article IDs\*\*:\s*.*?$",
            f"- **Created Article ID:** {article_id}",
            block,
            flags=re.MULTILINE,
        )
    else:
        # Insert after Links To if present, else after Target Keyword.
        if re.search(r"^\s*-\s*\*\*Links To\*\*:", block, flags=re.MULTILINE):
            block = re.sub(
                r"(^\s*-\s*\*\*Links To\*\*:\s*.*?$)",
                r"\1\n" + f"- **Created Article ID:** {article_id}",
                block,
                flags=re.MULTILINE,
            )
        elif re.search(r"^\s*-\s*\*\*Target Keyword\*\*:", block, flags=re.MULTILINE):
            block = re.sub(
                r"(^\s*-\s*\*\*Target Keyword\*\*:\s*.*?$)",
                r"\1\n" + f"- **Created Article ID:** {article_id}",
                block,
                flags=re.MULTILINE,
            )
        else:
            block = block + f"\n- **Created Article ID:** {article_id}\n"

    updated = text[:pos] + block + text[block_end:]
    _save_text(brief_path, updated)
    return True


def _get_articles_index(
    *,
    workspace_root: str,
    website_path: str,
    status: str | None,
) -> ArticlesIndexResult:
    data = _load_articles_json(workspace_root, website_path)
    items: list[ArticleIndexItem] = []
    desired_status = (status or "").strip().lower()
    for a in data.get("articles", []):
        if not isinstance(a, dict):
            continue
        st = str(a.get("status") or "").strip().lower()
        if desired_status and st != desired_status:
            continue
        items.append(
            ArticleIndexItem(
                id=int(a.get("id") or 0),
                title=str(a.get("title") or ""),
                target_keyword=str(a.get("target_keyword") or ""),
                status=str(a.get("status") or ""),
                file=str(a.get("file") or ""),
                url_slug=(str(a.get("url_slug") or "") or None),
                published_date=(str(a.get("published_date") or "") or None),
            )
        )

    items.sort(key=lambda x: x.id)
    return ArticlesIndexResult(website_path=website_path, total=len(items), items=items)


def _articles_summary(*, workspace_root: str, website_path: str) -> ArticlesSummary:
    data = _load_articles_json(workspace_root, website_path)
    articles = [a for a in data.get("articles", []) if isinstance(a, dict)]
    total = len(articles)
    ids = [int(a.get("id")) for a in articles if a.get("id") is not None]
    max_id = max(ids) if ids else 0
    next_id = max_id + 1

    normalized_map, _ = _extract_existing_keywords(data)
    existing_unique = len(normalized_map)
    with_kw = sum(1 for a in articles if (a.get("target_keyword") or "").strip())

    status_counts: dict[str, int] = {}
    for a in articles:
        status = str(a.get("status") or "").strip().lower() or "unknown"
        status_counts[status] = status_counts.get(status, 0) + 1

    return ArticlesSummary(
        website_path=website_path,
        total_articles=total,
        max_id=max_id,
        next_id=next_id,
        articles_with_target_keywords=with_kw,
        existing_unique_keywords=existing_unique,
        status_counts=dict(sorted(status_counts.items())),
    )


def _get_next_article_id(*, workspace_root: str, website_path: str) -> dict[str, Any]:
    summary = _articles_summary(workspace_root=workspace_root, website_path=website_path)
    return {
        "website_path": website_path,
        "max_id": summary.max_id,
        "next_id": summary.next_id,
    }


def _append_draft_articles(
    *,
    workspace_root: str,
    website_path: str,
    drafts: list[DraftArticleInput],
    enable_dedupe: bool,
    fuzzy_threshold: float,
) -> AppendDraftResult:
    data = _load_articles_json(workspace_root, website_path)
    articles = [a for a in data.get("articles", []) if isinstance(a, dict)]

    # Determine next id.
    ids = [int(a.get("id")) for a in articles if a.get("id") is not None]
    next_id = (max(ids) + 1) if ids else 1

    added_ids: list[int] = []
    added: list[dict[str, Any]] = []

    if enable_dedupe:
        # Dedupe on target_keyword before writing.
        filter_res = _filter_new_keywords(
            workspace_root=workspace_root,
            website_path=website_path,
            keywords=[d.target_keyword for d in drafts if (d.target_keyword or "").strip()],
            enable_fuzzy=True,
            fuzzy_threshold=fuzzy_threshold,
        )
        allowed = set(_normalize_keyword(k) for k in filter_res.new_keywords)
    else:
        allowed = None

    for draft in drafts:
        title = (draft.title or "").strip()
        target_keyword = (draft.target_keyword or "").strip()
        if not title or not target_keyword:
            continue

        if allowed is not None and _normalize_keyword(target_keyword) not in allowed:
            # Skip duplicates when dedupe is enabled.
            continue

        url_slug = (draft.url_slug or "").strip() or _slugify(title)
        file_ref = (draft.file or "").strip()
        if not file_ref:
            file_ref = f"./content/{next_id:02d}_{url_slug.replace('-', '_')}.md"

        entry: dict[str, Any] = {
            "id": next_id,
            "title": title,
            "url_slug": url_slug,
            "file": file_ref,
            "target_keyword": target_keyword,
            "keyword_difficulty": "" if draft.keyword_difficulty is None else str(draft.keyword_difficulty),
            "target_volume": int(draft.target_volume or 0),
            "published_date": "",
            "word_count": 0,
            "status": "draft",
            "content_gaps_addressed": draft.content_gaps_addressed or [],
            "estimated_traffic_monthly": "" if draft.estimated_traffic_monthly is None else str(draft.estimated_traffic_monthly),
        }

        articles.append(entry)
        added_ids.append(next_id)
        added.append(entry)
        next_id += 1

    data["articles"] = articles
    _save_articles_json(workspace_root, website_path, data)

    return AppendDraftResult(website_path=website_path, added_ids=added_ids, added=added)


def _get_articles_by_keyword(
    *,
    workspace_root: str,
    website_path: str,
    keyword: str,
    enable_fuzzy: bool,
    fuzzy_threshold: float,
) -> ArticlesByKeywordResult:
    data = _load_articles_json(workspace_root, website_path)
    articles = [a for a in data.get("articles", []) if isinstance(a, dict)]

    query = (keyword or "").strip()
    normalized_query = _normalize_keyword(query)
    canonical_query = _canonicalize_keyword(query)

    matches: list[ArticleKeywordMatch] = []
    for a in articles:
        target = (a.get("target_keyword") or "").strip()
        if not target:
            continue

        normalized_target = _normalize_keyword(target)
        canonical_target = _canonicalize_keyword(target)

        match_type: str | None = None
        score: float | None = None

        if normalized_target == normalized_query and normalized_query:
            match_type = "exact"
        elif canonical_target == canonical_query and canonical_query:
            match_type = "canonical"
        elif enable_fuzzy and canonical_query and canonical_target:
            score = difflib.SequenceMatcher(a=canonical_query, b=canonical_target).ratio()
            if score >= fuzzy_threshold:
                match_type = "fuzzy"

        if match_type:
            matches.append(
                ArticleKeywordMatch(
                    article_id=int(a.get("id") or 0),
                    title=str(a.get("title") or ""),
                    status=str(a.get("status") or ""),
                    target_keyword=target,
                    match_type=match_type,
                    score=score,
                )
            )

    # Stable ordering: best match first, then id.
    match_rank = {"exact": 0, "canonical": 1, "fuzzy": 2}
    matches.sort(key=lambda m: (match_rank.get(m.match_type, 9), -(m.score or 0), m.article_id))

    return ArticlesByKeywordResult(
        website_path=website_path,
        query_keyword=query,
        normalized_query=normalized_query,
        canonical_query=canonical_query,
        matches=matches,
    )


def _extract_existing_keywords(articles_data: dict[str, Any]) -> tuple[dict[str, list[int]], dict[str, list[int]]]:
    """Return (normalized_map, canonical_map) of keyword -> article_ids."""
    normalized_map: dict[str, list[int]] = {}
    canonical_map: dict[str, list[int]] = {}

    for article in articles_data.get("articles", []):
        raw = (article.get("target_keyword") or "").strip()
        if not raw:
            continue
        article_id = int(article.get("id"))

        norm = _normalize_keyword(raw)
        can = _canonicalize_keyword(raw)

        normalized_map.setdefault(norm, []).append(article_id)
        canonical_map.setdefault(can, []).append(article_id)

    return normalized_map, canonical_map


def _filter_new_keywords(
    *,
    workspace_root: str,
    website_path: str,
    keywords: list[str],
    enable_fuzzy: bool,
    fuzzy_threshold: float,
) -> KeywordFilterResult:
    articles_data = _load_articles_json(workspace_root, website_path)
    normalized_map, canonical_map = _extract_existing_keywords(articles_data)

    existing_unique = len(normalized_map)
    total_articles = len(articles_data.get("articles", []))

    matches: list[KeywordMatch] = []
    new_keywords: list[str] = []

    canonical_keys = list(canonical_map.keys())

    for kw in keywords:
        original = (kw or "").strip()
        if not original:
            continue

        norm = _normalize_keyword(original)
        can = _canonicalize_keyword(original)

        if norm in normalized_map:
            matches.append(
                KeywordMatch(
                    input_keyword=original,
                    matched_existing_keyword=norm,
                    match_type="exact",
                    matched_article_ids=sorted(normalized_map[norm]),
                )
            )
            continue

        if can in canonical_map:
            matches.append(
                KeywordMatch(
                    input_keyword=original,
                    matched_existing_keyword=can,
                    match_type="canonical",
                    matched_article_ids=sorted(canonical_map[can]),
                )
            )
            continue

        if enable_fuzzy and can and canonical_keys:
            # Find best fuzzy match among existing canonical forms.
            best_score = 0.0
            best_match = ""
            for existing_can in canonical_keys:
                score = difflib.SequenceMatcher(a=can, b=existing_can).ratio()
                if score > best_score:
                    best_score = score
                    best_match = existing_can
            if best_score >= fuzzy_threshold and best_match:
                matches.append(
                    KeywordMatch(
                        input_keyword=original,
                        matched_existing_keyword=best_match,
                        match_type="fuzzy",
                        matched_article_ids=sorted(canonical_map.get(best_match, [])),
                    )
                )
                continue

        new_keywords.append(original)

    return KeywordFilterResult(
        website_path=website_path,
        total_articles=total_articles,
        existing_unique_keywords=existing_unique,
        input_keywords=len([k for k in keywords if (k or "").strip()]),
        new_keywords=new_keywords,
        matches=matches,
    )


def format_distribution_result(result: DistributionResult) -> str:
    """Format distribution result as readable text"""
    lines = [
        f"📊 {result.project_name} Distribution Test ({result.article_count} articles)",
        "=" * 60,
        "",
        f"  Earliest date: {result.earliest_date}",
        f"  Today: {result.today_date}",
        f"  Total days available: {result.days_available} days",
        f"  Days per article: {result.days_per_article} days",
        f"  Date range: {result.earliest_date} → {result.today_date}",
        "",
        "  Distribution:",
        ""
    ]
    
    for item in result.distribution:
        if item["article_number"] is None:
            # Ellipsis
            lines.append(f"    {item['date']}")
            if item['marker']:
                lines.append(f"    {item['marker']}")
        else:
            marker = f" {item['marker']}" if item['marker'] else ""
            lines.append(f"    Article {item['article_number']}: {item['date']}{marker}")
    
    lines.extend([
        "",
        "✅ Articles are spread evenly across the full date range!",
        "   Instead of clustering, they're distributed proportionally.",
    ])
    
    return "\n".join(lines)


def detect_workspace_root() -> str:
    """
    Detect the workspace root directory by checking common locations.
    
    Priority:
    1. WORKSPACE_ROOT environment variable
    2. Look for 'general/days_to_expiry' or 'general/coffee' directory up the tree
    3. Current working directory
    4. Parent directory of the MCP script
    """
    # First, check environment variable
    if "WORKSPACE_ROOT" in os.environ:
        root = os.environ["WORKSPACE_ROOT"]
        if os.path.isdir(root):
            return root
    
    # Try to find the automation workspace by looking for telltale directories
    current = Path.cwd()
    for _ in range(5):  # Look up to 5 levels up
        if (current / "general" / "days_to_expiry").exists() or \
           (current / "general" / "coffee").exists() or \
           (current / "general" / "expense").exists():
            return str(current)
        current = current.parent
    
    # Try the MCP server directory's parent path
    mcp_dir = Path(__file__).parent.parent.parent.parent  # src/seo_content_mcp -> seo-content-mcp
    workspace_check = mcp_dir.parent  # Go to /mcp level
    if (workspace_check / "general" / "days_to_expiry").exists():
        return str(workspace_check)
    
    # Default to current working directory
    return os.getcwd()


async def serve() -> None:
    """Run the SEO Content MCP server"""
    server = Server("seo-content-mcp")
    
    # Get workspace root using intelligent detection
    workspace_root = detect_workspace_root()
    seo_server = SEOContentServer(workspace_root)
    seo_ops = SEOOps(workspace_root)

    
    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """List available SEO content tools"""
        return [
            Tool(
                name=SEOTools.TEST_DISTRIBUTION,
                description=(
                    "Test date distribution for articles without making changes. "
                    "Shows how articles would be spread across dates from earliest_date to today. "
                    "Useful for previewing distribution before applying changes."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_name": {
                            "type": "string",
                            "description": "Name of the project (e.g., 'Coffee', 'Expense', 'Days to Expiry')"
                        },
                        "article_count": {
                            "type": "integer",
                            "description": "Number of articles to distribute",
                            "minimum": 1
                        },
                        "earliest_date": {
                            "type": "string",
                            "description": "Earliest date in YYYY-MM-DD format",
                            "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
                        }
                    },
                    "required": ["project_name", "article_count", "earliest_date"]
                }
            ),
            Tool(
                name=SEOTools.CLEAN_CONTENT,
                description=(
                    "Clean content files (MDX/Markdown) by removing duplicate title headings and syncing dates "
                    "between articles.json and frontmatter. Makes actual changes to files."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "website_path": {
                            "type": "string",
                            "description": "Relative path to website folder (e.g., 'general/coffee', 'general/expense')"
                        }
                    },
                    "required": ["website_path"]
                }
            ),
            Tool(
                name=SEOTools.VALIDATE_CONTENT,
                description=(
                    "Validate content files without making changes. Reports issues like "
                    "duplicate title headings, date mismatches, and missing frontmatter. "
                    "Use this before seo_clean_content to preview what would be fixed."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "website_path": {
                            "type": "string",
                            "description": "Relative path to website folder (e.g., 'general/coffee', 'general/expense')"
                        }
                    },
                    "required": ["website_path"]
                }
            ),
            Tool(
                name=SEOTools.ANALYZE_DATES,
                description=(
                    "Analyze article dates to find issues without making changes. "
                    "Detects future dates, overlapping dates (multiple articles on same day), "
                    "and poor distribution in recently created articles (last 7 days). "
                    "Use this before seo_fix_dates to see what would be changed."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "website_path": {
                            "type": "string",
                            "description": "Relative path to website folder (e.g., 'general/coffee', 'general/expense')"
                        }
                    },
                    "required": ["website_path"]
                }
            ),
            Tool(
                name=SEOTools.FIX_DATES,
                description=(
                    "Fix article date issues by redistributing recent articles (last 7 days). "
                    "Removes future dates, eliminates overlapping dates, and ensures even distribution. "
                    "Only affects recently created articles; leaves historical articles untouched. "
                    "Makes actual changes to articles.json file."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "website_path": {
                            "type": "string",
                            "description": "Relative path to website folder (e.g., 'general/coffee', 'general/expense')"
                        }
                    },
                    "required": ["website_path"]
                }
            )
            ,
            Tool(
                name=SEOTools.FILTER_NEW_KEYWORDS,
                description=(
                    "Filter candidate keywords against existing articles.json target_keyword values. "
                    "Returns only NEW keywords plus a match report (exact/canonical/fuzzy). "
                    "Use this to avoid writing local Python scripts for dedupe."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "website_path": {
                            "type": "string",
                            "description": "Relative path to website folder (e.g., 'general/coffee', 'general/expense')",
                        },
                        "keywords": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Candidate keywords to filter",
                        },
                        "enable_fuzzy": {
                            "type": "boolean",
                            "description": "Whether to use fuzzy matching for close variants",
                            "default": True,
                        },
                        "fuzzy_threshold": {
                            "type": "number",
                            "description": "Fuzzy match threshold (0-1). Higher = stricter.",
                            "default": 0.92,
                            "minimum": 0,
                            "maximum": 1,
                        },
                    },
                    "required": ["website_path", "keywords"],
                },
            ),
            Tool(
                name=SEOTools.GET_ARTICLES_SUMMARY,
                description=(
                    "Get a compact summary of articles.json for a website (counts, max id, next id, unique keywords, statuses). "
                    "Use this instead of jq/Python to inspect current state."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "website_path": {
                            "type": "string",
                            "description": "Relative path to website folder (e.g., 'general/coffee', 'general/expense')",
                        }
                    },
                    "required": ["website_path"],
                },
            ),
            Tool(
                name=SEOTools.GET_NEXT_ARTICLE_ID,
                description=(
                    "Get the next available article id (max id + 1) from articles.json."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "website_path": {
                            "type": "string",
                            "description": "Relative path to website folder (e.g., 'general/coffee', 'general/expense')",
                        }
                    },
                    "required": ["website_path"],
                },
            ),
            Tool(
                name=SEOTools.APPEND_DRAFT_ARTICLES,
                description=(
                    "Append one or more draft articles to articles.json with auto IDs and generated slugs/files. "
                    "Optionally dedupes by target_keyword before writing."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "website_path": {
                            "type": "string",
                            "description": "Relative path to website folder (e.g., 'general/coffee', 'general/expense')",
                        },
                        "drafts": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "title": {"type": "string"},
                                    "target_keyword": {"type": "string"},
                                    "keyword_difficulty": {"type": ["string", "number", "integer", "null"]},
                                    "target_volume": {"type": ["integer", "null"], "default": 0},
                                    "estimated_traffic_monthly": {"type": ["string", "integer", "null"]},
                                    "content_gaps_addressed": {"type": "array", "items": {"type": "string"}},
                                    "url_slug": {"type": ["string", "null"]},
                                    "file": {"type": ["string", "null"]}
                                },
                                "required": ["title", "target_keyword"]
                            },
                            "description": "Draft article inputs",
                        },
                        "enable_dedupe": {
                            "type": "boolean",
                            "description": "Skip drafts whose target_keyword already exists",
                            "default": True
                        },
                        "fuzzy_threshold": {
                            "type": "number",
                            "description": "Fuzzy threshold used when dedupe is enabled",
                            "default": 0.92,
                            "minimum": 0,
                            "maximum": 1
                        }
                    },
                    "required": ["website_path", "drafts"],
                },
            ),
            Tool(
                name=SEOTools.GET_ARTICLES_BY_KEYWORD,
                description=(
                    "Find existing articles whose target_keyword matches a given keyword (exact/canonical/fuzzy). "
                    "Use this to detect keyword cannibalization without inspecting articles.json."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "website_path": {
                            "type": "string",
                            "description": "Relative path to website folder (e.g., 'general/coffee', 'general/expense')",
                        },
                        "keyword": {
                            "type": "string",
                            "description": "Keyword to search for in articles.json target_keyword",
                        },
                        "enable_fuzzy": {
                            "type": "boolean",
                            "description": "Whether to use fuzzy matching for close variants",
                            "default": True,
                        },
                        "fuzzy_threshold": {
                            "type": "number",
                            "description": "Fuzzy match threshold (0-1). Higher = stricter.",
                            "default": 0.92,
                            "minimum": 0,
                            "maximum": 1,
                        },
                    },
                    "required": ["website_path", "keyword"],
                },
            ),
            Tool(
                name=SEOTools.GET_NEXT_CONTENT_TASK,
                description=(
                    "Get the next open content task from the project's *_seo_content_brief.md, filtered by priority (default HIGH PRIORITY). "
                    "If the brief has no structured Task ID blocks, falls back to returning the next draft article from articles.json as a task."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "website_path": {
                            "type": "string",
                            "description": "Relative path to website folder (e.g., 'general/coffee')",
                        },
                        "brief_path": {
                            "type": ["string", "null"],
                            "description": "Optional path to content brief (relative to workspace or absolute). If omitted, auto-detects '*_seo_content_brief.md' under website_path.",
                            "default": None,
                        },
                        "priority": {
                            "type": "string",
                            "description": "Priority heading to select from (e.g., 'HIGH PRIORITY', 'MEDIUM PRIORITY').",
                            "default": "HIGH PRIORITY",
                        },
                    },
                    "required": ["website_path"],
                },
            ),
            Tool(
                name=SEOTools.PLAN_CONTENT_ARTICLE,
                description=(
                    "Plan the next content article from a content brief task: computes id, url_slug, file path, and a safe published_date (3 days after latest published, never future). "
                    "If the task is a registry draft (REGISTRY_DRAFT:<id>), preserves the existing id/file from articles.json."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "website_path": {
                            "type": "string",
                            "description": "Relative path to website folder (e.g., 'general/coffee')",
                        },
                        "brief_path": {
                            "type": ["string", "null"],
                            "description": "Optional path to content brief (relative to workspace or absolute).",
                            "default": None,
                        },
                        "task_id": {
                            "type": ["string", "null"],
                            "description": "Optional specific Task ID to plan. If omitted, uses the next open task by priority.",
                            "default": None,
                        },
                        "priority": {
                            "type": "string",
                            "description": "Priority heading to select from when task_id is omitted.",
                            "default": "HIGH PRIORITY",
                        },
                        "extension": {
                            "type": "string",
                            "description": "File extension to use for the content file (default mdx).",
                            "default": "mdx",
                        },
                    },
                    "required": ["website_path"],
                },
            ),
            Tool(
                name=SEOTools.PUBLISH_ARTICLE_AND_COMPLETE_TASK,
                description=(
                    "Upsert an article into articles.json and mark the corresponding content brief task as completed (Status ✅, Created Article ID set). "
                    "Default status is 'ready_to_publish' (not 'published')."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "website_path": {
                            "type": "string",
                            "description": "Relative path to website folder (e.g., 'general/coffee')",
                        },
                        "brief_path": {
                            "type": ["string", "null"],
                            "description": "Optional path to content brief (relative to workspace or absolute).",
                            "default": None,
                        },
                        "task_id": {"type": "string", "description": "Task ID in the content brief (e.g., 'C1-STORAGE-001')"},
                        "article": {
                            "type": "object",
                            "description": "Published article entry fields (id, title, url_slug, file, target_keyword, keyword_difficulty, target_volume, published_date, word_count, status, content_gaps_addressed, estimated_traffic_monthly)",
                        },
                    },
                    "required": ["website_path", "task_id", "article"],
                },
            ),
            Tool(
                name=SEOTools.GET_ARTICLES_INDEX,
                description=(
                    "Get a lightweight index of articles from articles.json (id/title/keyword/status/file/url_slug/published_date). "
                    "Use this for clustering and linking without inspecting files via terminal scripts."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "website_path": {
                            "type": "string",
                            "description": "Relative path to website folder (e.g., 'general/coffee')",
                        },
                        "status": {
                            "type": ["string", "null"],
                            "description": "Optional status filter (e.g., 'published', 'draft')",
                            "default": None,
                        },
                    },
                    "required": ["website_path"],
                },
            ),

            # --- Clustering & Linking tools (Step 3) ---
            Tool(
                name=SEOTools.SCAN_INTERNAL_LINKS,
                description=(
                    "Scan all content files (MDX) and build the internal link graph. "
                    "Returns summary stats + per-article outgoing/incoming links and orphan articles. "
                    "Use this to understand the current linking state before adding new links."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "website_path": {
                            "type": "string",
                            "description": "Relative path to website folder (e.g., 'general/expense')",
                        },
                    },
                    "required": ["website_path"],
                },
            ),
            Tool(
                name=SEOTools.GENERATE_LINKING_PLAN,
                description=(
                    "Generate a hub-spoke internal linking plan from clusters defined in the content brief. "
                    "Compares planned links against existing links to show what's missing. "
                    "Read-only: does not modify any files."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "website_path": {
                            "type": "string",
                            "description": "Relative path to website folder (e.g., 'general/expense')",
                        },
                        "brief_path": {
                            "type": ["string", "null"],
                            "description": "Path to content brief (auto-detected if omitted)",
                            "default": None,
                        },
                        "clusters_json": {
                            "type": ["array", "null"],
                            "items": {"type": "object"},
                            "description": "Optional explicit cluster definitions: [{cluster_id, name, pillar_id, support_ids}]. If omitted, parsed from brief.",
                            "default": None,
                        },
                    },
                    "required": ["website_path"],
                },
            ),
            Tool(
                name=SEOTools.ADD_ARTICLE_LINKS,
                description=(
                    "Add internal links from one article to target articles. "
                    "Mode 'related-section' appends a Related Articles section. "
                    "Mode 'inline' tries to add natural anchor links in the body text. "
                    "Skips links that already exist. Writes to the MDX file."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "website_path": {
                            "type": "string",
                            "description": "Relative path to website folder",
                        },
                        "source_id": {
                            "type": "integer",
                            "description": "Article ID to add links into",
                        },
                        "target_ids": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "Target article IDs to link to",
                        },
                        "mode": {
                            "type": "string",
                            "enum": ["related-section", "inline"],
                            "default": "related-section",
                            "description": "How to add links",
                        },
                        "dry_run": {
                            "type": "boolean",
                            "default": False,
                            "description": "Preview without writing",
                        },
                    },
                    "required": ["website_path", "source_id", "target_ids"],
                },
            ),
            Tool(
                name=SEOTools.GET_ARTICLE_CONTENT,
                description=(
                    "Get article metadata + MDX content body by article ID. "
                    "Saves the agent from manually looking up file paths and reading files. "
                    "Returns id, title, file, keyword, status, word_count, and full content."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "website_path": {
                            "type": "string",
                            "description": "Relative path to website folder",
                        },
                        "article_id": {
                            "type": "integer",
                            "description": "Article ID to retrieve",
                        },
                    },
                    "required": ["website_path", "article_id"],
                },
            ),
            Tool(
                name=SEOTools.UPDATE_BRIEF_LINKING_STATUS,
                description=(
                    "Scan actual internal links in MDX files and update the linking checklist "
                    "in the content brief (☐ → ✅ for links that actually exist). "
                    "Writes to the brief file."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "website_path": {
                            "type": "string",
                            "description": "Relative path to website folder",
                        },
                        "brief_path": {
                            "type": ["string", "null"],
                            "description": "Path to content brief (auto-detected if omitted)",
                            "default": None,
                        },
                        "dry_run": {
                            "type": "boolean",
                            "default": False,
                            "description": "Preview without writing",
                        },
                    },
                    "required": ["website_path"],
                },
            ),
            Tool(
                name=SEOTools.BATCH_ADD_LINKS,
                description=(
                    "Add ALL missing internal links from the linking plan at once. "
                    "Generates the plan from clusters in the brief, then adds links to every "
                    "article that has missing outgoing links. Use with dry_run=true to preview first."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "website_path": {
                            "type": "string",
                            "description": "Relative path to website folder",
                        },
                        "brief_path": {
                            "type": ["string", "null"],
                            "description": "Path to content brief (auto-detected if omitted)",
                            "default": None,
                        },
                        "mode": {
                            "type": "string",
                            "enum": ["related-section", "inline"],
                            "default": "related-section",
                            "description": "How to add links",
                        },
                        "dry_run": {
                            "type": "boolean",
                            "default": False,
                            "description": "Preview without writing",
                        },
                    },
                    "required": ["website_path"],
                },
            ),

            # --- SEO Ops tools (registry-driven) ---
            Tool(
                name=SEOTools.OPS_OVERVIEW,
                description=(
                    "Get a multi-site SEO ops overview from WEBSITES_REGISTRY.json (counts, latest published, issue totals). "
                    "Read-only; mirrors the /seo dashboard overview."
                ),
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name=SEOTools.OPS_SITE_METRICS,
                description=(
                    "Get per-site SEO metrics for a website_id from WEBSITES_REGISTRY.json (same fields used by the UI)."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "website_id": {"type": "string", "description": "Website ID (e.g., 'coffee', 'days_to_expiry')"}
                    },
                    "required": ["website_id"],
                },
            ),
            Tool(
                name=SEOTools.OPS_DRIFT,
                description=(
                    "Compute drift between automation content/ and the real repo content dir (sha256 by basename). "
                    "Read-only; mirrors /api/seo/drift/<website_id>."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "website_id": {"type": "string"}
                    },
                    "required": ["website_id"],
                },
            ),
            Tool(
                name=SEOTools.OPS_IMPORT_PREVIEW,
                description=(
                    "Preview syncing automation articles.json from repo content frontmatter (read-only preview). "
                    "Does not modify repo files."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {"website_id": {"type": "string"}},
                    "required": ["website_id"],
                },
            ),
            Tool(
                name=SEOTools.OPS_IMPORT_APPLY,
                description=(
                    "Apply syncing automation articles.json from repo content frontmatter. "
                    "Writes automation articles.json only; repo stays read-only."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {"website_id": {"type": "string"}},
                    "required": ["website_id"],
                },
            ),
            Tool(
                name=SEOTools.OPS_DATES_ANALYZE,
                description=(
                    "Analyze automation-side dates for a website_id (future/missing/bad/overlaps). Read-only."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {"website_id": {"type": "string"}},
                    "required": ["website_id"],
                },
            ),
            Tool(
                name=SEOTools.OPS_SCHEDULE_PREVIEW,
                description=(
                    "Preview draft-safe date scheduling for automation-side articles (never touches repo files). "
                    "By default, only schedules status='ready_to_publish'."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "website_id": {"type": "string"},
                        "spacing_days": {"type": "integer", "default": 2, "minimum": 1},
                        "statuses": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Only schedule articles whose status is in this list (default: ['ready_to_publish']).",
                            "default": ["ready_to_publish"]
                        },
                        "compact": {
                            "type": "boolean",
                            "description": "If true, return only summary (count + date range) instead of full schedule list.",
                            "default": False
                        }
                    },
                    "required": ["website_id"],
                },
            ),
            Tool(
                name=SEOTools.OPS_SCHEDULE_APPLY,
                description=(
                    "Apply draft-safe date scheduling: updates automation articles.json + automation content frontmatter dates. "
                    "Never modifies repo files. By default, only schedules status='ready_to_publish'."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "website_id": {"type": "string"},
                        "spacing_days": {"type": "integer", "default": 2, "minimum": 1},
                        "statuses": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Only schedule articles whose status is in this list (default: ['ready_to_publish']).",
                            "default": ["ready_to_publish"]
                        },
                        "compact": {
                            "type": "boolean",
                            "description": "If true, return only summary (count + date range) instead of full schedule list.",
                            "default": False
                        }
                    },
                    "required": ["website_id"],
                },
            ),
            Tool(
                name=SEOTools.OPS_REPORT_OVERVIEW_MARKDOWN,
                description=(
                    "Generate a Markdown overview report across all sites (AI-friendly). Read-only."
                ),
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name=SEOTools.OPS_REPORT_SITE_MARKDOWN,
                description=(
                    "Generate a per-site Markdown report (AI-friendly) with optional drift and schedule preview. Read-only unless you call apply tools."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "website_id": {"type": "string"},
                        "include_drift": {"type": "boolean", "default": False},
                        "include_dates": {"type": "boolean", "default": True},
                        "include_schedule_preview": {"type": "boolean", "default": True},
                        "spacing_days": {"type": "integer", "default": 2, "minimum": 1},
                        "max_items": {"type": "integer", "default": 25, "minimum": 1, "maximum": 200}
                    },
                    "required": ["website_id"],
                },
            ),
            Tool(
                name=SEOTools.OPS_VALIDATE_INDEX,
                description=(
                    "Validate articles.json entries against both automation content files and the real repo content dir. "
                    "Index-aware: can detect entries missing in BOTH places, and surfaces effective dates. Read-only."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "website_id": {"type": "string"},
                        "ids": {"type": "array", "items": {"type": "integer"}},
                        "max_repo_candidates": {"type": "integer", "default": 5, "minimum": 0, "maximum": 25}
                    },
                    "required": ["website_id"],
                },
            ),
            Tool(
                name=SEOTools.OPS_SYNC_AND_OPTIMIZE,
                description=(
                    "🚀 UNIFIED WORKFLOW: Sync from production, analyze dates, fix issues, check drift, validate, deploy. "
                    "Treats production repo as source of truth. Orchestrates: "
                    "1) Import from production 2) Analyze dates 3) Fix dates (if auto_fix) 4) Check drift 5) Validate 6) Deploy (if auto_deploy). "
                    "Returns structured results for agent parsing. Default mode is preview (read-only)."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "website_id": {
                            "type": "string",
                            "description": "Website ID from WEBSITES_REGISTRY.json (e.g., 'days_to_expiry')"
                        },
                        "auto_fix": {
                            "type": "boolean",
                            "description": "If true (and dry_run false), apply date fixes. Default: false (preview only)",
                            "default": False
                        },
                        "spacing_days": {
                            "type": "integer",
                            "description": "Days to space between redistributed articles. Default: 2",
                            "default": 2,
                            "minimum": 1
                        },
                        "max_recent_days": {
                            "type": "integer",
                            "description": "Only fix articles created in last N days. Historical articles untouched. Default: 14",
                            "default": 14,
                            "minimum": 1
                        },
                        "dry_run": {
                            "type": "boolean",
                            "description": "Safety check - if true, no changes made even if auto_fix is true. Default: true",
                            "default": True
                        },
                        "auto_deploy": {
                            "type": "boolean",
                            "description": "If true (and dry_run false), automatically copy files to production repo. Default: false",
                            "default": False
                        },
                        "target_statuses": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Statuses that are eligible for scheduling + deploy (default: ['ready_to_publish']).",
                            "default": ["ready_to_publish"]
                        },
                        "compact": {
                            "type": "boolean",
                            "description": "If true, return only summary (no phase details). Recommended for agent workflows.",
                            "default": False
                        }
                    },
                    "required": ["website_id"],
                },
            ),
        ]
    
    @server.call_tool()
    async def call_tool(name: str, arguments: Any) -> list[TextContent]:
        """Handle tool calls"""
        try:
            if name == SEOTools.TEST_DISTRIBUTION:
                result = seo_server.test_distribution(
                    project_name=arguments["project_name"],
                    article_count=arguments["article_count"],
                    earliest_date=arguments["earliest_date"]
                )
                
                formatted_output = format_distribution_result(result)
                
                return [
                    TextContent(
                        type="text",
                        text=formatted_output
                    )
                ]
            
            elif name == SEOTools.CLEAN_CONTENT:
                result = seo_server.cleaner.clean_website(
                    website_path=arguments["website_path"],
                    dry_run=False
                )
                
                formatted_output = format_cleaning_result(result)
                
                return [
                    TextContent(
                        type="text",
                        text=formatted_output
                    )
                ]
            
            elif name == SEOTools.VALIDATE_CONTENT:
                result = seo_server.cleaner.clean_website(
                    website_path=arguments["website_path"],
                    dry_run=True
                )
                
                formatted_output = format_cleaning_result(result)
                
                return [
                    TextContent(
                        type="text",
                        text=formatted_output
                    )
                ]
            
            elif name == SEOTools.ANALYZE_DATES:
                result = seo_server.distributor.analyze_dates(
                    website_path=arguments["website_path"]
                )
                
                formatted_output = format_date_analysis(result)
                
                return [
                    TextContent(
                        type="text",
                        text=formatted_output
                    )
                ]
            
            elif name == SEOTools.FIX_DATES:
                result = seo_server.distributor.fix_dates(
                    website_path=arguments["website_path"],
                    dry_run=False
                )
                
                formatted_output = format_date_fix(result, dry_run=False)
                
                return [
                    TextContent(
                        type="text",
                        text=formatted_output
                    )
                ]

            elif name == SEOTools.FILTER_NEW_KEYWORDS:
                result = _filter_new_keywords(
                    workspace_root=seo_server.workspace_root,
                    website_path=arguments["website_path"],
                    keywords=arguments.get("keywords", []),
                    enable_fuzzy=bool(arguments.get("enable_fuzzy", True)),
                    fuzzy_threshold=float(arguments.get("fuzzy_threshold", 0.92)),
                )

                return [TextContent(type="text", text=result.model_dump_json(indent=2))]

            elif name == SEOTools.GET_ARTICLES_SUMMARY:
                result = _articles_summary(
                    workspace_root=seo_server.workspace_root,
                    website_path=arguments["website_path"],
                )
                return [TextContent(type="text", text=result.model_dump_json(indent=2))]

            elif name == SEOTools.GET_NEXT_ARTICLE_ID:
                result = _get_next_article_id(
                    workspace_root=seo_server.workspace_root,
                    website_path=arguments["website_path"],
                )
                return [TextContent(type="text", text=json.dumps(result, indent=2))]

            elif name == SEOTools.APPEND_DRAFT_ARTICLES:
                drafts_raw = arguments.get("drafts", [])
                drafts = [DraftArticleInput.model_validate(d) for d in drafts_raw]
                result = _append_draft_articles(
                    workspace_root=seo_server.workspace_root,
                    website_path=arguments["website_path"],
                    drafts=drafts,
                    enable_dedupe=bool(arguments.get("enable_dedupe", True)),
                    fuzzy_threshold=float(arguments.get("fuzzy_threshold", 0.92)),
                )
                return [TextContent(type="text", text=result.model_dump_json(indent=2))]

            elif name == SEOTools.GET_ARTICLES_BY_KEYWORD:
                result = _get_articles_by_keyword(
                    workspace_root=seo_server.workspace_root,
                    website_path=arguments["website_path"],
                    keyword=arguments.get("keyword", ""),
                    enable_fuzzy=bool(arguments.get("enable_fuzzy", True)),
                    fuzzy_threshold=float(arguments.get("fuzzy_threshold", 0.92)),
                )
                return [TextContent(type="text", text=result.model_dump_json(indent=2))]

            elif name == SEOTools.GET_NEXT_CONTENT_TASK:
                brief_file, task = _get_next_content_task(
                    workspace_root=seo_server.workspace_root,
                    website_path=arguments["website_path"],
                    brief_path=arguments.get("brief_path"),
                    priority=arguments.get("priority", "HIGH PRIORITY"),
                )
                payload = {
                    "website_path": arguments["website_path"],
                    "brief_path": str(brief_file),
                    "task": task.model_dump(),
                }
                return [TextContent(type="text", text=json.dumps(payload, indent=2))]

            elif name == SEOTools.PLAN_CONTENT_ARTICLE:
                result = _plan_content_article(
                    workspace_root=seo_server.workspace_root,
                    website_path=arguments["website_path"],
                    brief_path=arguments.get("brief_path"),
                    task_id=arguments.get("task_id"),
                    priority=arguments.get("priority", "HIGH PRIORITY"),
                    extension=arguments.get("extension", "mdx"),
                )
                return [TextContent(type="text", text=result.model_dump_json(indent=2))]

            elif name == SEOTools.PUBLISH_ARTICLE_AND_COMPLETE_TASK:
                website_path = arguments["website_path"]
                brief_file = _resolve_brief_path(
                    workspace_root=seo_server.workspace_root,
                    website_path=website_path,
                    brief_path=arguments.get("brief_path"),
                )
                task_id = arguments["task_id"]
                article = dict(arguments.get("article") or {})
                article_id = int(article.get("id") or 0)
                if article_id <= 0:
                    raise ValueError("article.id must be provided and > 0")

                # Normalize required-ish fields with safe defaults.
                article.setdefault("status", "ready_to_publish")
                article.setdefault("published_date", "")
                article.setdefault("word_count", 0)
                article.setdefault("content_gaps_addressed", [])
                article.setdefault("target_volume", 0)
                article.setdefault("keyword_difficulty", "")
                article.setdefault("estimated_traffic_monthly", "")

                _upsert_article_entry(
                    workspace_root=seo_server.workspace_root,
                    website_path=website_path,
                    entry=article,
                )

                updated_brief = _complete_task_in_brief(
                    brief_path=brief_file,
                    task_id=task_id,
                    article_id=article_id,
                )

                result = PublishAndCompleteResult(
                    website_path=website_path,
                    brief_path=str(brief_file),
                    task_id=task_id,
                    article_id=article_id,
                    updated_articles_json=True,
                    updated_brief=updated_brief,
                )
                return [TextContent(type="text", text=result.model_dump_json(indent=2))]

            elif name == SEOTools.GET_ARTICLES_INDEX:
                result = _get_articles_index(
                    workspace_root=seo_server.workspace_root,
                    website_path=arguments["website_path"],
                    status=arguments.get("status"),
                )
                return [TextContent(type="text", text=result.model_dump_json(indent=2))]

            # --- Clustering & Linking handlers ---
            elif name == SEOTools.SCAN_INTERNAL_LINKS:
                from .clustering_linking import scan_internal_links
                res = scan_internal_links(seo_server.workspace_root, arguments["website_path"])
                output = {
                    "website_path": res.website_path,
                    "total_articles": res.total_articles,
                    "total_internal_links": res.total_internal_links,
                    "articles_with_outgoing": res.articles_with_outgoing,
                    "articles_with_incoming": res.articles_with_incoming,
                    "orphan_articles": res.orphan_articles,
                    "profiles": [
                        {
                            "id": p.id, "title": p.title, "file": p.file,
                            "outgoing_ids": p.outgoing_ids, "incoming_ids": p.incoming_ids,
                        }
                        for p in res.profiles if p.outgoing_ids or p.incoming_ids
                    ],
                }
                return [TextContent(type="text", text=json.dumps(output, indent=2))]

            elif name == SEOTools.GENERATE_LINKING_PLAN:
                from .clustering_linking import generate_linking_plan
                res = generate_linking_plan(
                    seo_server.workspace_root,
                    arguments["website_path"],
                    brief_path=arguments.get("brief_path"),
                    clusters_json=arguments.get("clusters_json"),
                )
                output = {
                    "website_path": res.website_path,
                    "total_planned": res.total_planned,
                    "already_linked": res.already_linked,
                    "missing_links": res.missing_links,
                    "items": [
                        {
                            "source_id": it.source_id, "source_title": it.source_title,
                            "target_id": it.target_id, "target_title": it.target_title,
                            "link_type": it.link_type, "already_exists": it.already_exists,
                        }
                        for it in res.items
                    ],
                }
                return [TextContent(type="text", text=json.dumps(output, indent=2))]

            elif name == SEOTools.ADD_ARTICLE_LINKS:
                from .clustering_linking import add_article_links
                res = add_article_links(
                    seo_server.workspace_root,
                    arguments["website_path"],
                    source_id=int(arguments["source_id"]),
                    target_ids=[int(t) for t in arguments["target_ids"]],
                    mode=arguments.get("mode", "related-section"),
                    dry_run=bool(arguments.get("dry_run", False)),
                )
                output = {
                    "source_id": res.source_id, "source_file": res.source_file,
                    "mode": res.mode, "links_added": res.links_added,
                    "links_skipped": res.links_skipped,
                }
                return [TextContent(type="text", text=json.dumps(output, indent=2))]

            elif name == SEOTools.GET_ARTICLE_CONTENT:
                from .clustering_linking import get_article_content
                res = get_article_content(
                    seo_server.workspace_root,
                    arguments["website_path"],
                    article_id=int(arguments["article_id"]),
                )
                return [TextContent(type="text", text=json.dumps(res, indent=2))]

            elif name == SEOTools.UPDATE_BRIEF_LINKING_STATUS:
                from .clustering_linking import update_brief_linking_status
                res = update_brief_linking_status(
                    seo_server.workspace_root,
                    arguments["website_path"],
                    brief_path=arguments.get("brief_path"),
                    dry_run=bool(arguments.get("dry_run", False)),
                )
                output = {
                    "brief_path": res.brief_path,
                    "items_checked": res.items_checked,
                    "items_already_done": res.items_already_done,
                    "items_still_pending": res.items_still_pending,
                }
                return [TextContent(type="text", text=json.dumps(output, indent=2))]

            elif name == SEOTools.BATCH_ADD_LINKS:
                from .clustering_linking import add_article_links, generate_linking_plan
                plan = generate_linking_plan(
                    seo_server.workspace_root,
                    arguments["website_path"],
                    brief_path=arguments.get("brief_path"),
                )
                mode = arguments.get("mode", "related-section")
                dry_run = bool(arguments.get("dry_run", False))
                missing_by_source: dict[int, list[int]] = {}
                for it in plan.items:
                    if not it.already_exists:
                        missing_by_source.setdefault(it.source_id, []).append(it.target_id)
                total_added = 0
                total_skipped = 0
                results = []
                for src_id, tgt_ids in sorted(missing_by_source.items()):
                    try:
                        res = add_article_links(
                            seo_server.workspace_root, arguments["website_path"],
                            source_id=src_id, target_ids=tgt_ids, mode=mode, dry_run=dry_run,
                        )
                        total_added += len(res.links_added)
                        total_skipped += len(res.links_skipped)
                        results.append({"source_id": src_id, "links_added": len(res.links_added), "links_skipped": len(res.links_skipped)})
                    except Exception as e:
                        results.append({"source_id": src_id, "error": str(e)})
                output = {
                    "website_path": arguments["website_path"], "mode": mode, "dry_run": dry_run,
                    "total_sources": len(missing_by_source), "total_links_added": total_added,
                    "total_links_skipped": total_skipped, "results": results,
                }
                return [TextContent(type="text", text=json.dumps(output, indent=2))]

            elif name == SEOTools.OPS_OVERVIEW:
                result = seo_ops.overview()
                return [TextContent(type="text", text=json.dumps(result, indent=2))]

            elif name == SEOTools.OPS_SITE_METRICS:
                site = seo_ops.get_site_by_id(arguments["website_id"])
                if not site:
                    return [TextContent(type="text", text=json.dumps({"ok": False, "error": "Unknown website_id"}, indent=2))]
                result = seo_ops.compute_site_metrics(site)
                return [TextContent(type="text", text=json.dumps({"ok": True, "site": result}, indent=2))]

            elif name == SEOTools.OPS_DRIFT:
                site = seo_ops.get_site_by_id(arguments["website_id"])
                if not site:
                    return [TextContent(type="text", text=json.dumps({"ok": False, "error": "Unknown website_id"}, indent=2))]
                result = seo_ops.compute_repo_drift(site)
                return [TextContent(type="text", text=json.dumps(result, indent=2))]

            elif name == SEOTools.OPS_IMPORT_PREVIEW:
                site = seo_ops.get_site_by_id(arguments["website_id"])
                if not site:
                    return [TextContent(type="text", text=json.dumps({"ok": False, "error": "Unknown website_id"}, indent=2))]
                result = seo_ops.preview_import_from_repo(site)
                return [TextContent(type="text", text=json.dumps(result, indent=2))]

            elif name == SEOTools.OPS_IMPORT_APPLY:
                site = seo_ops.get_site_by_id(arguments["website_id"])
                if not site:
                    return [TextContent(type="text", text=json.dumps({"ok": False, "error": "Unknown website_id"}, indent=2))]
                result = seo_ops.apply_import_from_repo(site)
                return [TextContent(type="text", text=json.dumps(result, indent=2))]

            elif name == SEOTools.OPS_DATES_ANALYZE:
                site = seo_ops.get_site_by_id(arguments["website_id"])
                if not site:
                    return [TextContent(type="text", text=json.dumps({"ok": False, "error": "Unknown website_id"}, indent=2))]
                result = seo_ops.analyze_site_dates(site)
                return [TextContent(type="text", text=json.dumps(result, indent=2))]

            elif name == SEOTools.OPS_SCHEDULE_PREVIEW:
                site = seo_ops.get_site_by_id(arguments["website_id"])
                if not site:
                    return [TextContent(type="text", text=json.dumps({"ok": False, "error": "Unknown website_id"}, indent=2))]
                spacing_days = int(arguments.get("spacing_days", 2) or 2)
                statuses = arguments.get("statuses")
                if statuses is None:
                    statuses = ["ready_to_publish"]
                else:
                    statuses = [str(s) for s in (statuses or [])]
                result = seo_ops.preview_date_schedule(site, spacing_days=spacing_days, statuses=statuses)
                if arguments.get("compact"):
                    from .cli import _compact_schedule_apply
                    result = _compact_schedule_apply(result)
                return [TextContent(type="text", text=json.dumps(result, indent=2))]

            elif name == SEOTools.OPS_SCHEDULE_APPLY:
                site = seo_ops.get_site_by_id(arguments["website_id"])
                if not site:
                    return [TextContent(type="text", text=json.dumps({"ok": False, "error": "Unknown website_id"}, indent=2))]
                spacing_days = int(arguments.get("spacing_days", 2) or 2)
                statuses = arguments.get("statuses")
                if statuses is None:
                    statuses = ["ready_to_publish"]
                else:
                    statuses = [str(s) for s in (statuses or [])]
                result = seo_ops.apply_date_schedule(site, spacing_days=spacing_days, statuses=statuses)
                if arguments.get("compact"):
                    from .cli import _compact_schedule_apply
                    result = _compact_schedule_apply(result)
                return [TextContent(type="text", text=json.dumps(result, indent=2))]

            elif name == SEOTools.OPS_REPORT_OVERVIEW_MARKDOWN:
                md = seo_ops.build_overview_markdown_report()
                return [TextContent(type="text", text=md)]

            elif name == SEOTools.OPS_REPORT_SITE_MARKDOWN:
                site = seo_ops.get_site_by_id(arguments["website_id"])
                if not site:
                    return [TextContent(type="text", text="# SEO Report\n\nUnknown website_id\n")]
                md = seo_ops.build_site_markdown_report(
                    site,
                    include_drift=bool(arguments.get("include_drift", False)),
                    include_dates=bool(arguments.get("include_dates", True)),
                    include_schedule_preview=bool(arguments.get("include_schedule_preview", True)),
                    spacing_days=int(arguments.get("spacing_days", 2) or 2),
                    max_items=int(arguments.get("max_items", 25) or 25),
                )
                return [TextContent(type="text", text=md)]

            elif name == SEOTools.OPS_VALIDATE_INDEX:
                site = seo_ops.get_site_by_id(arguments["website_id"])
                if not site:
                    return [TextContent(type="text", text=json.dumps({"ok": False, "error": "Unknown website_id"}, indent=2))]
                ids = arguments.get("ids")
                if ids is not None:
                    try:
                        ids = [int(x) for x in (ids or [])]
                    except Exception:
                        ids = None
                max_repo_candidates = int(arguments.get("max_repo_candidates", 5) or 5)
                result = seo_ops.validate_site_index(site, ids=ids, max_repo_candidates=max_repo_candidates)
                return [TextContent(type="text", text=json.dumps(result, indent=2))]

            elif name == SEOTools.OPS_SYNC_AND_OPTIMIZE:
                site = seo_ops.get_site_by_id(arguments["website_id"])
                if not site:
                    return [TextContent(type="text", text=json.dumps({"ok": False, "error": "Unknown website_id"}, indent=2))]
                
                auto_fix = bool(arguments.get("auto_fix", False))
                spacing_days = int(arguments.get("spacing_days", 2) or 2)
                max_recent_days = int(arguments.get("max_recent_days", 14) or 14)
                dry_run = bool(arguments.get("dry_run", True))
                auto_deploy = bool(arguments.get("auto_deploy", False))
                target_statuses = arguments.get("target_statuses")
                if target_statuses is not None:
                    target_statuses = [str(s) for s in (target_statuses or [])]
                
                result = seo_ops.sync_and_optimize(
                    site=site,
                    auto_fix=auto_fix,
                    spacing_days=spacing_days,
                    max_recent_days=max_recent_days,
                    dry_run=dry_run,
                    auto_deploy=auto_deploy,
                    target_statuses=target_statuses,
                )
                if arguments.get("compact"):
                    from .cli import _compact_sync_and_optimize
                    result = _compact_sync_and_optimize(result)
                return [TextContent(type="text", text=json.dumps(result, indent=2))]
            
            else:
                return [
                    TextContent(
                        type="text",
                        text=f"Unknown tool: {name}"
                    )
                ]
                
        except Exception as e:
            return [
                TextContent(
                    type="text",
                    text=f"Error executing {name}: {str(e)}"
                )
            ]
    
    # Run the server
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


def main():
    """Main entry point"""
    import asyncio
    asyncio.run(serve())


if __name__ == "__main__":
    main()
