#!/usr/bin/env python3
"""
Create test content with issues to demonstrate cleaning functionality.
"""

import os
import tempfile
import shutil
import json

def create_test_website():
    """Create a temporary test website with issues"""
    
    # Create temp directory
    test_dir = tempfile.mkdtemp(prefix="seo_test_")
    content_dir = os.path.join(test_dir, "content")
    os.makedirs(content_dir)
    
    # Create articles.json
    articles_data = {
        "articles": [
            {
                "id": 1,
                "title": "Best Coffee Beans",
                "file": "./content/01_best-coffee-beans.md",
                "published_date": "2025-10-25"
            },
            {
                "id": 2,
                "title": "Coffee Storage Tips",
                "file": "./content/02_coffee-storage-tips.md",
                "published_date": "2025-10-26"
            }
        ]
    }
    
    with open(os.path.join(test_dir, "articles.json"), 'w') as f:
        json.dump(articles_data, f, indent=2)
    
    # Create markdown file with duplicate title heading
    md_content_1 = '''---
title: "Best Coffee Beans"
date: "2025-10-20"
summary: "Guide to choosing the best coffee beans"
slug: "best-coffee-beans"
---

# Best Coffee Beans

This article talks about the best coffee beans you can buy.

## Types of Coffee Beans

There are many types of coffee beans available.
'''
    
    with open(os.path.join(content_dir, "01_best-coffee-beans.md"), 'w') as f:
        f.write(md_content_1)
    
    # Create markdown file with date mismatch
    md_content_2 = '''---
title: "Coffee Storage Tips"
date: "2025-10-15"
summary: "How to store coffee properly"
slug: "coffee-storage-tips"
---

Learn how to store your coffee to keep it fresh.

## Storage Methods

Keep coffee in an airtight container.
'''
    
    with open(os.path.join(content_dir, "02_coffee-storage-tips.md"), 'w') as f:
        f.write(md_content_2)
    
    return test_dir


def test_cleaning_with_issues():
    """Test cleaning functionality with actual issues"""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
    
    from seo_content_mcp.content_cleaner import ContentCleaner, format_cleaning_result
    
    # Create test website
    test_dir = create_test_website()
    
    print("🧪 Testing Content Cleaning with Issues\n")
    print("=" * 80)
    print(f"Test directory: {test_dir}")
    print("=" * 80)
    
    try:
        # Create cleaner with test directory as workspace
        cleaner = ContentCleaner(workspace_root=os.path.dirname(test_dir))
        website_path = os.path.basename(test_dir)
        
        # First, validate (dry-run)
        print("\n1️⃣  VALIDATION (Dry-Run)")
        print("-" * 80)
        result_validation = cleaner.clean_website(
            website_path=website_path,
            dry_run=True
        )
        print(format_cleaning_result(result_validation))
        
        # Then, actually clean
        print("\n2️⃣  CLEANING (Making Changes)")
        print("-" * 80)
        result_clean = cleaner.clean_website(
            website_path=website_path,
            dry_run=False
        )
        print(format_cleaning_result(result_clean))
        
        # Validate again to confirm fixes
        print("\n3️⃣  RE-VALIDATION (After Cleaning)")
        print("-" * 80)
        result_revalidation = cleaner.clean_website(
            website_path=website_path,
            dry_run=True
        )
        print(format_cleaning_result(result_revalidation))
        
        # Show fixed content
        print("\n4️⃣  FIXED CONTENT PREVIEW")
        print("-" * 80)
        
        file1 = os.path.join(test_dir, "content", "01_best-coffee-beans.md")
        with open(file1, 'r') as f:
            content = f.read()
        
        print(f"\n📄 {os.path.basename(file1)}:")
        print(content[:300] + "...")
        
        file2 = os.path.join(test_dir, "content", "02_coffee-storage-tips.md")
        with open(file2, 'r') as f:
            content = f.read()
        
        print(f"\n📄 {os.path.basename(file2)}:")
        print(content[:300] + "...")
        
    finally:
        # Cleanup
        print(f"\n🗑️  Cleaning up test directory: {test_dir}")
        shutil.rmtree(test_dir)
    
    print("\n✅ Test completed successfully!")


if __name__ == "__main__":
    test_cleaning_with_issues()
