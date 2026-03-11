"""
Tests for URL slug generation.
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from dashboard.utils.article_manager_refactored import generate_url_slug


def test_generate_url_slug_basic():
    """Test basic slug generation."""
    assert generate_url_slug("001_test_article.mdx") == "test_article"
    assert generate_url_slug("042_spy_vs_spx.mdx") == "spy_vs_spx"
    assert generate_url_slug("105_options_trading.mdx") == "options_trading"
    print("✓ Basic slug generation")


def test_generate_url_slug_with_path():
    """Test slug generation with full path."""
    assert generate_url_slug("./content/001_test.mdx") == "test"
    assert generate_url_slug("/path/to/content/042_spy.mdx") == "spy"
    print("✓ Slug generation with paths")


def test_generate_url_slug_no_prefix():
    """Test slug generation without ID prefix."""
    assert generate_url_slug("test_article.mdx") == "test_article"
    assert generate_url_slug("spy_vs_spx.mdx") == "spy_vs_spx"
    print("✓ Slug generation without ID prefix")


def test_generate_url_slug_md_extension():
    """Test slug generation with .md extension."""
    assert generate_url_slug("001_test.md") == "test"
    assert generate_url_slug("042_article.md") == "article"
    print("✓ Slug generation with .md extension")


def test_generate_url_slug_special_chars():
    """Test slug generation preserves underscores."""
    assert generate_url_slug("001_spy_vs_spx_analysis.mdx") == "spy_vs_spx_analysis"
    assert generate_url_slug("001_multiple_words_here.mdx") == "multiple_words_here"
    print("✓ Slug generation preserves underscores")


def test_generate_url_slug_large_id():
    """Test slug generation with large ID numbers."""
    assert generate_url_slug("123_test.mdx") == "test"
    assert generate_url_slug("9999_large_id.mdx") == "large_id"
    assert generate_url_slug("0001_leading_zeros.mdx") == "leading_zeros"
    print("✓ Slug generation with large IDs")


def test_consistency_with_filename():
    """Test that slug is consistent with ContentSync.build_filename."""
    # Simulate what ContentSync does
    import re
    article_id = 42
    title = "SPY vs SPX Analysis"
    
    # Build filename (from ContentSync)
    slug = re.sub(r'[^\w\s-]', '', title).strip().lower()
    slug = re.sub(r'[-\s]+', '_', slug)
    filename = f"{article_id:03d}_{slug}.mdx"
    
    # Generate URL slug
    url_slug = generate_url_slug(filename)
    
    # They should match
    assert url_slug == "spy_vs_spx_analysis"
    assert url_slug == slug
    
    print("✓ Consistency between filename and URL slug")


if __name__ == "__main__":
    print("=== Testing URL Slug Generation ===\n")
    test_generate_url_slug_basic()
    test_generate_url_slug_with_path()
    test_generate_url_slug_no_prefix()
    test_generate_url_slug_md_extension()
    test_generate_url_slug_special_chars()
    test_generate_url_slug_large_id()
    test_consistency_with_filename()
    print("\n=== All Slug Tests Passed ===")
