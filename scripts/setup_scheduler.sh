#!/usr/bin/env zsh
set -e

# SEO Scheduler Setup Script
# This script helps initialize the scheduler for a project

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DASHBOARD_DIR="$ROOT_DIR/dashboard_ptk"

echo "=== SEO Scheduler Setup ==="
echo ""

# Check prerequisites
echo "Checking prerequisites..."

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found"
    exit 1
fi
echo "✓ Python 3 found"

# Check CLIs
for cli in pageseeds; do
    if command -v $cli &> /dev/null; then
        echo "✓ $cli found"
    else
        echo "⚠ $cli not found (install with: uv tool install $cli)"
    fi
done

# Check projects config
PROJECTS_CONFIG="$HOME/.config/automation/projects.json"
if [[ ! -f "$PROJECTS_CONFIG" ]]; then
    echo ""
    echo "❌ Projects config not found: $PROJECTS_CONFIG"
    echo ""
    echo "Create it with content like:"
    cat <<'EOF'
{
  "projects": [
    {
      "name": "My Website",
      "website_id": "my_site",
      "repo_root": "/path/to/repo"
    }
  ]
}
EOF
    exit 1
fi
echo "✓ Projects config found"

# Count projects
PROJECT_COUNT=$(python3 -c "
import json
with open('$PROJECTS_CONFIG') as f:
    data = json.load(f)
    print(len(data.get('projects', [])))
" 2>/dev/null || echo "0")

echo "  Found $PROJECT_COUNT project(s)"
echo ""

# Check if running in a project repo
CURRENT_DIR="$(pwd)"
if [[ -d "$CURRENT_DIR/.github/automation" ]]; then
    echo "Detected automation directory in current directory"
    REPO_ROOT="$CURRENT_DIR"
    
    # Try to find website_id from manifest or articles.json
    WEBSITE_ID=$(python3 -c "
import json
from pathlib import Path

# Try manifest.json
manifest = Path('$REPO_ROOT/.github/automation/manifest.json')
if manifest.exists():
    try:
        data = json.loads(manifest.read_text())
        print(data.get('website_id', ''))
    except:
        pass

# Fallback to articles.json
articles = Path('$REPO_ROOT/.github/automation/articles.json')
if articles.exists():
    try:
        data = json.loads(articles.read_text())
        print(data.get('website_id', ''))
    except:
        pass
" 2>/dev/null)
    
    if [[ -n "$WEBSITE_ID" ]]; then
        echo "Detected website_id: $WEBSITE_ID"
    fi
fi

echo ""
echo "=== Setup Options ==="
echo ""
echo "1. Check all projects for scheduler readiness"
echo "2. Initialize scheduler for current project ($WEBSITE_ID)"
echo "3. Install launchd agents (automatic scheduling)"
echo "4. Install SwiftBar plugin"
echo "5. Run scheduler test (dry run)"
echo "q. Quit"
echo ""

read "choice?Choice: "

case "$choice" in
    1)
        echo ""
        echo "Checking all projects..."
        cd "$DASHBOARD_DIR"
        python3 -c "
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path('$DASHBOARD_DIR')))

from dashboard.engine.preflight import ProjectPreflight

config_path = Path('$PROJECTS_CONFIG')
with open(config_path) as f:
    data = json.load(f)
    projects = data.get('projects', [])

print(f'Checking {len(projects)} project(s)...\n')

for project in projects:
    name = project.get('name', 'Unknown')
    website_id = project.get('website_id', '')
    repo_root = project.get('repo_root', '')
    
    print(f'📁 {name} ({website_id})')
    
    if not repo_root:
        print('   ❌ No repo_root configured')
        continue
    
    repo_path = Path(repo_root).expanduser()
    if not repo_path.exists():
        print(f'   ❌ Repo root does not exist: {repo_root}')
        continue
    
    # Run preflight
    preflight = ProjectPreflight(repo_path, website_id)
    report = preflight.run()
    
    if report.is_ready:
        print('   ✓ Preflight passed')
    else:
        print(f'   ⚠ Preflight issues: {len(report.errors)} errors, {len(report.warnings)} warnings')
    
    # Check for scheduler state file
    scheduler_state = repo_path / '.github' / 'automation' / 'scheduler_state.json'
    if scheduler_state.exists():
        print('   ✓ Scheduler state file exists')
    else:
        print('   ℹ No scheduler state yet (will be created on first run)')
    
    print()
