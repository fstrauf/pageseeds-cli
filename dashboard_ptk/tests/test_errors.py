"""
Tests for error types.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../dashboard/utils'))

from errors import (
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


def test_duplicate_id_error():
    """Test DuplicateIdError."""
    err = DuplicateIdError(105)
    assert err.article_id == 105
    assert "105" in err.message
    assert "already exists" in err.message
    assert len(err.fix_suggestion) > 0
    print("✓ DuplicateIdError")


def test_duplicate_date_error():
    """Test DuplicateDateError."""
    err = DuplicateDateError("2026-02-25", 42)
    assert err.date == "2026-02-25"
    assert err.existing_id == 42
    assert "2026-02-25" in err.message
    assert "42" in err.message
    print("✓ DuplicateDateError")


def test_duplicate_slug_error():
    """Test DuplicateSlugError."""
    err = DuplicateSlugError("spy_vs_spx")
    assert err.slug == "spy_vs_spx"
    assert "spy_vs_spx" in err.message
    print("✓ DuplicateSlugError")


def test_file_exists_error():
    """Test FileExistsError."""
    err = FileExistsError("content/105_test.mdx")
    assert err.filepath == "content/105_test.mdx"
    assert "content/105_test.mdx" in err.message
    print("✓ FileExistsError")


def test_articles_json_error():
    """Test ArticlesJsonError."""
    err = ArticlesJsonError("Invalid JSON at line 5")
    assert "Invalid JSON" in err.reason
    assert "Invalid JSON at line 5" in err.message
    print("✓ ArticlesJsonError")


def test_integrity_error():
    """Test IntegrityError."""
    issues = ["Duplicate ID 105", "Missing file for ID 42"]
    err = IntegrityError(issues)
    assert err.issues == issues
    assert "2 issue(s) found" in err.message
    print("✓ IntegrityError")


def test_date_allocation_error():
    """Test DateAllocationError."""
    err = DateAllocationError("No dates available in next 60 days")
    assert "No dates available" in err.reason
    assert "No dates available in next 60 days" in err.message
    print("✓ DateAllocationError")


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
    
    print("✓ All errors inherit from ArticleError")


def test_error_str_format():
    """Test error string formatting includes fix suggestion."""
    err = DuplicateIdError(105)
    str_repr = str(err)
    assert err.message in str_repr
    assert "→" in str_repr or err.fix_suggestion in str_repr
    print("✓ Error string includes fix suggestion")


if __name__ == "__main__":
    print("=== Testing Error Types ===\n")
    test_duplicate_id_error()
    test_duplicate_date_error()
    test_duplicate_slug_error()
    test_file_exists_error()
    test_articles_json_error()
    test_integrity_error()
    test_date_allocation_error()
    test_error_inheritance()
    test_error_str_format()
    print("\n=== All Error Tests Passed ===")
