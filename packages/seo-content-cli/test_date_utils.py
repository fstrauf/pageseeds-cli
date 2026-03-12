#!/usr/bin/env python3
"""Test the new date utilities."""

import sys
import os
from datetime import datetime, timedelta

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from seo_content_mcp.date_utils import (
    get_next_article_date,
    validate_article_dates,
    get_date_statistics
)


def test_get_next_article_date():
    """Test date assignment logic."""
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    
    # Test 1: Empty articles list → yesterday
    result = get_next_article_date([])
    assert result == yesterday.strftime("%Y-%m-%d"), f"Expected {yesterday}, got {result}"
    print("✓ Test 1: Empty articles returns yesterday")
    
    # Test 2: One article → 2 days before it
    articles = [{"id": 1, "published_date": "2025-03-01"}]
    result = get_next_article_date(articles)
    assert result == "2025-02-27", f"Expected 2025-02-27, got {result}"
    print("✓ Test 2: One article → 2 days before")
    
    # Test 3: Multiple articles → 2 days before earliest
    articles = [
        {"id": 1, "published_date": "2025-03-10"},
        {"id": 2, "published_date": "2025-03-05"},
        {"id": 3, "published_date": "2025-03-01"},
    ]
    result = get_next_article_date(articles)
    assert result == "2025-02-27", f"Expected 2025-02-27, got {result}"
    print("✓ Test 3: Multiple articles → 2 days before earliest")
    
    # Test 4: Ignores articles without dates
    articles = [
        {"id": 1, "published_date": "2025-03-01"},
        {"id": 2, "status": "draft"},  # no date
    ]
    result = get_next_article_date(articles)
    assert result == "2025-02-27", f"Expected 2025-02-27, got {result}"
    print("✓ Test 4: Ignores articles without dates")
    
    print()


def test_validate_article_dates():
    """Test validation logic."""
    today = datetime.now().date()
    today_str = today.strftime("%Y-%m-%d")
    tomorrow_str = (today + timedelta(days=1)).strftime("%Y-%m-%d")
    
    # Test 1: Valid articles → no errors
    articles = [
        {"id": 1, "published_date": "2025-02-01"},
        {"id": 2, "published_date": "2025-02-03"},
    ]
    errors = validate_article_dates(articles)
    assert len(errors) == 0, f"Expected no errors, got: {errors}"
    print("✓ Test 1: Valid articles pass validation")
    
    # Test 2: Future date → error
    articles = [
        {"id": 1, "published_date": tomorrow_str},
    ]
    errors = validate_article_dates(articles)
    assert len(errors) == 1, f"Expected 1 error, got: {errors}"
    assert "future date" in errors[0].lower()
    print("✓ Test 2: Future dates rejected")
    
    # Test 3: Duplicate dates → error
    articles = [
        {"id": 1, "published_date": "2025-02-01"},
        {"id": 2, "published_date": "2025-02-01"},
    ]
    errors = validate_article_dates(articles)
    assert len(errors) == 1, f"Expected 1 error, got: {errors}"
    assert "duplicate" in errors[0].lower()
    print("✓ Test 3: Duplicate dates rejected")
    
    # Test 4: Invalid format → error
    articles = [
        {"id": 1, "published_date": "not-a-date"},
    ]
    errors = validate_article_dates(articles)
    assert len(errors) == 1
    assert "invalid" in errors[0].lower()
    print("✓ Test 4: Invalid date format rejected")
    
    print()


def test_integration_scenario():
    """Test a realistic scenario of creating articles."""
    print("Integration scenario: Creating 3 articles in sequence")
    
    articles = []
    
    # Create article 1
    date1 = get_next_article_date(articles)
    articles.append({"id": 1, "published_date": date1})
    print(f"  Article 1: {date1}")
    
    # Create article 2
    date2 = get_next_article_date(articles)
    articles.append({"id": 2, "published_date": date2})
    print(f"  Article 2: {date2}")
    
    # Create article 3
    date3 = get_next_article_date(articles)
    articles.append({"id": 3, "published_date": date3})
    print(f"  Article 3: {date3}")
    
    # Verify no overlaps
    errors = validate_article_dates(articles)
    assert len(errors) == 0, f"Unexpected errors: {errors}"
    
    # Verify all in past
    today = datetime.now().date()
    for a in articles:
        d = datetime.strptime(a["published_date"], "%Y-%m-%d").date()
        assert d <= today, f"Future date found: {d}"
    
    # Verify 2-day spacing
    dates = sorted([datetime.strptime(a["published_date"], "%Y-%m-%d").date() for a in articles])
    for i in range(1, len(dates)):
        gap = (dates[i] - dates[i-1]).days
        assert gap == 2, f"Expected 2-day gap, got {gap}"
    
    print("  ✓ All dates valid, in past, 2-day spacing")
    print()


if __name__ == "__main__":
    print("=== Testing Date Utilities ===\n")
    
    test_get_next_article_date()
    test_validate_article_dates()
    test_integration_scenario()
    
    print("=== All Tests Passed ===")
