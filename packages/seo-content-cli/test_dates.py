#!/usr/bin/env python3
"""
Test script for date distribution functionality.
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from seo_content_mcp.date_distributor import DateDistributor, format_date_analysis, format_date_fix


def test_date_analysis():
    """Test date analysis on actual websites"""
    
    from pathlib import Path
    workspace_root = str(Path(__file__).resolve().parents[2])
    distributor = DateDistributor(workspace_root)
    
    websites = [
        "general/coffee",
        "general/days_to_expiry",
        "general/expense",
        "general/examplesite",
    ]
    
    print("🧪 Testing Date Analysis\n")
    print("=" * 80)
    
    for website_path in websites:
        try:
            print(f"\n{'=' * 80}")
            print(f"Analyzing: {website_path}")
            print('=' * 80)
            
            result = distributor.analyze_dates(website_path=website_path)
            
            output = format_date_analysis(result)
            print(output)
            
            # If issues found, show what would be fixed
            if result.has_issues():
                print("\n" + "-" * 80)
                print("Preview of fixes (dry-run):")
                print("-" * 80)
                
                fix_result = distributor.fix_dates(
                    website_path=website_path,
                    dry_run=True
                )
                
                fix_output = format_date_fix(fix_result, dry_run=True)
                print(fix_output)
            
        except FileNotFoundError as e:
            print(f"⚠️  Skipping {website_path}: {e}")
        except Exception as e:
            print(f"❌ Error analyzing {website_path}: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 80)
    print("✅ Date analysis tests completed!")
    print("\nNote: This was analysis only. No files were modified.")
    print("To actually fix dates, use: seo_fix_dates tool")


if __name__ == "__main__":
    test_date_analysis()
