"""
Tests for ContentSync.
"""
import sys
import os
import json
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from dashboard.utils.content_sync import ContentSync
from dashboard.utils.errors import ArticlesJsonError, ContentNotFoundError


def create_test_articles_json(articles=None):
    """Create a temporary articles.json file."""
    data = {
        "articles": articles or [],
        "nextArticleId": 1,
        "statistics": {"total_articles": 0, "last_updated": "2026-01-01"}
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(data, f)
        return Path(f.name)


def test_build_filename():
    """Test filename building."""
    json_path = create_test_articles_json([])
    
    with tempfile.TemporaryDirectory() as tmpdir:
        content_dir = Path(tmpdir)
        sync = ContentSync(json_path, content_dir)
        
        # Test basic filename
        filename = sync.build_filename(1, "Test Article")
        assert filename == "001_test_article.mdx"
        
        # Test with special chars
        filename = sync.build_filename(42, "SPY vs SPX: Analysis!")
        assert filename == "042_spy_vs_spx_analysis.mdx"
        
        # Test with multiple spaces
        filename = sync.build_filename(105, "Options  Trading  Strategy")
        assert filename == "105_options_trading_strategy.mdx"
        
        print("✓ build_filename")
    
    json_path.unlink()


def test_extract_frontmatter():
    """Test frontmatter extraction."""
    json_path = create_test_articles_json([])
    
    with tempfile.TemporaryDirectory() as tmpdir:
        content_dir = Path(tmpdir)
        sync = ContentSync(json_path, content_dir)
        
        # Create test file with frontmatter
        content = """---
title: "Test Article"
date: "2026-02-25"
description: "A test article"
---

# Content here
"""
        test_file = content_dir / "test.mdx"
        test_file.write_text(content)
        
        title, date, desc = sync.extract_frontmatter(test_file)
        assert title == "Test Article"
        assert date == "2026-02-25"
        assert desc == "A test article"
        
        print("✓ extract_frontmatter")
    
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
        assert data["articles"][0]["title"] == "Test Article"
        assert data["articles"][0]["url_slug"] == "test_article"
        assert data["articles"][0]["status"] == "draft"
        
        print("✓ add_article_entry")
    
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
        
        # Verify JSON was updated
        data = json.loads(json_path.read_text())
        assert len(data["articles"]) == 2
        
        print("✓ sync_with_directory adds new files")
    
    json_path.unlink()


def test_sync_with_directory_remove_orphaned():
    """Test sync removes orphaned entries."""
    articles = [
        {"id": 1, "published_date": "2026-02-25", "file": "./content/001_existing.mdx", "url_slug": "existing"},
        {"id": 2, "published_date": "2026-02-27", "file": "./content/002_missing.mdx", "url_slug": "missing"}
    ]
    json_path = create_test_articles_json(articles)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        content_dir = Path(tmpdir)
        
        # Only create first file
        (content_dir / "001_existing.mdx").write_text("---\ntitle: Existing\ndate: 2026-02-25\n---\nContent")
        
        sync = ContentSync(json_path, content_dir)
        result = sync.sync_with_directory(dry_run=False)
        
        assert len(result["removed"]) == 1
        assert result["removed"][0]["id"] == 2
        
        # Verify JSON was updated
        data = json.loads(json_path.read_text())
        assert len(data["articles"]) == 1
        
        print("✓ sync_with_directory removes orphaned entries")
    
    json_path.unlink()


def test_sync_dry_run():
    """Test dry run doesn't modify files."""
    articles = []
    json_path = create_test_articles_json(articles)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        content_dir = Path(tmpdir)
        (content_dir / "001_new.mdx").write_text("---\ntitle: New\ndate: 2026-02-25\n---\nContent")
        
        sync = ContentSync(json_path, content_dir)
        result = sync.sync_with_directory(dry_run=True)
        
        # Should report changes but not make them
        assert len(result["added"]) == 1
        
        # Verify JSON was NOT updated
        data = json.loads(json_path.read_text())
        assert len(data["articles"]) == 0
        
        print("✓ sync dry_run")
    
    json_path.unlink()


if __name__ == "__main__":
    print("=== Testing ContentSync ===\n")
    test_build_filename()
    test_extract_frontmatter()
    test_add_article_entry()
    test_sync_with_directory_add_new()
    test_sync_with_directory_remove_orphaned()
    test_sync_dry_run()
    print("\n=== All ContentSync Tests Passed ===")
