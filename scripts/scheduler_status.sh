#!/usr/bin/env zsh
# Quick scheduler status check - run this anytime to see what's happening

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)

echo "=== Scheduler Status ==="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Check launchd agents
echo "Launchd Agents:"
if launchctl list | grep -q "com.pageseeds.scheduler.cycle"; then
    echo "  ${GREEN}✓${NC} Scheduler cycle agent loaded"
else
    echo "  ${RED}✗${NC} Scheduler cycle agent NOT loaded"
fi

if launchctl list | grep -q "com.pageseeds.scheduler.health"; then
    echo "  ${GREEN}✓${NC} Health check agent loaded"
else
    echo "  ${RED}✗${NC} Health check agent NOT loaded"
fi
echo ""

# Check global status
STATUS_FILE="$ROOT_DIR/output/monitoring/seo_scheduler/status.json"
if [[ -f "$STATUS_FILE" ]]; then
    echo "Global Status:"
    
    # Use Python to parse and display status
    python3 - "$STATUS_FILE" << 'PYTHON_SCRIPT'
import json
import sys
from pathlib import Path

status_path = Path(sys.argv[1])
status = json.loads(status_path.read_text())

result = status.get('last_result', 'unknown')
result_emoji = {'ok': '✓', 'warn': '⚠', 'error': '✗', 'running': '⋯'}.get(result, '?')

print(f"  Last result: {result_emoji} {result.upper()}")
print(f"  Last run: {status.get('last_finished_at', 'never')}")
print(f"  Duration: {status.get('last_duration_sec', 0)}s")
print(f"  Projects: {status.get('project_count', 0)}")

if status.get('due_count', 0) > 0:
    print(f"  Due rules: {status.get('due_count', 0)}")
if status.get('overdue_count', 0) > 0:
    print(f"  ! Overdue: {status.get('overdue_count', 0)}")
if status.get('manual_attention_count', 0) > 0:
    print(f"  Need attention: {status.get('manual_attention_count', 0)}")

if status.get('last_error'):
    print(f"  ! Error: {status['last_error'][:80]}")

runs = status.get('runs', {})
if runs:
    print(f"  Total runs: {runs.get('total', 0)} (ok: {runs.get('successes', 0)}, failed: {runs.get('failures', 0)})")
PYTHON_SCRIPT
    
else
    echo "Global Status:"
    echo "  ${YELLOW}⚠${NC} No status file found (scheduler hasn't run yet)"
fi
echo ""

# Check per-project status
echo "Per-Project Status:"
PROJECTS_DIR="$ROOT_DIR/output/monitoring/seo_scheduler/projects"
if [[ -d "$PROJECTS_DIR" ]]; then
    python3 - "$PROJECTS_DIR" << 'PYTHON_SCRIPT'
import json
import sys
from pathlib import Path

projects_dir = Path(sys.argv[1])
files = list(projects_dir.glob('*.json'))

if not files:
    print("  No project status files yet")
else:
    for f in sorted(files):
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
                status_parts.append(f"! {attention['overdue_rules_error']} critical")
            elif attention.get('overdue_rules_warn', 0) > 0:
                status_parts.append(f"! {attention['overdue_rules_warn']} overdue")
            
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
PYTHON_SCRIPT
else
    echo "  No project statuses yet"
fi
echo ""

# Recent history
HISTORY_FILE="$ROOT_DIR/output/monitoring/seo_scheduler/history.log"
if [[ -f "$HISTORY_FILE" ]]; then
    echo "Recent Run History:"
    tail -5 "$HISTORY_FILE" | while read line; do
        echo "  $line"
    done
else
    echo "Run History:"
    echo "  No history yet"
fi
echo ""

# Show helpful commands
echo "Commands:"
echo "  View full logs:     tail -f /tmp/com.pageseeds.scheduler.cycle.out.log"
echo "  View errors:        tail -f /tmp/com.pageseeds.scheduler.cycle.err.log"
echo "  Run manually:       cd dashboard_ptk && python main.py --scheduled-cycle"
echo "  Dashboard:          cd dashboard_ptk && python main.py -> 's'"
echo ""
