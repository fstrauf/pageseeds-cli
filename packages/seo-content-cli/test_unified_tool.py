#!/usr/bin/env python3
"""
Quick test of the new seo_ops_sync_and_optimize tool
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from seo_content_mcp.seo_ops import SEOOps

def test_sync_and_optimize():
    """Test the unified workflow tool"""
    from pathlib import Path
    workspace_root = str(Path(__file__).resolve().parents[2])
    seo_ops = SEOOps(workspace_root)
    
    # Get days_to_expiry site
    site = seo_ops.get_site_by_id("days_to_expiry")
    
    if not site:
        print("❌ Could not find days_to_expiry in registry")
        return False
    
    print("✓ Found site:", site.get("name"))
    
    # Test preview mode (dry_run=True)
    print("\n🧪 Testing preview mode...")
    result = seo_ops.sync_and_optimize(
        site=site,
        auto_fix=False,
        spacing_days=2,
        max_recent_days=7,
        dry_run=True
    )
    
    if not result.get("ok"):
        print("❌ Preview mode failed")
        print("Error:", result.get("error"))
        return False
    
    print(f"✓ Mode: {result.get('mode')}")
    print(f"✓ Website: {result.get('website_id')}")
    
    # Check phases
    phases = result.get("phases", {})
    print(f"\n📊 Phases executed: {len(phases)}")
    for phase_name, phase_data in phases.items():
        status = phase_data.get("status", "unknown")
        emoji = "✓" if status == "completed" else "⊘" if status == "skipped" else "○" if status == "preview" else "✗"
        print(f"  {emoji} {phase_name}: {status}")
    
    # Check summary
    summary = result.get("summary", {})
    print(f"\n📈 Summary:")
    print(f"  • Articles in sync: {summary.get('articles_in_sync')}")
    print(f"  • Date issues found: {summary.get('date_issues_found')}")
    print(f"  • Files ready to push: {summary.get('files_ready_to_push')}")
    print(f"  • Validation errors: {summary.get('validation_errors')}")
    
    # Check recommendations
    recommendations = result.get("recommended_actions", [])
    if recommendations:
        print(f"\n💡 Recommendations:")
        for rec in recommendations:
            print(f"  • {rec}")
    
    print(f"\n🎯 Next action: {summary.get('next_action')}")
    
    print("\n✅ Test completed successfully!")
    return True

if __name__ == "__main__":
    try:
        success = test_sync_and_optimize()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
