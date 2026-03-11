#!/usr/bin/env python3
"""
Test script for content cleaning functionality.
Tests validation (dry-run) mode only to avoid modifying actual files.
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from seo_content_mcp.content_cleaner import ContentCleaner, format_cleaning_result


def test_validate_content():
    """Test content validation (dry-run mode)"""
    
    from pathlib import Path
    workspace_root = str(Path(__file__).resolve().parents[2])
    cleaner = ContentCleaner(workspace_root)
    
    # Test with different websites
    websites = [
        "general/coffee",
        "general/days_to_expiry",
        "general/expense",
    ]
    
    print("🧪 Testing Content Validation (Dry-Run Mode)\n")
    print("=" * 80)
    
    for website_path in websites:
        try:
            print(f"\n{'=' * 80}")
            print(f"Testing: {website_path}")
            print('=' * 80)
            
            result = cleaner.clean_website(
                website_path=website_path,
                dry_run=True  # Don't modify files
            )
            
            output = format_cleaning_result(result)
            print(output)
            
        except FileNotFoundError as e:
            print(f"⚠️  Skipping {website_path}: {e}")
        except Exception as e:
            print(f"❌ Error testing {website_path}: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 80)
    print("✅ Validation tests completed!")
    print("\nNote: This was a dry-run. No files were modified.")
    print("To actually clean content, use: seo_clean_content tool")


if __name__ == "__main__":
    test_validate_content()
