#!/usr/bin/env python3
"""Quick scheduler status check - run this anytime to see what's happening."""
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

def check_launchd_agents():
    """Check if launchd agents are loaded."""
    print("Launchd Agents:")
    result = subprocess.run(['launchctl', 'list'], capture_output=True, text=True)
    output = result.stdout
    
    if 'com.pageseeds.scheduler.cycle' in output:
        print("  ✓ Scheduler cycle agent loaded")
    else:
        print("  ✗ Scheduler cycle agent NOT loaded")
    
    if 'com.pageseeds.scheduler.health' in output:
        print("  ✓ Health check agent loaded")
    else:
        print("  ✗ Health check agent NOT loaded")
    print()

def check_global_status(root_dir: Path):
    """Check global scheduler status."""
    status_file = root_dir / "output" / "monitoring" / "seo_scheduler" / "status.json"
    
    print("Global Status:")
    if not status_file.exists():
        print("  ⚠ No status file found (scheduler hasn't run yet)")
        return
    
    try:
        status = json.loads(status_file.read_text())
        
        result = status.get('last_result', 'unknown')
        emoji = {'ok': '✓', 'warn': '⚠', 'error': '✗', 'running': '⋯'}.get(result, '?')
        
        print(f"  Last result: {emoji} {result.upper()}")
        print(f"  Last run: {status.get('last_finished_at', 'never')}")
        print(f"  Duration: {status.get('last_duration_sec', 0)}s")
        print(f"  Projects: {status.get('project_count', 0)}")
        
        if status.get('due_count', 0) > 0:
            print(f"  Due rules: {status.get('due_count', 0)}")
        if status.get('overdue_count', 0) > 0:
            print(f"  ⚠ Overdue: {status.get('overdue_count', 0)}")
        if status.get('manual_attention_count', 0) > 0:
            print(f"  Need attention: {status.get('manual_attention_count', 0)}")
        
        if status.get('last_error'):
            print(f"  ✗ Error: {status['last_error'][:80]}")
        
        runs = status.get('runs', {})
        if runs:
            print(f"  Total runs: {runs.get('total', 0)} (ok: {runs.get('successes', 0)}, failed: {runs.get('failures', 0)})")
    except Exception as e:
        print(f"  ✗ Error reading status: {e}")
    print()

def check_project_statuses(root_dir: Path):
    """Check per-project status."""
    projects_dir = root_dir / "output" / "monitoring" / "seo_scheduler" / "projects"
    
    print("Per-Project Status:")
    if not projects_dir.exists():
        print("  No project status files yet")
        return
    
    files = sorted(projects_dir.glob("*.json"))
    if not files:
        print("  No project status files yet")
        return
    
    for f in files:
        try:
            data = json.loads(f.read_text())
            website_id = data.get('website_id', f.stem)
            
            # Count due rules
            due_rules = [r for r in data.get('due_rules', []) if r.get('is_due')]
            attention = data.get('attention_summary', {})
            
            status_parts = []
            if due_rules:
                status_parts.append(f"{len(due_rules)} due")
            if attention.get('overdue_rules_error', 0) > 0:
                status_parts.append(f"⚠ {attention['overdue_rules_error']} critical")
            elif attention.get('overdue_rules_warn', 0) > 0:
                status_parts.append(f"⚠ {attention['overdue_rules_warn']} overdue")
            
            total_attention = attention.get('total_attention_needed', 0)
            if total_attention > 0:
                status_parts.append(f"{total_attention} need attention")
            
            status_str = ', '.join(status_parts) if status_parts else 'all good'
            
            print(f"  {website_id}: {status_str}")
            
            top = data.get('top_priority')
            if top:
                print(f"    -> {top}")
        except Exception as e:
            print(f"  {f.stem}: error reading status")
    print()

def check_history(root_dir: Path):
    """Check recent run history."""
    history_file = root_dir / "output" / "monitoring" / "seo_scheduler" / "history.log"
    
    print("Recent Run History:")
    if not history_file.exists():
        print("  No history yet")
        return
    
    try:
        lines = history_file.read_text().strip().split('\n')
        for line in lines[-5:]:
            print(f"  {line}")
    except Exception as e:
        print(f"  Error reading history: {e}")
    print()

def show_commands():
    """Show helpful commands."""
    print("Commands:")
    print("  View full logs:     tail -f /tmp/com.pageseeds.scheduler.cycle.out.log")
    print("  View errors:        tail -f /tmp/com.pageseeds.scheduler.cycle.err.log")
    print("  Run manually:       cd dashboard_ptk && python main.py --scheduled-cycle")
    print("  Dashboard:          cd dashboard_ptk && python main.py -> 's'")
    print()

def main():
    script_dir = Path(__file__).parent
    root_dir = script_dir.parent
    
    print("=" * 50)
    print("Scheduler Status")
    print("=" * 50)
    print()
    
    check_launchd_agents()
    check_global_status(root_dir)
    check_project_statuses(root_dir)
    check_history(root_dir)
    show_commands()

if __name__ == "__main__":
    main()
