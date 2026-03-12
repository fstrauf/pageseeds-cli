"""Integration guide: How to use the new date utilities.

Copy these changes into your existing server.py
"""

# ============================================================================
# STEP 1: Add import at top of server.py
# ============================================================================

# Add this import:
from .date_utils import get_next_article_date, validate_article_dates


# ============================================================================
# STEP 2: Replace _suggest_publish_date function (around line 635)
# ============================================================================

def _suggest_publish_date(*, articles_data: dict) -> str:
    """
    Suggest a safe publish date for a new article.
    
    New behavior: Returns a date 2 days before the earliest existing date.
    This guarantees no future dates and no overlaps.
    """
    articles = articles_data.get("articles", [])
    return get_next_article_date(articles)


# ============================================================================
# STEP 3: Update _plan_content_article (around line 687-690)
# ============================================================================

# OLD CODE (lines 687-690):
#     articles_data = _load_articles_json(workspace_root, website_path)
#     latest = _latest_published_date(articles_data)
#     occupied = _all_article_dates(articles_data)
#     published_date = _suggest_publish_date(latest=latest, occupied=occupied)

# NEW CODE:
#     articles_data = _load_articles_json(workspace_root, website_path)
#     published_date = _suggest_publish_date(articles_data=articles_data)


# ============================================================================
# STEP 4: Add validation before save (optional but recommended)
# ============================================================================

# In _upsert_article_entry (around line 767), add at the start:

def _upsert_article_entry(
    *,
    workspace_root: str,
    website_path: str,
    entry: dict[str, Any],
) -> None:
    data = _load_articles_json(workspace_root, website_path)
    articles = [a for a in data.get("articles", []) if isinstance(a, dict)]
    
    # NEW: Validate dates before saving
    errors = validate_article_dates(articles + [entry])
    if errors:
        raise ValueError(f"Date validation failed: {errors}")
    
    # ... rest of existing function ...


# ============================================================================
# STEP 5: Update tool description (around line 1527)
# ============================================================================

# Update the PLAN_CONTENT_ARTICLE tool description to reflect new behavior:

# OLD:
# "Plan the next content article from a content brief task: computes id, url_slug, file path, and a safe published_date (3 days after latest published, never future). "

# NEW:
# "Plan the next content article from a content brief task: computes id, url_slug, file path, and a safe published_date (2 days before earliest existing date, never future, never overlapping). "
