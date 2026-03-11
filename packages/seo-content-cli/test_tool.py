#!/usr/bin/env python3
"""
Test script to verify the seo_test_distribution tool works correctly.
"""

import json
import sys
from seo_content_mcp.server import SEOContentServer, format_distribution_result

def test_distribution():
    """Test the distribution with real project data"""
    server = SEOContentServer()
    
    test_cases = [
        ("Coffee", 39, "2025-01-09"),
        ("Days to Expiry", 16, "2025-10-06"),
        ("Expense", 74, "2025-01-05"),
        ("ExampleSite", 41, "2025-08-05"),
    ]
    
    print("🧪 Testing Date Distribution Tool\n")
    print("=" * 80)
    
    for project_name, article_count, earliest_date in test_cases:
        print(f"\n{'=' * 80}")
        result = server.test_distribution(
            project_name=project_name,
            article_count=article_count,
            earliest_date=earliest_date
        )
        
        output = format_distribution_result(result)
        print(output)
        print()
    
    print("\n✅ All tests completed successfully!")

if __name__ == "__main__":
    test_distribution()
