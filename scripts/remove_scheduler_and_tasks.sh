#!/usr/bin/env zsh
# Remove SEO Scheduler AND all scheduled tasks

set -e

echo "=== SEO Scheduler & Tasks Removal ==="
echo ""
echo "WARNING: This will remove:"
echo "  1. All scheduler configuration"
echo "  2. All tasks created by the scheduler"
echo "  3. Automatic scheduling"
echo ""
echo "Your manually created tasks will be preserved."
echo ""

read "confirm?Type 'remove everything' to proceed: "
if [[ "$confirm" != "remove everything" ]]; then
    echo "Cancelled."
    exit 0
fi

echo ""
echo "Starting removal..."

# 1. Stop and remove launchd agents
echo ""
echo "1. Stopping launchd agents..."
launchctl bootout gui/$UID/com.pageseeds.scheduler.cycle 2>/dev/null || true
launchctl bootout gui/$UID/com.pageseeds.scheduler.health 2>/dev/null || true
rm -f ~/Library/LaunchAgents/com.pageseeds.scheduler.*.plist
echo "   ✓ Launch agents removed"

# 2. Remove scheduler tasks and config from all projects
echo ""
echo "2. Processing projects..."

python3 << 'PYTHON_SCRIPT'
import json
from pathlib import Path

projects_config = Path.home() / ".config" / "automation" / "projects.json"

if not projects_config.exists():
    print("   No projects config found")
    exit(0)

with open(projects_config) as f:
    data = json.load(f)
    projects = data.get("projects", [])

for project in projects:
    website_id = project.get("website_id")
    repo_root = Path(project.get("repo_root", "")).expanduser()
    
    print(f"\n   📁 {website_id}")
    
    # Process task list to remove scheduled tasks
    task_list_path = repo_root / ".github" / "automation" / "task_list.json"
    tasks_removed = 0
    
    if task_list_path.exists():
        try:
            with open(task_list_path) as f:
                task_data = json.load(f)
            
            original_count = len(task_data.get("tasks", []))
            
            # Filter out tasks created by scheduler
            remaining_tasks = []
            for task in task_data.get("tasks", []):
                metadata = task.get("metadata", {})
                created_by = metadata.get("created_by", "")
                
                if created_by == "scheduler":
                    tasks_removed += 1
                    print(f"      - Removing: {task.get('title', task.get('id', 'unknown'))} [{task.get('status', 'unknown')}]")
                else:
                    remaining_tasks.append(task)
            
            if tasks_removed > 0:
                task_data["tasks"] = remaining_tasks
                task_data["last_updated"] = Path(__file__).stat().st_mtime
                
                with open(task_list_path, "w") as f:
                    json.dump(task_data, f, indent=2)
                print(f"      ✓ Removed {tasks_removed} scheduled task(s)")
            else:
                print(f"      (No scheduled tasks found)")
                
        except Exception as e:
            print(f"      ⚠ Error processing task list: {e}")
    else:
        print(f"      (No task list found)")
    
    # Remove scheduler section from policy
    policy_file = repo_root / ".github" / "automation" / "orchestrator_policy.json"
    if policy_file.exists():
        try:
            with open(policy_file) as f:
                policy = json.load(f)
            
            if "scheduler" in policy:
                del policy["scheduler"]
                with open(policy_file, "w") as f:
                    json.dump(policy, f, indent=2)
                print(f"      ✓ Removed scheduler from policy")
        except Exception as e:
            print(f"      ⚠ Could not update policy: {e}")
    
    # Remove scheduler state file
    state_file = repo_root / ".github" / "automation" / "scheduler_state.json"
    if state_file.exists():
        try:
            state_file.unlink()
            print(f"      ✓ Removed scheduler state")
        except Exception as e:
            print(f"      ⚠ Could not remove state: {e}")

PYTHON_SCRIPT

# 3. Remove monitoring files
echo ""
echo "3. Removing monitoring files..."
automation_root="${0:A:h:h}"
monitor_dir="$automation_root/output/monitoring/seo_scheduler"
if [[ -d "$monitor_dir" ]]; then
    rm -rf "$monitor_dir"
    echo "   ✓ Removed monitoring directory"
else
    echo "   (No monitoring files found)"
fi

