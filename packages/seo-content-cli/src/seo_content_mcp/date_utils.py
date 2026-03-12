"""Simple date utilities for article scheduling.

Rules:
1. Never future dates
2. Never overlapping dates  
3. Published articles never change
"""

from datetime import datetime, timedelta
from typing import List


def get_next_article_date(articles: List[dict]) -> str:
    """
    Get the next safe date for a new article.
    
    Strategy: Place 2 days before the earliest existing date.
    This guarantees:
    - No future dates (always in the past)
    - No overlaps (always 2+ days from any existing date)
    - Published articles unchanged (we never modify existing dates)
    
    Args:
        articles: List of article dicts from articles.json
        
    Returns:
        Date string in YYYY-MM-DD format
    """
    if not articles:
        # First article ever → yesterday
        date = datetime.now().date() - timedelta(days=1)
        return date.strftime("%Y-%m-%d")
    
    # Collect all existing dates (any status)
    existing_dates = set()
    for a in articles:
        if pd := a.get("published_date"):
            try:
                existing_dates.add(datetime.strptime(pd, "%Y-%m-%d").date())
            except ValueError:
                continue
    
    if not existing_dates:
        date = datetime.now().date() - timedelta(days=1)
    else:
        # 2 days before the earliest existing date
        date = min(existing_dates) - timedelta(days=2)
    
    return date.strftime("%Y-%m-%d")


def validate_article_dates(articles: List[dict]) -> List[str]:
    """
    Validate all article dates. Returns list of errors (empty if valid).
    
    Checks:
    - No future dates
    - No duplicate dates
    - Valid date format
    """
    errors = []
    today = datetime.now().date()
    dates_seen = {}
    
    for a in articles:
        article_id = a.get("id", "unknown")
        
        if not (pd := a.get("published_date")):
            continue
        
        # Check format
        try:
            d = datetime.strptime(pd, "%Y-%m-%d").date()
        except ValueError:
            errors.append(f"Article {article_id}: invalid date format '{pd}'")
            continue
        
        # Check future
        if d > today:
            errors.append(f"Article {article_id}: future date {pd}")
        
        # Check duplicates
        if pd in dates_seen:
            errors.append(f"Article {article_id}: duplicate date {pd} (also on article {dates_seen[pd]})")
        else:
            dates_seen[pd] = article_id
    
    return errors


def get_date_statistics(articles: List[dict]) -> dict:
    """
    Get statistics about article dates.
    """
    dates = []
    for a in articles:
        if pd := a.get("published_date"):
            try:
                dates.append(datetime.strptime(pd, "%Y-%m-%d").date())
            except ValueError:
                continue
    
    if not dates:
        return {
            "count": 0,
            "earliest": None,
            "latest": None,
            "span_days": 0
        }
    
    return {
        "count": len(dates),
        "earliest": min(dates).strftime("%Y-%m-%d"),
        "latest": max(dates).strftime("%Y-%m-%d"),
        "span_days": (max(dates) - min(dates)).days
    }
