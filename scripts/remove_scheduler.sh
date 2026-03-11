#!/usr/bin/env zsh
# Remove SEO Scheduler completely

set -e

echo "=== SEO Scheduler Removal ==="
echo ""

read "confirm?This will remove all scheduler configuration. Continue? (yes/no): "
if [[ "$confirm" != "yes" ]]; then
    echo "Cancelled."
    exit 0
fi

echo ""
echo "Removing scheduler..."

# 1. Stop and remove launchd agents
echo "Stopping launchd agents..."
launchctl bootout gui/$UID/com.pageseeds.scheduler.cycle 2>/dev/null || true
launchctl bootout gui/$UID/com.pageseeds.scheduler.health 2>/dev/null || true
rm -f ~/Library/LaunchAgents/com.pageseeds.scheduler.*.plist
echo "  ✓ Launch agents removed"

# 2. Remove scheduler section from all project policies
echo ""
echo "Removing scheduler config from projects..."

python3 << 'PYTHON_SCRIPT'
import json
from pathlib import Path

projects_config = Path.home() / ".config" / "automation" / "projects.json"

if not projects_config.exists():
    print("  No projects config found")
    exit(0)

with open(projects_config) as f:
    data = json.load(f)
    projects = data.get("projects", [])

removed_count = 0
for project in projects:
    website_id = project.get("website_id")
    repo_root = Path(project.get("repo_root", "")).expanduser()
    
    policy_file = repo_root / ".github" / "automation" / "orchestrator_policy.json"
    state_file = repo_root / ".github" / "automation" / "scheduler_state.json"
    
    # Remove scheduler section from policy
    if policy_file.exists():
        try:
            with open(policy_file) as f:
                policy = json.load(f)
            
            if "scheduler" in policy:
                del policy["scheduler"]
                with open(policy_file, "w") as f:
                    json.dump(policy, f, indent=2)
                print(f"  ✓ {website_id}: Removed scheduler from policy")
                removed_count += 1
        except Exception as e:
            print(f"  ⚠ {website_id}: Could not update policy - {e}")
    
    # Remove scheduler state file
    if state_file.exists():
        try:
            state_file.unlink()
            print(f"  ✓ {website_id}: Removed scheduler state")
        except Exception as e:
            print(f"  ⚠ {website_id}: Could not remove state - {e}")

if removed_count == 0:
    print("  (No scheduler configs found in projects)")

PYTHON_SCRIPT

# 3. Remove monitoring files
echo ""
echo "Removing monitoring files..."
automation_root="${0:A:h:h}"
monitor_dir="$automation_root/output/monitoring/seo_scheduler"
if [[ -d "$monitor_dir" ]]; then
    rm -rf "$monitor_dir"
    echo "  ✓ Removed $monitor_dir"
else
    echo "  (No monitoring files found)"
fi

# 4. Remove SwiftBar job scripts (optional)
echo ""
read "remove_swiftbar?Remove SwiftBar integration too? (yes/no): "
if [[ "$remove_swiftbar" == "yes" ]]; then
    swiftbar_jobs="$automation_root/swiftbar/jobs/seo_scheduler"
    if [[ -d "$swiftbar_jobs" ]]; then
        rm -rf "$swiftbar_jobs"
        echo "  ✓ Removed SwiftBar job scripts"
    fi
    
    # Update jobs.json to remove seo_scheduler entry
    jobs_file="$automation_root/swiftbar/jobs.json"
    if [[ -f "$jobs_file" ]]; then
        python3 - "$jobs_file" << 'PYTHON_SCRIPT'
import json
import sys
from pathlib import Path

jobs_path = Path(sys.argv[1])
with open(jobs_path) as f:
    data = json.load(f)

data["jobs"] = [j for j in data.get("jobs", []) if j.get("id") != "seo_scheduler"]

with open(jobs_path, "w") as f:
    json.dump(data, f, indent=2)
print("  ✓ Removed from jobs.json")
PYTHON_SCRIPT
    fi
else
    echo "  (Keeping SwiftBar integration)"
fi

echo ""
echo "==================================="
echo "✓ Scheduler removed successfully"
echo "==================================="
echo ""
echo "Your task lists, articles, and project data are unchanged."
echo ""
echo "What was removed:"
echo "  • Launchd agents (automatic scheduling)"
echo "  • Scheduler config from orchestrator_policy.json"
echo "  • Scheduler state files (timestamps only)"
echo "  • Monitoring/status files"
echo ""
echo "If you want to use the scheduler again in the future:"
echo "  zsh scripts/setup_scheduler_auto.sh"
echo ""
