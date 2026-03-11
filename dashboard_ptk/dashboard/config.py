"""
Configuration constants and paths

All automation data lives in the target repo's .github/automation/ directory.
The dashboard_ptk code is designed to work from any repo that has the automation
payload installed via `automation-cli repo install`.
"""
import os
from pathlib import Path


def get_repo_root() -> Path:
    """Get the current repository root (from environment or cwd)."""
    # For CLI usage, paths are resolved relative to the target repo root
    # The REPO_ROOT env var can be set to override
    if repo_root_env := os.environ.get("REPO_ROOT"):
        return Path(repo_root_env).expanduser().resolve()
    return Path.cwd().resolve()


def get_automation_dir(repo_root: Path | None = None) -> Path:
    """Get the automation directory for a repo (default: .github/automation/)."""
    root = repo_root or get_repo_root()
    return root / ".github" / "automation"


# Legacy compatibility - these are deprecated, use get_automation_dir() instead
AUTOMATION_ROOT = get_repo_root()
CLI_DIR = Path(__file__).parent.parent.parent / "packages" / "automation-cli"
USER_CONFIG_DIR = Path.home() / ".config/automation"
PROJECTS_CONFIG = USER_CONFIG_DIR / "projects.json"
WEBSITES_REGISTRY = get_repo_root() / "WEBSITES_REGISTRY.json"

# Task phases in order
PHASES = ["collection", "investigation", "research", "implementation", "verification"]

# Task type to execution mode mapping
EXECUTION_MODE_MAP = {
    # Direct content tasks - agent writes immediately
    "write_article": "direct",
    "optimize_article": "direct",
    "create_content": "direct",
    "optimize_content": "direct",
    
    # Spec tasks - need specification first
    "content_strategy": "spec",
    "technical_fix": "spec",
    "fix_technical": "spec",
    "fix_content": "spec",
    
    # Workflow tasks - run specific method
    "cluster_and_link": "workflow",
    "content_cleanup": "workflow",
    "publish_content": "workflow",
    "indexing_diagnostics": "workflow",
    
    # Collection tasks
    "collect_gsc": "workflow",
    "collect_posthog": "workflow",
    "investigate_gsc": "workflow",
    "investigate_posthog": "workflow",
    "research_keywords": "workflow",
    "custom_keyword_research": "workflow",
    "research_landing_pages": "workflow",
    "analyze_gsc_performance": "workflow",
    
    # Reddit tasks
    "reddit_opportunity_search": "workflow",
    "reddit_search": "automatic",
    "reddit_reply": "manual",
    
    # Fix tasks - agent decides
    "fix_indexing": "auto",
    
    # Landing page tasks
    "landing_page_spec": "spec",
}

# Task type to autonomy mode mapping (for batch processing)
AUTONOMY_MODE_MAP = {
    # Fully automatic - no human intervention needed
    "collect_gsc": "automatic",
    "collect_posthog": "automatic",
    "investigate_gsc": "automatic",
    "investigate_posthog": "automatic",
    "research_keywords": "automatic",
    "custom_keyword_research": "automatic",
    "research_landing_pages": "automatic",
    "analyze_gsc_performance": "automatic",
    "reddit_search": "automatic",
    "cluster_and_link": "automatic",
    "content_cleanup": "automatic",
    
    # Batchable - can process multiple but may need review
    "write_article": "batchable",
    "optimize_article": "batchable",
    "create_content": "batchable",
    "optimize_content": "batchable",
    "reddit_reply": "batchable",
    
    # Spec tasks - pause for human review/implementation
    "content_strategy": "spec",
    "technical_fix": "spec",
    "fix_technical": "spec",
    "fix_content": "spec",
    "landing_page_spec": "spec",
    
    # Manual - needs human decision
    "fix_indexing": "manual",
    "publish_content": "manual",
    "indexing_diagnostics": "manual",
}

# Project code mapping (examples)
PROJECT_CODE_MAP = {
    "coffee": "COF",
    "coffee-site": "COF",
    "examplesite": "EXA",
    "myproject": "MYP",
}