"
        ;;
    
    2)
        if [[ -z "$REPO_ROOT" ]]; then
            echo "❌ Not in a project directory (no .github/automation found)"
            exit 1
        fi
        
        echo ""
        echo "Initializing scheduler for $WEBSITE_ID..."
        
        # Check/create orchestrator_policy.json
        POLICY_FILE="$REPO_ROOT/.github/automation/orchestrator_policy.json"
        if [[ -f "$POLICY_FILE" ]]; then
            echo "✓ Policy file exists: $POLICY_FILE"
            
            # Check if it has scheduler section
            HAS_SCHEDULER=$(python3 -c "
import json
with open('$POLICY_FILE') as f:
    data = json.load(f)
    print('scheduler' in data)
")
            if [[ "$HAS_SCHEDULER" == "False" ]]; then
                echo "ℹ Policy missing scheduler section, will use defaults"
                read "add_scheduler?Add default scheduler config? (y/n): "
                if [[ "$add_scheduler" == "y" ]]; then
                    python3 -c "
import json
with open('$POLICY_FILE') as f:
    data = json.load(f)

data['scheduler'] = {
    'enabled': True,
    'timezone': '',
    'max_task_creations_per_cycle': 3,
    'quiet_hours_start': '22:00',
    'quiet_hours_end': '07:00',
    'overdue_warn_after_hours': 48,
    'overdue_error_after_hours': 168,
    'rules': [
        {'id': 'collect_gsc_weekly', 'task_type': 'collect_gsc', 'mode': 'create_task', 'cadence_hours': 168, 'priority': 'medium', 'phase': 'collection', 'enabled': True},
        {'id': 'collect_posthog_weekly', 'task_type': 'collect_posthog', 'mode': 'create_task', 'cadence_hours': 168, 'priority': 'medium', 'phase': 'collection', 'enabled': True},
        {'id': 'reddit_opportunity_search', 'task_type': 'reddit_opportunity_search', 'mode': 'create_task', 'cadence_hours': 48, 'priority': 'medium', 'phase': 'research', 'enabled': True},
        {'id': 'research_keywords', 'task_type': 'research_keywords', 'mode': 'reminder_only', 'cadence_hours': 336, 'priority': 'medium', 'phase': 'research', 'enabled': True},
        {'id': 'indexing_diagnostics', 'task_type': 'indexing_diagnostics', 'mode': 'reminder_only', 'cadence_hours': 168, 'priority': 'medium', 'phase': 'diagnostics', 'enabled': True}
    ]
}

with open('$POLICY_FILE', 'w') as f:
    json.dump(data, f, indent=2)
print('✓ Added scheduler configuration')
"
                fi
            else
                echo "✓ Scheduler section already exists"
            fi
        else
            echo "Creating policy file with default scheduler config..."
            mkdir -p "$(dirname "$POLICY_FILE")"
            cat > "$POLICY_FILE" <<'EOF'
{
  "schema_version": 1,
  "max_steps_per_run": 8,
  "max_failures_per_run": 2,
  "allow_modes": ["automatic", "batchable"],
  "blocked_task_types": ["research_keywords", "custom_keyword_research"],
  "allowed_task_types": [],
  "reddit_autopost_enabled": false,
  "reddit_max_posts_per_day": 4,
  "reddit_max_posts_per_week": 12,
  "stop_on_policy_block": false,
  "scheduler": {
    "enabled": true,
    "timezone": "",
    "max_task_creations_per_cycle": 3,
    "quiet_hours_start": "22:00",
    "quiet_hours_end": "07:00",
    "overdue_warn_after_hours": 48,
    "overdue_error_after_hours": 168,
    "rules": [
      {"id": "collect_gsc_weekly", "task_type": "collect_gsc", "mode": "create_task", "cadence_hours": 168, "priority": "medium", "phase": "collection", "enabled": true},
      {"id": "collect_posthog_weekly", "task_type": "collect_posthog", "mode": "create_task", "cadence_hours": 168, "priority": "medium", "phase": "collection", "enabled": true},
      {"id": "reddit_opportunity_search", "task_type": "reddit_opportunity_search", "mode": "create_task", "cadence_hours": 48, "priority": "medium", "phase": "research", "enabled": true},
      {"id": "research_keywords", "task_type": "research_keywords", "mode": "reminder_only", "cadence_hours": 336, "priority": "medium", "phase": "research", "enabled": true},
      {"id": "indexing_diagnostics", "task_type": "indexing_diagnostics", "mode": "reminder_only", "cadence_hours": 168, "priority": "medium", "phase": "diagnostics", "enabled": true}
    ]
  }
}
EOF
            echo "✓ Created policy file"
        fi
        
        # Check gitignore
        GITIGNORE="$REPO_ROOT/.gitignore"
        if [[ -f "$GITIGNORE" ]]; then
            if grep -q ".github/automation/" "$GITIGNORE"; then
                echo "✓ .gitignore excludes automation data"
            else
                echo "⚠ .gitignore does not exclude .github/automation/"
                read "fix_gitignore?Add to .gitignore? (y/n): "
                if [[ "$fix_gitignore" == "y" ]]; then
                    echo "" >> "$GITIGNORE"
                    echo "# Automation data - do not commit" >> "$GITIGNORE"
                    echo ".github/automation/" >> "$GITIGNORE"
                    echo "✓ Updated .gitignore"
                fi
            fi
        else
            echo "ℹ No .gitignore found"
        fi
        
        echo ""
        echo "✓ Scheduler initialized for $WEBSITE_ID"
        echo ""
        echo "Next steps:"
        echo "  1. Review/edit scheduler config: python main.py → 's' → Option 1"
        echo "  2. Test manually: python main.py --scheduled-cycle --project $WEBSITE_ID"
        echo "  3. Install launchd agents: Option 3 in this script"
        ;;
    
    3)
        echo ""
        echo "Installing launchd agents..."
        zsh "$ROOT_DIR/swiftbar/launchd/install.sh"
        echo ""
        echo "✓ Launch agents installed"
        echo ""
        echo "The scheduler will now run automatically every 30 minutes"
        echo "View logs: tail -f /tmp/com.pageseeds.scheduler.cycle.out.log"
        ;;
    
    4)
        echo ""
        echo "Installing SwiftBar plugin..."
        zsh "$ROOT_DIR/swiftbar/install_plugin.sh"
        ;;
    
    5)
        echo ""
        read "test_project?Enter website_id to test (or 'all'): "
        
        if [[ "$test_project" == "all" ]]; then
            echo "Running scheduler test for all projects..."
            cd "$DASHBOARD_DIR"
            python3 main.py --scheduled-cycle
        elif [[ -n "$test_project" ]]; then
            echo "Running scheduler test for $test_project..."
            cd "$DASHBOARD_DIR"
            python3 main.py --scheduled-cycle --project "$test_project"
        else
            echo "❌ No project specified"
        fi
        ;;
    
    q)
        echo "Goodbye!"
        exit 0
        ;;
    
    *)
        echo "Invalid choice"
        exit 1
        ;;
esac

echo ""
echo "Done!"
