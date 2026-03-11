#!/usr/bin/env python3
"""
Setup gitignore to exclude automation data from git commits.
This prevents task files, artifacts, and secrets from being committed.
"""
import sys
from pathlib import Path


def setup_gitignore(repo_root: str | None = None) -> bool:
    """Add automation exclusions to .gitignore if not present.
    
    Args:
        repo_root: Path to git repository root. If None, uses current directory.
        
    Returns:
        True if gitignore was modified or already correct, False on error.
    """
    if repo_root is None:
        repo_root = "."
    
    repo_path = Path(repo_root).resolve()
    gitignore_path = repo_path / ".gitignore"
    
    # Entries to add
    automation_entries = [
        "# Automation data - do not commit",
        ".github/automation/",
    ]
    
    try:
        # Read existing content
        if gitignore_path.exists():
            content = gitignore_path.read_text()
            # Check if already configured
            if ".github/automation/" in content:
                print(f"✓ .gitignore already excludes automation data")
                return True
        else:
            content = ""
        
        # Append automation entries
        with open(gitignore_path, "a") as f:
            # Add newline if file doesn't end with one
            if content and not content.endswith("\n"):
                f.write("\n")
            # Add separator if file has content
            if content:
                f.write("\n")
            for entry in automation_entries:
                f.write(f"{entry}\n")
        
        print(f"✓ Added automation exclusions to {gitignore_path}")
        print(f"  - .github/automation/")
        return True
        
    except IOError as e:
        print(f"✗ Error updating .gitignore: {e}", file=sys.stderr)
        return False


if __name__ == "__main__":
    # Try to find repo root from command line or use current directory
    repo_root = sys.argv[1] if len(sys.argv) > 1 else "."
    success = setup_gitignore(repo_root)
    sys.exit(0 if success else 1)
