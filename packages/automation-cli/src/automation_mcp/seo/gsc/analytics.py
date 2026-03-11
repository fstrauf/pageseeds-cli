"""Search Analytics API operations."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, Sequence


@dataclass(frozen=True)
class PageMetrics:
    """Metrics for a single page."""
    page: str
    clicks: float
    impressions: float
    ctr: float
    position: float


@dataclass(frozen=True)
class QueryMetrics:
    """Metrics for a single query."""
    query: str
    clicks: float
    impressions: float
    ctr: float
    position: float


@dataclass(frozen=True)
class MoverMetrics:
    """Metrics showing change between two periods."""
    key: str  # page or query
    current_clicks: float
    current_impressions: float
    current_position: float
    previous_clicks: float
    previous_impressions: float
    previous_position: float
    clicks_delta: float
    impressions_delta: float
    position_delta: float


def _date_range(days: int, *, end_offset_days: int = 1) -> tuple[str, str]:
    """Get ISO date range."""
    end_date = dt.date.today() - dt.timedelta(days=end_offset_days)
    start_date = end_date - dt.timedelta(days=days - 1)
    return start_date.isoformat(), end_date.isoformat()


def fetch_page_rows(
    service: Any,
    site_url: str,
    start_date: str,
    end_date: str,
    limit: int = 1000,
) -> dict[str, PageMetrics]:
    """Fetch page-level metrics from Search Analytics.
    
    Args:
        service: Search Console API service
        site_url: Site property URL (e.g., "sc-domain:example.com")
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        limit: Maximum rows to fetch
        
    Returns:
        Dict mapping page URL to PageMetrics
    """
    body = {
        "startDate": start_date,
        "endDate": end_date,
        "dimensions": ["page"],
        "rowLimit": max(1, limit),
        "dataState": "final",
    }
    
    response = service.searchanalytics().query(siteUrl=site_url, body=body).execute()
    rows = response.get("rows", []) or []
    
    result: dict[str, PageMetrics] = {}
    for row in rows:
        keys = row.get("keys", []) or []
        page = str(keys[0]) if keys else ""
        if not page:
            continue
        result[page] = PageMetrics(
            page=page,
            clicks=row.get("clicks", 0.0),
            impressions=row.get("impressions", 0.0),
            ctr=row.get("ctr", 0.0),
            position=row.get("position", 0.0),
        )
    
    return result


def fetch_queries_for_page(
    service: Any,
    site_url: str,
    page_url: str,
    start_date: str,
    end_date: str,
    limit: int = 100,
) -> list[QueryMetrics]:
    """Fetch query-level metrics for a specific page.
    
    Args:
        service: Search Console API service
        site_url: Site property URL
        page_url: Specific page URL to filter by
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        limit: Maximum rows to fetch
        
    Returns:
        List of QueryMetrics sorted by impressions (descending)
    """
    body = {
        "startDate": start_date,
        "endDate": end_date,
        "dimensions": ["query"],
        "dimensionFilterGroups": [{
            "filters": [{
                "dimension": "page",
                "operator": "equals",
                "expression": page_url,
            }]
        }],
        "rowLimit": max(1, limit),
        "dataState": "final",
    }
    
    try:
        response = service.searchanalytics().query(siteUrl=site_url, body=body).execute()
    except Exception:
        return []
    
    rows = response.get("rows", []) or []
    
    result: list[QueryMetrics] = []
    for row in rows:
        keys = row.get("keys", []) or []
        query = str(keys[0]) if keys else ""
        if not query:
            continue
        result.append(QueryMetrics(
            query=query,
            clicks=row.get("clicks", 0.0),
            impressions=row.get("impressions", 0.0),
            ctr=row.get("ctr", 0.0),
            position=row.get("position", 0.0),
        ))
    
    return sorted(result, key=lambda x: x.impressions, reverse=True)


def compute_movers(
    current_data: dict[str, PageMetrics] | list[QueryMetrics],
    previous_data: dict[str, PageMetrics] | list[QueryMetrics],
    min_impressions: float = 0,
) -> list[MoverMetrics]:
    """Compute movers (changes) between two periods.
    
    Args:
        current_data: Metrics from current period
        previous_data: Metrics from previous period
        min_impressions: Minimum impressions to include (filters noise)
        
    Returns:
        List of MoverMetrics sorted by absolute impression change
    """
    # Normalize inputs to dicts
    if isinstance(current_data, list):
        current_dict = {m.query: m for m in current_data}
    else:
        current_dict = current_data
        
    if isinstance(previous_data, list):
        previous_dict = {m.query: m for m in previous_data}
    else:
        previous_dict = previous_data
    
    all_keys = set(current_dict.keys()) | set(previous_dict.keys())
    
    movers: list[MoverMetrics] = []
    for key in all_keys:
        curr = current_dict.get(key)
        prev = previous_dict.get(key)
        
        curr_imp = curr.impressions if curr else 0.0
        prev_imp = prev.impressions if prev else 0.0
        
        # Skip if below threshold
        if curr_imp < min_impressions and prev_imp < min_impressions:
            continue
        
        movers.append(MoverMetrics(
            key=key,
            current_clicks=curr.clicks if curr else 0.0,
            current_impressions=curr_imp,
            current_position=curr.position if curr else 0.0,
            previous_clicks=prev.clicks if prev else 0.0,
            previous_impressions=prev_imp,
            previous_position=prev.position if prev else 0.0,
            clicks_delta=(curr.clicks if curr else 0.0) - (prev.clicks if prev else 0.0),
            impressions_delta=curr_imp - prev_imp,
            position_delta=(curr.position if curr else 0.0) - (prev.position if prev else 0.0),
        ))
    
    # Sort by absolute impression change (descending)
    return sorted(movers, key=lambda x: abs(x.impressions_delta), reverse=True)


def get_top_pages(
    service: Any,
    site_url: str,
    days: int = 7,
    limit: int = 10,
) -> list[PageMetrics]:
    """Get top pages by impressions.
    
    Args:
        service: Search Console API service
        site_url: Site property URL
        days: Number of days to analyze
        limit: Maximum pages to return
        
    Returns:
        List of PageMetrics sorted by impressions
    """
    start_date, end_date = _date_range(days)
    pages = fetch_page_rows(service, site_url, start_date, end_date, limit)
    return sorted(pages.values(), key=lambda x: x.impressions, reverse=True)[:limit]


def get_decliners(
    service: Any,
    site_url: str,
    days: int = 7,
    limit: int = 10,
) -> list[MoverMetrics]:
    """Get pages with biggest impression drops.
    
    Args:
        service: Search Console API service
        site_url: Site property URL
        days: Comparison window size
        limit: Maximum pages to return
        
    Returns:
        List of MoverMetrics with negative impression_delta
    """
    # Current period
    cur_start, cur_end = _date_range(days, end_offset_days=1)
    current = fetch_page_rows(service, site_url, cur_start, cur_end, 1000)
    
    # Previous period
    prev_end = dt.date.fromisoformat(cur_start) - dt.timedelta(days=1)
    prev_start = prev_end - dt.timedelta(days=days - 1)
    previous = fetch_page_rows(
        service, site_url, 
        prev_start.isoformat(), 
        prev_end.isoformat(),
        1000
    )
    
    movers = compute_movers(current, previous)
    
    # Filter to decliners only, sort by most negative
    decliners = [m for m in movers if m.impressions_delta < 0]
    return sorted(decliners, key=lambda x: x.impressions_delta)[:limit]


def get_query_movers_for_page(
    service: Any,
    site_url: str,
    page_url: str,
    days: int = 7,
    limit: int = 10,
) -> list[MoverMetrics]:
    """Get query movers for a specific page.
    
    Args:
        service: Search Console API service
        site_url: Site property URL
        page_url: Specific page URL
        days: Comparison window size
        limit: Maximum queries to return
        
    Returns:
        List of MoverMetrics sorted by absolute change
    """
    # Current period
    cur_start, cur_end = _date_range(days, end_offset_days=1)
    current = fetch_queries_for_page(service, site_url, page_url, cur_start, cur_end, 100)
    
    # Previous period
    prev_end = dt.date.fromisoformat(cur_start) - dt.timedelta(days=1)
    prev_start = prev_end - dt.timedelta(days=days - 1)
    previous = fetch_queries_for_page(
        service, site_url, page_url,
        prev_start.isoformat(),
        prev_end.isoformat(),
        100
    )
    
    movers = compute_movers(current, previous, min_impressions=10)
    return movers[:limit]
