#!/usr/bin/env python3
"""
Bootstrap scheduler state based on existing task history.

This prevents the scheduler from treating all rules as "due immediately"
when first set up. It looks at existing completed tasks and sets the
scheduler's last run times to match.
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add dashboard to path
sys.path.insert(0, str(Path(__file__).parent.parent / "dashboard_ptk"))

from dashboard.engine.scheduler_service import SchedulerService
from dashboard.engine.types import SchedulerState, RuleState


def find_last_task_completion(repo_root: Path, task_type: str) -> datetime | None:
    """Find when a task of this type was last completed."""
    task_list_path = repo_root / ".github" / "automation" / "task_list.json"
    
    if not task_list_path.exists():
        return None
    
    try:
        data = json.loads(task_list_path.read_text())
        tasks = data.get("tasks", [])
        
        # Find completed tasks of this type
        completed = [
            t for t in tasks 
            if t.get("type") == task_type and t.get("status") == "done"
        ]
        
        if not completed:
            return None
        
        # Get the most recent completion
        latest = None
        for task in completed:
            completed_at = task.get("completed_at") or task.get("metadata", {}).get("completed_at")
            if completed_at:
                try:
                    dt = datetime.fromisoformat(completed_at.replace("Z", "+00:00").replace("+00:00", ""))
                    if latest is None or dt > latest:
                        latest = dt
                except:
                    pass
        
        return latest
        
    except Exception as e:
        print(f"  Warning: Could not read task list: {e}")
        return None


def bootstrap_project(repo_root: Path, website_id: str, dry_run: bool = True):
    """Bootstrap scheduler state for a single project."""
    print(f"\n📁 {website_id}")
    
    # Load policy to get rules
    policy_path = repo_root / ".github" / "automation" / "orchestrator_policy.json"
    if not policy_path.exists():
        print(f"  ⚠ No policy file found")
        return
    
    try:
        policy = json.loads(policy_path.read_text())
        rules = policy.get("scheduler", {}).get("rules", [])
    except Exception as e:
        print(f"  ⚠ Could not read policy: {e}")
        return
    
    if not rules:
        print(f"  ℹ No scheduler rules configured")
        return
    
    # Load or create scheduler state
    state_path = repo_root / ".github" / "automation" / "scheduler_state.json"
    
    if state_path.exists():
        try:
            state = SchedulerState.from_dict(json.loads(state_path.read_text()))
            print(f"  ℹ Existing state found ({state.stats.cycles} previous cycles)")
        except:
            state = SchedulerState()
            print(f"  ℹ Creating new state (existing was invalid)")
    else:
        state = SchedulerState()
        print(f"  ℹ Creating new state")
    
    # For each rule, set last run based on task history
    updated = 0
    for rule in rules:
        rule_id = rule.get("id")
        task_type = rule.get("task_type")
        cadence_hours = rule.get("cadence_hours", 168)
        
        # Check if we already have state for this rule
        existing = state.rules.get(rule_id)
        if existing and existing.last_task_created_at:
            print(f"  ✓ {rule_id}: Already has state, skipping")
            continue
        
        # Find last completion of this task type
        last_completion = find_last_task_completion(repo_root, task_type)
        
        if last_completion:
            # Set the last run to the completion time
            if not dry_run:
                rule_state = RuleState()
                rule_state.last_task_created_at = last_completion.isoformat()
                rule_state.last_due_at = last_completion.isoformat()
                rule_state.last_status = "created"
                rule_state.last_message = f"Bootstrapped from task history"
                state.rules[rule_id] = rule_state
            
            # Calculate next due
            next_due = last_completion + timedelta(hours=cadence_hours)
            is_overdue = datetime.now() > next_due
            
            status = "⚠ OVERDUE" if is_overdue else "✓ OK"
            print(f"  {status} {rule_id}: Last run {last_completion.date()}, next due {next_due.date()}")
            updated += 1
        else:
            # No history found - set to now minus half cadence so it's not immediately due
            fake_last_run = datetime.now() - timedelta(hours=cadence_hours / 2)
            
            if not dry_run:
                rule_state = RuleState()
                rule_state.last_task_created_at = fake_last_run.isoformat()
                rule_state.last_due_at = fake_last_run.isoformat()
                rule_state.last_status = "skipped"
                rule_state.last_message = f"Bootstrapped (no task history found)"
                state.rules[rule_id] = rule_state
            
            next_due = fake_last_run + timedelta(hours=cadence_hours)
            print(f"  ℹ {rule_id}: No history found, setting last run to ~{cadence_hours//2}h ago, next due {next_due.date()}")
            updated += 1
    
    if updated > 0 and not dry_run:
        # Save the state
        state.last_cycle_started_at = datetime.now().isoformat()
        state.last_cycle_finished_at = datetime.now().isoformat()
        state.stats.cycles = 0  # Don't count bootstrap as a cycle
        
        state_path.write_text(json.dumps(state.to_dict(), indent=2))
        print(f"  ✓ Saved state ({updated} rules updated)")
    elif updated > 0:
        print(f"  → Would update {updated} rules (dry run, use --apply to save)")
    else:
        print(f"  ✓ All rules already have state")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Bootstrap scheduler state from existing task history"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually save the changes (default is dry-run)"
    )
    parser.add_argument(
        "--project",
        help="Specific project website_id to bootstrap (default: all)"
    )
    
    args = parser.parse_args()
    
    # Load projects
    projects_config = Path.home() / ".config" / "automation" / "projects.json"
    
    if not projects_config.exists():
        print(f"❌ Projects config not found: {projects_config}")
        sys.exit(1)
    
    with open(projects_config) as f:
        data = json.load(f)
        projects = data.get("projects", [])
    
    if args.project:
        projects = [p for p in projects if p.get("website_id") == args.project]
        if not projects:
            print(f"❌ Project '{args.project}' not found")
            sys.exit(1)
    
    print("=" * 60)
    print("Scheduler State Bootstrap")
    print("=" * 60)
    print(f"\nFound {len(projects)} project(s)")
    
    if not args.apply:
        print("\n⚠ DRY RUN MODE - No changes will be saved")
        print("   Use --apply to actually save the state\n")
    else:
        print("\n📝 APPLY MODE - Will save changes to scheduler_state.json\n")
    
    for project in projects:
        website_id = project.get("website_id")
        repo_root = Path(project.get("repo_root", "")).expanduser()
        
        if not repo_root.exists():
            print(f"\n⚠ {website_id}: Repo not found at {repo_root}")
            continue
        
        bootstrap_project(repo_root, website_id, dry_run=not args.apply)
    
    print("\n" + "=" * 60)
    if args.apply:
        print("✅ Bootstrap complete!")
        print("\nThe scheduler now knows when tasks were last run.")
        print("Run the scheduler manually to verify:")
        print("  cd dashboard_ptk && python main.py --scheduled-cycle")
    else:
        print("📝 Dry run complete - no changes saved")
        print("\nTo apply these changes, run with --apply:")
        print("  python scripts/bootstrap_scheduler_state.py --apply")
    print("=" * 60)


if __name__ == "__main__":
    main()
