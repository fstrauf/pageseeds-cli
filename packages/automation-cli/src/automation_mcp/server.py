"""Automation MCP Server - Unified Reddit and SEO operations

Consolidates functionality from:
- reddit-mcp (Reddit API operations)
- reddit-db-mcp (Reddit database operations)  
- seo-mcp (SEO research tools)
- seo-content-mcp (SEO content management)

Usage:
    python -m automation_mcp.server
"""

import json
import os
import sqlite3
import subprocess
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastmcp import FastMCP
from pydantic import BaseModel

# Initialize FastMCP with custom serializer
def custom_serializer(data: Any) -> str:
    """Custom serializer to handle string returns correctly"""
    if isinstance(data, str):
        return data
    return json.dumps(data)

mcp = FastMCP(
    "automation-mcp",
    strict_input_validation=False,
    tool_serializer=custom_serializer
)

# Configuration
REPO_ROOT = Path(__file__).resolve().parents[4]  # automation-mcp/src/automation_mcp/ → repo root
DATABASE_PATH = REPO_ROOT / "tools" / ".data" / "client_ops.db"

# ============================================================================
# REDDIT OPERATIONS
# ============================================================================

# Import reddit tools
try:
    from .reddit.api import RedditAPI
    reddit_api = RedditAPI()
except ImportError:
    reddit_api = None

# Import reddit database tools
from .reddit.database import (
    get_connection,
    ensure_reddit_table,
    validate_reply_text,
    insert_reddit_opportunity,
    get_pending_opportunities,
    get_posted_opportunities,
    mark_opportunity_posted,
    mark_opportunity_skipped,
    get_reddit_statistics,
    update_opportunity_performance
)

# ============================================================================
# SEO OPERATIONS  
# ============================================================================

# Import SEO tools
from .seo.research import (
    keyword_generator,
    keyword_difficulty,
    batch_keyword_difficulty,
    get_backlinks_list,
    get_traffic
)

from .seo.content import (
    get_articles_summary,
    get_next_article_id,
    append_draft_articles,
    get_articles_by_keyword,
    get_articles_index,
    clean_content,
    validate_content,
    analyze_dates,
    fix_dates,
    test_distribution,
    filter_new_keywords,
    get_next_content_task,
    plan_content_article,
    publish_article_and_complete_task,
    ops_schedule_apply,
    ops_sync_and_optimize
)

# =========================================================================
# GEO / PLACES (GOOGLE MAPS VIA PLAYWRIGHT)
# =========================================================================

from .geo.google_maps import GoogleMapsClient, enrich_csv_with_google_maps

# ============================================================================
# REDDIT TOOLS
# ============================================================================

