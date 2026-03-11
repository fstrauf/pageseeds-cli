#!/usr/bin/env zsh
set -e

# SEO Scheduler Auto-Setup Script
# Non-interactive setup - "just do it"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DASHBOARD_DIR="$ROOT_DIR/dashboard_ptk"

echo "=== SEO Scheduler Auto-Setup ==="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_success() { echo "${GREEN}✓${NC} $1"; }
log_warn() { echo "${YELLOW}⚠${NC} $1"; }
log_error() { echo "${RED}✗${NC} $1"; }

# Check prerequisites
echo "Checking prerequisites..."

if ! command -v python3 &> /dev/null; then
    log_error "Python 3 not found"
    exit 1
fi
log_success "Python 3 found"

for cli in automation-cli seo-cli seo-content-cli; do
    if command -v $cli &> /dev/null; then
        log_success "$cli found"
    else
        log_warn "$cli not found (install with: uv tool install $cli)"
    fi
done

# Check projects config
PROJECTS_CONFIG="$HOME/.config/automation/projects.json"
if [[ ! -f "$PROJECTS_CONFIG" ]]; then
    log_error "Projects config not found: $PROJECTS_CONFIG"
    echo ""
    echo "Create it first with your projects:"
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
log_success "Projects config found"

# Count projects
PROJECT_COUNT=$(python3 -c "
import json
with open('$PROJECTS_CONFIG') as f:
    data = json.load(f)
    print(len(data.get('projects', [])))
" 2>/dev/null || echo "0")

log_success "Found $PROJECT_COUNT project(s)"
echo ""

# Initialize scheduler for all projects
echo "Initializing scheduler for all projects..."

python3 <<PY
import json
import sys
from pathlib import Path

sys.path.insert(0, '$DASHBOARD_DIR')

config_path = Path('$PROJECTS_CONFIG')
with open(config_path) as f:
    data = json.load(f)
    projects = data.get('projects', [])

for project in projects:
    name = project.get('name', 'Unknown')
    website_id = project.get('website_id', '')
    repo_root = project.get('repo_root', '')
    
    if not repo_root or not website_id:
        print(f"⚠ Skipping {name}: missing repo_root or website_id")
        continue
    
    repo_path = Path(repo_root).expanduser()
    if not repo_path.exists():
        print(f"⚠ Skipping {name}: repo not found")
        continue
    
    # Ensure automation directory exists
    auto_dir = repo_path / '.github' / 'automation'
    auto_dir.mkdir(parents=True, exist_ok=True)
    
    # Check/create policy file
    policy_file = auto_dir / 'orchestrator_policy.json'
    
    if policy_file.exists():
        try:
            with open(policy_file) as f:
                policy = json.load(f)
            
            if 'scheduler' not in policy:
                # Add scheduler section
                policy['scheduler'] = {
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
                with open(policy_file, 'w') as f:
                    json.dump(policy, f, indent=2)
                print(f"✓ {name}: Added scheduler to existing policy")
            else:
                print(f"✓ {name}: Scheduler already configured")
        except Exception as e:
            print(f"⚠ {name}: Error updating policy - {e}")
    else:
        # Create new policy file with scheduler
        policy = {
            'schema_version': 1,
            'max_steps_per_run': 8,
            'max_failures_per_run': 2,
            'allow_modes': ['automatic', 'batchable'],
            'blocked_task_types': ['research_keywords', 'custom_keyword_research'],
            'allowed_task_types': [],
            'reddit_autopost_enabled': False,
            'reddit_max_posts_per_day': 4,
            'reddit_max_posts_per_week': 12,
            'stop_on_policy_block': False,
            'scheduler': {
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
        }
        with open(policy_file, 'w') as f:
            json.dump(policy, f, indent=2)
        print(f"✓ {name}: Created policy with scheduler config")
    
    # Check/fix gitignore
    gitignore = repo_path / '.gitignore'
    if gitignore.exists():
        try:
            content = gitignore.read_text()
            if '.github/automation/' not in content:
                with open(gitignore, 'a') as f:
                    if not content.endswith('\n'):
                        f.write('\n')
                    f.write('\n# Automation data - do not commit\n.github/automation/\n')
                print(f"  → Added .gitignore exclusion")
        except:
            pass

PY

echo ""

# Install launchd agents
echo "Installing launchd agents..."
zsh "$ROOT_DIR/swiftbar/launchd/install.sh" > /tmp/scheduler_launchd_install.log 2>&1
if [[ $? -eq 0 ]]; then
    log_success "Launch agents installed"
else
    log_error "Launch agent installation failed"
    cat /tmp/scheduler_launchd_install.log
    exit 1
fi

echo ""

# Verify installation
echo "Verifying installation..."

sleep 1

if launchctl list | grep -q "com.pageseeds.scheduler"; then
    log_success "Scheduler agents loaded"
else
    log_warn "Scheduler agents may not be loaded yet"
fi

echo ""
echo "==================================="
echo "${GREEN}✓ Scheduler Auto-Setup Complete!${NC}"
echo "==================================="
echo ""
echo "The scheduler will now run automatically every 30 minutes"
echo ""
echo "Monitor it:"
echo "  • SwiftBar menu bar icon"
echo "  • CLI: python main.py → 's' → View Global Scheduler Status"
echo "  • Logs: tail -f /tmp/com.pageseeds.scheduler.cycle.out.log"
echo ""
echo "Test it now:"
echo "  cd dashboard_ptk && python main.py --scheduled-cycle"
echo ""