# 4. Remove SwiftBar integration
echo ""
echo "4. Removing SwiftBar integration..."
swiftbar_jobs="$automation_root/swiftbar/jobs/seo_scheduler"
if [[ -d "$swiftbar_jobs" ]]; then
    rm -rf "$swiftbar_jobs"
    echo "   ✓ Removed SwiftBar job scripts"
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
print("   ✓ Removed from jobs.json")
PYTHON_SCRIPT
fi

# 5. Clean up scheduler code files (optional)
echo ""
read "remove_code?Remove scheduler code files too? (yes/no): "
if [[ "$remove_code" == "yes" ]]; then
    echo "   Removing scheduler code..."
    
    # Remove scheduler service
    rm -f "$automation_root/dashboard_ptk/dashboard/engine/scheduler_service.py"
    echo "   ✓ Removed scheduler_service.py"
    
    # Remove scheduler CLI
    rm -f "$automation_root/dashboard_ptk/dashboard/scheduler_cli.py"
    echo "   ✓ Removed scheduler_cli.py"
    
    # Remove scheduler types from types.py (this is harder, just leave them)
    echo "   ℹ Scheduler types left in types.py (harmless)"
    
    # Remove scheduler tests
    rm -f "$automation_root/dashboard_ptk/tests/test_scheduler_*.py"
    echo "   ✓ Removed scheduler tests"
    
    # Remove scripts
    rm -f "$automation_root/scripts/setup_scheduler.sh"
    rm -f "$automation_root/scripts/setup_scheduler_auto.sh"
    rm -f "$automation_root/scripts/bootstrap_scheduler_state.py"
    rm -f "$automation_root/scripts/scheduler_status.py"
    rm -f "$automation_root/scripts/scheduler_status.sh"
    rm -f "$automation_root/scripts/remove_scheduler.sh"
    echo "   ✓ Removed scheduler scripts"
    
    # Revert main.py changes
    python3 - "$automation_root/dashboard_ptk/main.py" << 'PYTHON_SCRIPT'
import sys
from pathlib import Path

main_path = Path(sys.argv[1])
content = main_path.read_text()

# Remove scheduled-cycle argument handling
# This is a simplified revert - just remove the scheduled cycle function
if "def run_scheduled_cycle" in content:
    print("   ℹ main.py has scheduler code - manual cleanup needed")
else:
    print("   ℹ main.py already clean")
PYTHON_SCRIPT
    
    # Revert cli.py changes
    python3 - "$automation_root/dashboard_ptk/dashboard/cli.py" << 'PYTHON_SCRIPT'
import sys
from pathlib import Path

cli_path = Path(sys.argv[1])
content = cli_path.read_text()

if "SchedulerCLI" in content:
    print("   ℹ cli.py has scheduler code - manual cleanup needed")
else:
    print("   ℹ cli.py already clean")
PYTHON_SCRIPT
    
    echo ""
    echo "   NOTE: Some code changes require manual cleanup in:"
    echo "     - dashboard_ptk/main.py"
    echo "     - dashboard_ptk/dashboard/cli.py"
    echo "     - dashboard_ptk/dashboard/engine/__init__.py"
    echo "     - dashboard_ptk/dashboard/engine/types.py"
fi

# 6. Remove documentation
echo ""
read "remove_docs?Remove scheduler documentation? (yes/no): "
if [[ "$remove_docs" == "yes" ]]; then
    rm -f "$automation_root/SCHEDULER_SETUP.md"
    rm -f "$automation_root/SCHEDULER_QUICKREF.md"
    rm -f "$automation_root/SCHEDULER_IMPLEMENTATION_SUMMARY.md"
    rm -f "$automation_root/SCHEDULER_MONITORING.md"
    echo "   ✓ Removed documentation"
fi

echo ""
echo "==================================="
echo "✓ Scheduler completely removed"
echo "==================================="
echo ""
echo "Summary:"
echo "  • Automatic scheduling stopped"
echo "  • Scheduled tasks deleted"
echo "  • Configuration removed from all projects"
echo "  • Your manual tasks are preserved"
echo ""
echo "If you want to restore the scheduler later:"
echo "  git checkout -- scripts/setup_scheduler_auto.sh"
echo "  zsh scripts/setup_scheduler_auto.sh"
echo ""