@mcp.tool()
def reddit_search_submissions(
    query: str,
    subreddit: str = "",
    limit: int = 10,
    sort: str = "relevance",
    time: str = "all"
) -> str:
    """Search for submissions/posts on Reddit
    
    Args:
        query: Search query string
        subreddit: Optional subreddit to search within (empty for all)
        limit: Maximum number of results (default: 10)
        sort: Sort order - relevance, hot, top, new, comments (default: relevance)
        time: Time filter - all, day, week, month, year (default: all)
    """
    if reddit_api is None:
        return json.dumps({"error": "Reddit API not initialized"})
    
    try:
        posts = reddit_api.search_submissions(query, subreddit, limit, sort, time)
        return json.dumps({"posts": [post.model_dump() for post in posts]}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def reddit_read_submission(
    post_id: str,
    comment_limit: int = 10,
    comment_depth: int = 3
) -> str:
    """Read detailed content of a specific post including comments
    
    Args:
        post_id: Reddit post ID (e.g., '1abc123')
        comment_limit: Maximum number of comments to fetch (default: 10)
        comment_depth: Depth of comment tree to fetch (default: 3)
    """
    if reddit_api is None:
        return json.dumps({"error": "Reddit API not initialized"})
    
    try:
        post_detail = reddit_api.get_post_content(post_id, comment_limit, comment_depth)
        return json.dumps(post_detail.model_dump(), indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def reddit_insert_opportunity(
    project_name: str,
    post_id: str,
    title: str,
    url: str,
    subreddit: str,
    author: str,
    posted_date: str,
    upvotes: int,
    comment_count: int,
    days_old: int,
    relevance_score: float,
    engagement_score: float,
    accessibility_score: float,
    final_score: float,
    severity: str,
    why_relevant: str,
    key_pain_points: List[str],
    website_fit: str,
    reply_text: str
) -> str:
    """Insert a Reddit opportunity into the database
    
    Args:
        project_name: Project slug (e.g., 'coffee', 'expense')
        post_id: Reddit post ID (e.g., '1abc123')
        title: Post title
        url: Post URL
        subreddit: Subreddit name
        author: Post author username
        posted_date: ISO format date string
        upvotes: Number of upvotes
        comment_count: Number of comments
        days_old: Days since posted
        relevance_score: 0-10 relevance score
        engagement_score: 0-10 engagement score
        accessibility_score: 0-10 accessibility score
        final_score: Average of scores
        severity: CRITICAL, HIGH, MEDIUM, or LOW
        why_relevant: Explanation of relevance
        key_pain_points: List of pain points
        website_fit: How website addresses this
        reply_text: Drafted reply text
    """
    try:
        # Validate reply first
        is_valid, error_msg = validate_reply_text(reply_text)
        if not is_valid:
            return json.dumps({"error": f"Invalid reply: {error_msg}"})
        
        # Insert to database
        result = insert_reddit_opportunity(
            project_name=project_name,
            post_id=post_id,
            title=title,
            url=url,
            subreddit=subreddit,
            author=author,
            posted_date=posted_date,
            upvotes=upvotes,
            comment_count=comment_count,
            days_old=days_old,
            relevance_score=relevance_score,
            engagement_score=engagement_score,
            accessibility_score=accessibility_score,
            final_score=final_score,
            severity=severity,
            why_relevant=why_relevant,
            key_pain_points=key_pain_points,
            website_fit=website_fit,
            reply_text=reply_text
        )
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def reddit_get_pending_opportunities(
    project_name: str,
    severity: str = ""
) -> str:
    """Get pending opportunities for a project
    
    Args:
        project_name: Project slug (e.g., 'coffee')
        severity: Optional filter - CRITICAL, HIGH, MEDIUM, LOW
    """
    try:
        opportunities = get_pending_opportunities(project_name, severity)
        return json.dumps({"opportunities": opportunities}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def reddit_get_posted_opportunities(
    project_name: str,
    days: int = 30
) -> str:
    """Get posted opportunities for performance tracking
    
    Args:
        project_name: Project slug (e.g., 'coffee')
        days: Number of days to look back (default: 30)
    """
    try:
        opportunities = get_posted_opportunities(project_name, days)
        return json.dumps({"opportunities": opportunities}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def reddit_mark_opportunity_posted(
    post_id: str,
    reply_text: str,
    reply_url: str = ""
) -> str:
    """Mark an opportunity as posted
    
    Args:
        post_id: Reddit post ID
        reply_text: The posted reply text
        reply_url: Optional URL to the posted comment
    """
    try:
        result = mark_opportunity_posted(post_id, reply_text, reply_url)
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def reddit_mark_opportunity_skipped(
    post_id: str,
    reason: str = ""
) -> str:
    """Mark an opportunity as skipped
    
    Args:
        post_id: Reddit post ID
        reason: Optional reason for skipping
    """
    try:
        result = mark_opportunity_skipped(post_id, reason)
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def reddit_get_statistics(
    project_name: str
) -> str:
    """Get statistics for a project
    
    Args:
        project_name: Project slug (e.g., 'coffee')
    """
    try:
        stats = get_reddit_statistics(project_name)
        return json.dumps(stats, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def reddit_update_performance(
    post_id: str,
    reply_upvotes: int = 0,
    reply_replies: int = 0
) -> str:
    """Update performance metrics for a posted opportunity
    
    Args:
        post_id: Reddit post ID
        reply_upvotes: Current upvotes on reply
        reply_replies: Number of replies to the comment
    """
    try:
        result = update_opportunity_performance(post_id, reply_upvotes, reply_replies)
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": str(e)})

# ============================================================================
# SEO RESEARCH TOOLS
# ============================================================================

@mcp.tool()
def seo_keyword_generator(
    keyword: str,
    country: str = "us",
    search_engine: str = "Google"
) -> str:
    """Generate keyword ideas using CapSolver/Ahrefs data
    
    Args:
        keyword: Seed keyword to generate ideas from
        country: Country code (default: us)
        search_engine: Search engine (default: Google)
    """
    try:
        result = keyword_generator(keyword, country, search_engine)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def seo_keyword_difficulty(
    keyword: str,
    country: str = "us"
) -> str:
    """Analyze keyword difficulty using CapSolver/Ahrefs data
    
    Args:
        keyword: Keyword to analyze
        country: Country code (default: us)
    """
    try:
        result = keyword_difficulty(keyword, country)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def seo_batch_keyword_difficulty(
    keywords: List[str],
    country: str = "us"
) -> str:
    """Analyze multiple keywords at once
    
    Args:
        keywords: List of keywords to analyze
        country: Country code (default: us)
    """
    try:
        result = batch_keyword_difficulty(keywords, country)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def seo_get_backlinks(
    domain: str
) -> str:
    """Get backlink data for a domain
    
    Args:
        domain: Domain to analyze (e.g., 'example.com')
    """
    try:
        result = get_backlinks_list(domain)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def seo_get_traffic(
    domain_or_url: str,
    country: str = "None",
    mode: Literal["subdomains", "exact"] = "subdomains"
) -> str:
    """Get traffic estimates for a domain or URL
    
    Args:
        domain_or_url: Domain or URL to analyze
        country: Country code (default: None for all countries)
        mode: Analysis mode - subdomains or exact (default: subdomains)
    """
    try:
        result = get_traffic(domain_or_url, country, mode)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})

# ============================================================================
# SEO CONTENT TOOLS
# ============================================================================

@mcp.tool()
def seo_get_articles_summary(
    website_path: str
) -> str:
    """Get summary statistics for a project's articles
    
    Args:
        website_path: Path to project folder (e.g., 'general/coffee')
    """
    try:
        result = get_articles_summary(website_path)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def seo_filter_new_keywords(
    website_path: str,
    keywords: List[str]
) -> str:
    """Filter new keywords against existing articles
    
    Args:
        website_path: Path to project folder (e.g., 'general/coffee')
        keywords: List of candidate keywords to filter
    """
    try:
        result = filter_new_keywords(website_path, keywords)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def seo_append_draft_articles(
    website_path: str,
    drafts: List[Dict[str, Any]]
) -> str:
    """Append draft articles to articles.json
    
    Args:
        website_path: Path to project folder (e.g., 'general/coffee')
        drafts: List of draft article objects with title, target_keyword, etc.
    """
    try:
        result = append_draft_articles(website_path, drafts)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def seo_get_articles_by_keyword(
    website_path: str,
    keyword: str
) -> str:
    """Find articles by keyword (cannibalization check)
    
    Args:
        website_path: Path to project folder (e.g., 'general/coffee')
        keyword: Keyword to search for
    """
    try:
        result = get_articles_by_keyword(website_path, keyword)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def seo_get_articles_index(
    website_path: str,
    status: str = ""
) -> str:
    """Get index of all articles
    
    Args:
        website_path: Path to project folder (e.g., 'general/coffee')
        status: Optional filter - draft, published, etc.
    """
    try:
        result = get_articles_index(website_path, status)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def seo_validate_content(
    website_path: str
) -> str:
    """Validate content files for issues
    
    Args:
        website_path: Path to project folder (e.g., 'general/coffee')
    """
    try:
        result = validate_content(website_path)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def seo_clean_content(
    website_path: str
) -> str:
    """Clean content files (fix issues)
    
    Args:
        website_path: Path to project folder (e.g., 'general/coffee')
    """
    try:
        result = clean_content(website_path)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def seo_analyze_dates(
    website_path: str
) -> str:
    """Analyze date distribution
    
    Args:
        website_path: Path to project folder (e.g., 'general/coffee')
    """
    try:
        result = analyze_dates(website_path)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def seo_fix_dates(
    website_path: str
) -> str:
    """Fix date distribution issues
    
    Args:
        website_path: Path to project folder (e.g., 'general/coffee')
    """
    try:
        result = fix_dates(website_path)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def seo_schedule_apply(
    website_id: str,
    auto_fix: bool = True
) -> str:
    """Apply scheduling to ready-to-publish articles
    
    Args:
        website_id: Website identifier
        auto_fix: Automatically fix issues (default: True)
    """
    try:
        result = ops_schedule_apply(website_id, auto_fix)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def seo_sync_and_optimize(
    website_id: str,
    auto_fix: bool = True,
    auto_deploy: bool = False,
    dry_run: bool = False
) -> str:
    """Sync articles and optionally deploy
    
    Args:
        website_id: Website identifier
        auto_fix: Automatically fix issues (default: True)
        auto_deploy: Deploy to production (default: False)
        dry_run: Preview changes without applying (default: False)
    """
    try:
        result = ops_sync_and_optimize(website_id, auto_fix, auto_deploy, dry_run)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# =========================================================================
# GEO TOOLS
# =========================================================================


@mcp.tool()
def geo_google_maps_lookup(
    query: str,
    headless: bool = False,
    slow_mo_ms: int = 0,
    timeout_ms: int = 30000,
    cdp_url: str = "",
) -> str:
    """Look up a place on Google Maps and return address + Maps URL.

    Args:
        query: Free-text query (e.g., 'Atomic Coffee, Auckland, New Zealand')
        headless: Run browser headless (default: False)
        slow_mo_ms: Slow motion delay between actions (default: 0)
        timeout_ms: Navigation/selector timeout (default: 30000)
        cdp_url: Optional CDP endpoint to attach to an existing Chrome (e.g. 'http://127.0.0.1:9222')
    """
    try:
        cdp = cdp_url.strip() or None
        with GoogleMapsClient(
            headless=headless,
            slow_mo_ms=slow_mo_ms,
            timeout_ms=timeout_ms,
            cdp_url=cdp,
        ) as client:
            result = client.lookup(query)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"ok": False, "error": str(e)})


@mcp.tool()
def geo_google_maps_enrich_csv(
    input_path: str,
    output_path: str,
    name_column: str = "cafe_name",
    city_column: str = "city_guess",
    country_hint: str = "New Zealand",
    max_rows: int = 0,
    sleep_seconds: float = 1.0,
    headless: bool = False,
    slow_mo_ms: int = 0,
    timeout_ms: int = 30000,
    cdp_url: str = "",
) -> str:
    """Enrich a CSV of cafes with Google Maps address + URL.

    Adds columns:
    - google_maps_query
    - google_maps_place_name
    - google_maps_address
    - google_maps_url
    - google_maps_ok
    - google_maps_error
    """
    try:
        result = enrich_csv_with_google_maps(
            input_path=input_path,
            output_path=output_path,
            name_column=name_column,
            city_column=city_column,
            country_hint=country_hint,
            max_rows=(None if max_rows <= 0 else int(max_rows)),
            sleep_seconds=float(sleep_seconds),
            headless=bool(headless),
            slow_mo_ms=int(slow_mo_ms),
            timeout_ms=int(timeout_ms),
            cdp_url=(cdp_url.strip() or None),
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"ok": False, "error": str(e)})

# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    """Run the MCP server"""
    # Ensure database tables exist
    ensure_reddit_table()
    
    # Run the server
    mcp.run()

if __name__ == "__main__":
    main()
