#!/usr/bin/env python3
"""
Unified test suite for dashboard_ptk.

This test file imports modules as part of the package (works with venv).
"""
import sys
import os
import json
import tempfile
import re
from datetime import datetime, timedelta
from pathlib import Path

# Add parent to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Import from the package (requires venv with rich)
from dashboard.utils.errors import (
    ArticleError,
    DuplicateIdError,
    DuplicateDateError,
    DuplicateSlugError,
    FileExistsError,
    ValidationError,
    ArticlesJsonError,
    IntegrityError,
    SyncError,
    DateAllocationError,
)
from dashboard.utils.date_manager import DateManager
from dashboard.utils.integrity_checker import IntegrityChecker
from dashboard.utils.content_sync import ContentSync
from dashboard.utils.article_manager_refactored import generate_url_slug


# === Helper Functions ===

def create_test_articles_json(articles=None, next_id=1):
    """Create a temporary articles.json file."""
    data = {
        "articles": articles or [],
        "nextArticleId": next_id,
        "statistics": {"total_articles": len(articles or []), "last_updated": "2026-01-01"}
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(data, f)
        return Path(f.name)


# === Error Tests ===

def test_duplicate_id_error():
    """Test DuplicateIdError."""
    err = DuplicateIdError(105)
    assert err.article_id == 105
    assert "105" in err.message
    assert len(err.fix_suggestion) > 0
    print("  ✓ DuplicateIdError")


def test_duplicate_date_error():
    """Test DuplicateDateError."""
    err = DuplicateDateError("2026-02-25", 42)
    assert err.date == "2026-02-25"
    assert err.existing_id == 42
    print("  ✓ DuplicateDateError")


def test_duplicate_slug_error():
    """Test DuplicateSlugError."""
    err = DuplicateSlugError("spy_vs_spx")
    assert err.slug == "spy_vs_spx"
    print("  ✓ DuplicateSlugError")


def test_error_inheritance():
    """Test that all errors inherit from ArticleError."""
    errors = [
        DuplicateIdError(1),
        DuplicateDateError("2026-01-01", 1),
        DuplicateSlugError("test"),
        FileExistsError("test.mdx"),
        ValidationError("title", "x", "bad"),
        ArticlesJsonError("test"),
        IntegrityError([]),
        SyncError("test", "detail"),
        DateAllocationError("test"),
    ]
    
    for err in errors:
        assert isinstance(err, ArticleError)
        assert hasattr(err, 'message')
        assert hasattr(err, 'fix_suggestion')
    
    print("  ✓ All errors inherit from ArticleError")


# === Slug Generation Tests ===

def test_generate_url_slug_basic():
    """Test basic slug generation."""
    assert generate_url_slug("001_test_article.mdx") == "test_article"
    assert generate_url_slug("042_spy_vs_spx.mdx") == "spy_vs_spx"
    assert generate_url_slug("105_options_trading.mdx") == "options_trading"
    print("  ✓ Basic slug generation")


def test_generate_url_slug_with_path():
    """Test slug generation with full path."""
    assert generate_url_slug("./content/001_test.mdx") == "test"
    assert generate_url_slug("/path/to/content/042_spy.mdx") == "spy"
    print("  ✓ Slug generation with paths")


def test_generate_url_slug_no_prefix():
    """Test slug generation without ID prefix."""
    assert generate_url_slug("test_article.mdx") == "test_article"
    print("  ✓ Slug generation without ID prefix")


# === DateManager Tests ===

def test_get_all_dates_empty():
    """Test getting dates from empty articles.json."""
    json_path = create_test_articles_json([])
    try:
        dm = DateManager(json_path)
        dates = dm.get_all_dates()
        assert dates == set()
        print("  ✓ get_all_dates with empty articles")
    finally:
        json_path.unlink()


def test_get_all_dates_with_articles():
    """Test getting dates from articles.json with articles."""
    articles = [
        {"id": 1, "published_date": "2026-02-25", "status": "published"},
        {"id": 2, "published_date": "2026-02-27", "status": "published"},
    ]
    json_path = create_test_articles_json(articles)
    try:
        dm = DateManager(json_path)
        dates = dm.get_all_dates()
        assert len(dates) == 2
        assert datetime(2026, 2, 25).date() in dates
        print("  ✓ get_all_dates with articles")
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
        print("  ✓ is_date_available")
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
        
        print("  ✓ get_available_slots with 2-day gaps")
    finally:
        json_path.unlink()


# === IntegrityChecker Tests ===

def test_check_duplicate_ids():
    """Test detection of duplicate IDs."""
    articles = [
        {"id": 1, "published_date": "2026-02-25", "url_slug": "article-1"},
        {"id": 1, "published_date": "2026-03-01", "url_slug": "article-2"},  # Duplicate ID
    ]
    json_path = create_test_articles_json(articles)
    try:
        checker = IntegrityChecker(json_path)
        issues = checker.check_all()
        assert any("Duplicate IDs" in issue for issue in issues)
        print("  ✓ Duplicate ID detection")
    finally:
        json_path.unlink()


def test_check_duplicate_dates():
    """Test detection of duplicate dates (future dates only)."""
    from datetime import datetime, timedelta
    
    # Use a date far in the future (definitely tomorrow+)
    future_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
    
    articles = [
        {"id": 1, "published_date": future_date, "url_slug": "article-1"},
        {"id": 2, "published_date": future_date, "url_slug": "article-2"},  # Same future date
    ]
    json_path = create_test_articles_json(articles)
    try:
        checker = IntegrityChecker(json_path)
        issues = checker.check_all()
        assert any(f"Date {future_date}" in issue for issue in issues)
        assert any("scheduling conflict" in issue for issue in issues)
        print("  ✓ Duplicate date detection (future dates)")
    finally:
        json_path.unlink()


def test_validate_new_article_valid():
    """Test validation of new article (valid case)."""
    articles = [
        {"id": 1, "published_date": "2026-02-25", "url_slug": "article-1"},
    ]
    json_path = create_test_articles_json(articles)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        content_dir = Path(tmpdir)
        try:
            checker = IntegrityChecker(json_path, content_dir)
            is_valid, error = checker.validate_new_article(
                "New Article", "2026-02-27", 2, content_dir
            )
            assert is_valid, f"Expected valid but got: {error}"
            print("  ✓ validate_new_article valid case")
        finally:
            json_path.unlink()


def test_validate_new_article_duplicate_id():
    """Test validation detects duplicate ID."""
    articles = [
        {"id": 1, "published_date": "2026-02-25", "url_slug": "article-1"},
    ]
    json_path = create_test_articles_json(articles)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        content_dir = Path(tmpdir)
        try:
            checker = IntegrityChecker(json_path, content_dir)
            is_valid, error = checker.validate_new_article(
                "New Article", "2026-02-27", 1, content_dir
            )
            assert not is_valid
            assert "ID 1 already exists" in error
            print("  ✓ Duplicate ID validation")
        finally:
            json_path.unlink()


# === ContentSync Tests ===

def test_build_filename():
    """Test filename building."""
    json_path = create_test_articles_json([])
    
    with tempfile.TemporaryDirectory() as tmpdir:
        content_dir = Path(tmpdir)
        sync = ContentSync(json_path, content_dir)
        
        assert sync.build_filename(1, "Test Article") == "001_test_article.mdx"
        assert sync.build_filename(42, "SPY vs SPX: Analysis!") == "042_spy_vs_spx_analysis.mdx"
        print("  ✓ build_filename")
    
    json_path.unlink()


def test_add_article_entry():
    """Test adding article entry to articles.json."""
    json_path = create_test_articles_json([])
    
    with tempfile.TemporaryDirectory() as tmpdir:
        content_dir = Path(tmpdir)
        sync = ContentSync(json_path, content_dir)
        
        result = sync.add_article_entry(
            article_id=1,
            title="Test Article",
            filename="001_test_article.mdx",
            publish_date="2026-02-25",
            word_count=500
        )
        
        assert result is True
        
        # Verify JSON was updated
        data = json.loads(json_path.read_text())
        assert len(data["articles"]) == 1
        assert data["articles"][0]["id"] == 1
        assert data["articles"][0]["url_slug"] == "test_article"
        print("  ✓ add_article_entry")
    
    json_path.unlink()


def test_sync_with_directory_add_new():
    """Test sync adds new content files."""
    articles = [
        {"id": 1, "published_date": "2026-02-25", "file": "./content/001_existing.mdx", "url_slug": "existing"}
    ]
    json_path = create_test_articles_json(articles)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        content_dir = Path(tmpdir)
        
        # Create existing file
        (content_dir / "001_existing.mdx").write_text("---\ntitle: Existing\ndate: 2026-02-25\n---\nContent")
        
        # Create new file (not in JSON)
        (content_dir / "002_new_article.mdx").write_text("---\ntitle: New Article\ndate: 2026-02-27\n---\nContent")
        
        sync = ContentSync(json_path, content_dir)
        result = sync.sync_with_directory(dry_run=False)
        
        assert len(result["added"]) == 1
        assert result["added"][0]["id"] == 2
        print("  ✓ sync_with_directory adds new files")
    
    json_path.unlink()


# === Main ===

def main():
    print("╔" + "═"*58 + "╗")
    print("║" + " "*18 + "DASHBOARD PTK TEST SUITE" + " "*18 + "║")
    print("╚" + "═"*58 + "╝\n")
    
    tests = [
        ("Error Types", [
            test_duplicate_id_error,
            test_duplicate_date_error,
            test_duplicate_slug_error,
            test_error_inheritance,
        ]),
        ("Slug Generation", [
            test_generate_url_slug_basic,
            test_generate_url_slug_with_path,
            test_generate_url_slug_no_prefix,
        ]),
        ("DateManager", [
            test_get_all_dates_empty,
            test_get_all_dates_with_articles,
            test_is_date_available,
            test_get_available_slots,
        ]),
        ("IntegrityChecker", [
            test_check_duplicate_ids,
            test_check_duplicate_dates,
            test_validate_new_article_valid,
            test_validate_new_article_duplicate_id,
        ]),
        ("ContentSync", [
            test_build_filename,
            test_add_article_entry,
            test_sync_with_directory_add_new,
        ]),
    ]
    
    total_passed = 0
    total_failed = 0
    
    for category, test_funcs in tests:
        print(f"\n{category}")
        print("-" * 40)
        for test_func in test_funcs:
            try:
                test_func()
                total_passed += 1
            except AssertionError as e:
                print(f"  ✗ {test_func.__name__}: {e}")
                total_failed += 1
            except Exception as e:
                print(f"  ✗ {test_func.__name__}: {type(e).__name__}: {e}")
                total_failed += 1
    
    print("\n" + "="*60)
    print(f"Total: {total_passed + total_failed} | Passed: {total_passed} | Failed: {total_failed}")
    print("="*60)
    
    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
