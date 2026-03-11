"""
Tests for DateManager.
"""
import sys
import os
import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from dashboard.utils.date_manager import DateManager
from dashboard.utils.errors import DateAllocationError


def create_test_articles_json(articles=None):
    """Create a temporary articles.json file."""
    data = {
        "articles": articles or [],
        "nextArticleId": 1
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(data, f)
        return Path(f.name)


def test_get_all_dates_empty():
    """Test getting dates from empty articles.json."""
    json_path = create_test_articles_json([])
    try:
        dm = DateManager(json_path)
        dates = dm.get_all_dates()
        assert dates == set()
        print("✓ get_all_dates with empty articles")
    finally:
        json_path.unlink()


def test_get_all_dates_with_articles():
    """Test getting dates from articles.json with articles."""
    articles = [
        {"id": 1, "published_date": "2026-02-25", "status": "published"},
        {"id": 2, "published_date": "2026-02-27", "status": "published"},
        {"id": 3, "published_date": "2026-03-01", "status": "draft"},
    ]
    json_path = create_test_articles_json(articles)
    try:
        dm = DateManager(json_path)
        dates = dm.get_all_dates()
        
        assert len(dates) == 3
        assert datetime(2026, 2, 25).date() in dates
        assert datetime(2026, 2, 27).date() in dates
        assert datetime(2026, 3, 1).date() in dates
        print("✓ get_all_dates with articles")
    finally:
        json_path.unlink()


def test_is_date_available():
    """Test date availability checking."""
    articles = [
        {"id": 1, "published_date": "2026-02-25", "status": "published"},
    ]
    json_path = create_test_articles_json(articles)
    try:
        dm = DateManager(json_path)
        
        assert not dm.is_date_available("2026-02-25")  # Taken
        assert dm.is_date_available("2026-02-26")  # Available
        assert dm.is_date_available("2026-02-24")  # Available
        print("✓ is_date_available")
    finally:
        json_path.unlink()


def test_get_next_available_date_empty():
    """Test getting next date when no articles exist."""
    json_path = create_test_articles_json([])
    try:
        dm = DateManager(json_path)
        next_date = dm.get_next_available_date()
        
        # Should return today
        today = datetime.now().date()
        assert next_date.date() == today
        print("✓ get_next_available_date with empty articles")
    finally:
        json_path.unlink()


def test_get_next_available_date_with_gap():
    """Test getting next date with existing articles."""
    today = datetime.now()
    yesterday = today - timedelta(days=1)
    yesterday_str = yesterday.strftime("%Y-%m-%d")
    
    articles = [
        {"id": 1, "published_date": yesterday_str, "status": "published"},
    ]
    json_path = create_test_articles_json(articles)
    try:
        dm = DateManager(json_path)
        next_date = dm.get_next_available_date()
        
        # Should be latest + 2 days
        expected = yesterday + timedelta(days=2)
        assert next_date.date() == expected.date()
        print("✓ get_next_available_date with gap")
    finally:
        json_path.unlink()


def test_get_available_slots():
    """Test getting multiple available slots."""
    today = datetime.now()
    yesterday = today - timedelta(days=1)
    yesterday_str = yesterday.strftime("%Y-%m-%d")
    
    articles = [
        {"id": 1, "published_date": yesterday_str, "status": "published"},
    ]
    json_path = create_test_articles_json(articles)
    try:
        dm = DateManager(json_path)
        slots = dm.get_available_slots(count=4)
        
        assert len(slots) == 4
        
        # Each slot should be 2 days apart
        dates = [datetime.strptime(s, "%Y-%m-%d") for s in slots]
        for i in range(1, len(dates)):
            gap = (dates[i] - dates[i-1]).days
            assert gap == 2, f"Expected 2-day gap, got {gap}"
        
        print("✓ get_available_slots with 2-day gaps")
    finally:
        json_path.unlink()


def test_invalid_json_handling():
    """Test handling of invalid JSON."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write("not valid json")
        json_path = Path(f.name)
    
    try:
        dm = DateManager(json_path)
        dates = dm.get_all_dates()
        # Should return empty set, not raise
        assert dates == set()
        print("✓ Invalid JSON handling")
    finally:
        json_path.unlink()


if __name__ == "__main__":
    print("=== Testing DateManager ===\n")
    test_get_all_dates_empty()
    test_get_all_dates_with_articles()
    test_is_date_available()
    test_get_next_available_date_empty()
    test_get_next_available_date_with_gap()
    test_get_available_slots()
    test_invalid_json_handling()
    print("\n=== All DateManager Tests Passed ===")
