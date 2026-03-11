"""
Tests for IntegrityChecker.
"""
import sys
import os
import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from dashboard.utils.integrity_checker import IntegrityChecker
from dashboard.utils.errors import (
    DuplicateIdError,
    DuplicateDateError,
    DuplicateSlugError,
    FileExistsError,
    ArticlesJsonError,
    IntegrityError,
)


def create_test_articles_json(articles=None):
    """Create a temporary articles.json file."""
    data = {
        "articles": articles or [],
        "nextArticleId": 1
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(data, f)
        return Path(f.name)


def test_check_all_empty():
    """Test integrity check on empty articles.json."""
    json_path = create_test_articles_json([])
    try:
        checker = IntegrityChecker(json_path)
        issues = checker.check_all()
        assert issues == []
        print("✓ check_all with empty articles")
    finally:
        json_path.unlink()


def test_check_duplicate_ids():
    """Test detection of duplicate IDs."""
    articles = [
        {"id": 1, "published_date": "2026-02-25", "url_slug": "article-1"},
        {"id": 2, "published_date": "2026-02-27", "url_slug": "article-2"},
        {"id": 1, "published_date": "2026-03-01", "url_slug": "article-3"},  # Duplicate ID
    ]
    json_path = create_test_articles_json(articles)
    try:
        checker = IntegrityChecker(json_path)
        issues = checker.check_all()
        
        assert len(issues) >= 1
        assert any("Duplicate IDs" in issue for issue in issues)
        print("✓ Duplicate ID detection")
    finally:
        json_path.unlink()


def test_check_duplicate_dates():
    """Test detection of duplicate dates."""
    future_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
    articles = [
        {"id": 1, "published_date": future_date, "url_slug": "article-1"},
        {"id": 2, "published_date": future_date, "url_slug": "article-2"},  # Same future date
    ]
    json_path = create_test_articles_json(articles)
    try:
        checker = IntegrityChecker(json_path)
        issues = checker.check_all()
        
        assert len(issues) >= 1
        assert any(f"Date {future_date}" in issue for issue in issues)
        print("✓ Duplicate date detection")
    finally:
        json_path.unlink()


def test_check_next_id():
    """Test detection of incorrect nextArticleId."""
    articles = [
        {"id": 1, "published_date": "2026-02-25", "url_slug": "article-1"},
        {"id": 2, "published_date": "2026-02-27", "url_slug": "article-2"},
    ]
    data = {
        "articles": articles,
        "nextArticleId": 5  # Should be 3
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(data, f)
        json_path = Path(f.name)
    
    try:
        checker = IntegrityChecker(json_path)
        issues = checker.check_all()
        
        assert len(issues) >= 1
        assert any("nextArticleId" in issue for issue in issues)
        print("✓ nextArticleId check")
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
            assert error == ""
            print("✓ validate_new_article valid case")
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
            
            # Return mode
            is_valid, error = checker.validate_new_article(
                "New Article", "2026-02-27", 1, content_dir
            )
            assert not is_valid
            assert "ID 1 already exists" in error
            
            # Raise mode
            try:
                checker.validate_new_article(
                    "New Article", "2026-02-27", 1, content_dir, raise_on_error=True
                )
                assert False, "Should have raised DuplicateIdError"
            except DuplicateIdError as e:
                assert e.article_id == 1
            
            print("✓ Duplicate ID validation")
        finally:
            json_path.unlink()


def test_validate_new_article_duplicate_date():
    """Test validation detects duplicate date."""
    articles = [
        {"id": 1, "published_date": "2026-02-25", "url_slug": "article-1"},
    ]
    json_path = create_test_articles_json(articles)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        content_dir = Path(tmpdir)
        try:
            checker = IntegrityChecker(json_path, content_dir)
            
            is_valid, error = checker.validate_new_article(
                "New Article", "2026-02-25", 2, content_dir
            )
            assert not is_valid
            assert "already taken" in error
            print("✓ Duplicate date validation")
        finally:
            json_path.unlink()


def test_validate_new_article_file_exists():
    """Test validation detects existing file."""
    articles = [
        {"id": 1, "published_date": "2026-02-25", "url_slug": "article-1"},
    ]
    json_path = create_test_articles_json(articles)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        content_dir = Path(tmpdir)
        # Create existing file
        (content_dir / "002_new_article.mdx").write_text("exists")
        
        try:
            checker = IntegrityChecker(json_path, content_dir)
            
            is_valid, error = checker.validate_new_article(
                "New Article", "2026-02-27", 2, content_dir
            )
            assert not is_valid
            assert "already exists" in error
            print("✓ File exists validation")
        finally:
            json_path.unlink()


def test_check_all_raise_on_error():
    """Test check_all with raise_on_error."""
    articles = [
        {"id": 1, "published_date": "2026-02-25", "url_slug": "article-1"},
        {"id": 1, "published_date": "2026-02-27", "url_slug": "article-2"},  # Duplicate
    ]
    json_path = create_test_articles_json(articles)
    try:
        checker = IntegrityChecker(json_path)
        
        try:
            checker.check_all(raise_on_error=True)
            assert False, "Should have raised IntegrityError"
        except IntegrityError as e:
            assert len(e.issues) >= 1
            print("✓ check_all with raise_on_error")
    finally:
        json_path.unlink()


if __name__ == "__main__":
    print("=== Testing IntegrityChecker ===\n")
    test_check_all_empty()
    test_check_duplicate_ids()
    test_check_duplicate_dates()
    test_check_next_id()
    test_validate_new_article_valid()
    test_validate_new_article_duplicate_id()
    test_validate_new_article_duplicate_date()
    test_validate_new_article_file_exists()
    test_check_all_raise_on_error()
    print("\n=== All IntegrityChecker Tests Passed ===")
