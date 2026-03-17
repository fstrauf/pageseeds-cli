#!/usr/bin/env python3
"""Replicate EXACTLY what CopilotAdapter.run() does for the reddit task."""
import os
import subprocess
import tempfile
from pathlib import Path

# The real output path the reddit task would use
repo_root = Path("/Users/fstrauf/01_code/call-analyzer")
output_file = repo_root / ".github/automation/reddit/search_test_adapter.md"
output_file.parent.mkdir(parents=True, exist_ok=True)

MAX_POST_AGE_DAYS = 14

# Build the exact same prompt as reddit._run_opportunity_search does
prompt_text = f"""You are a Reddit marketing researcher. Find opportunities for days_to_expiry and save results to a markdown file.

CONFIG FILES TO READ (from repo's .github/automation/ directory):
1. project_summary.md
2. reddit_config.md
3. brandvoice.md

YOUR TASK:
1. Read project_summary.md
2. Read reddit_config.md to get product name, mention stance, and excluded subreddits
3. Read brandvoice.md for tone guidelines
4. EXTRACT AND STATE: Before searching, write down:
   - Product name: [from reddit_config.md]
   - Mention stance: [REQUIRED/RECOMMENDED/OPTIONAL/OMIT]
   - Trigger topics: [list from reddit_config.md]
   - EXCLUDED subreddits: [list from reddit_config.md - NEVER search these]
5. Search Reddit using the CLI for each subreddit + query combination (use --time week)
6. Filter out posts older than {MAX_POST_AGE_DAYS} days
7. For each relevant post, extract title, URL, subreddit, posted date
8. Score and draft a reply for each one
9. Save results to: {output_file}

Save to the file using the format:
# Reddit Opportunities: days_to_expiry

Search Date: 2026-03-17
Total Found: X

## Opportunity 1

**Post:** [title]
**Subreddit:** r/[name]
**Posted:** YYYY-MM-DD
**Age:** X days ago
**Severity:** [CRITICAL|HIGH|MEDIUM]
**Score:** X.X/10
**URL:** [url]
**Why Relevant:** [one sentence]
**Product Mention Stance:** [stance]

**Drafted Reply:**
[reply text]

---
"""

print(f"Prompt length: {len(prompt_text)} chars")

# EXACT adapter behavior: strip tokens, set allow_all
env = os.environ.copy()
for key in ("COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"):
    env.pop(key, None)
env["COPILOT_ALLOW_ALL"] = "true"
model = env.get("COPILOT_MODEL", "claude-sonnet-4.6")
env["COPILOT_MODEL"] = model

print(f"Model: {model}")
print(f"COPILOT_ALLOW_ALL: {env.get('COPILOT_ALLOW_ALL')}")
print(f"GH_TOKEN in env: {'GH_TOKEN' in env}")
print(f"GITHUB_TOKEN in env: {'GITHUB_TOKEN' in env}")
print()

with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tf:
    output_path = tf.name

try:
    print(f"Running copilot from cwd: {repo_root}")
    with open(output_path, "w") as out_f:
        result = subprocess.run(
            ["copilot", "--model", model, "--prompt", prompt_text, "--silent", "--no-color"],
            stdout=out_f,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(repo_root),
            timeout=300,
            env=env,
        )

    stdout_text = Path(output_path).read_text() if Path(output_path).exists() else ""
    print(f"Return code: {result.returncode}")
    print(f"Stdout length: {len(stdout_text)} chars")
    print(f"Stderr length: {len(result.stderr)} chars")
    print()

    if result.returncode != 0:
        print("=== STDERR (last 1000 chars) ===")
        print(result.stderr[-1000:])
        print()
        print("=== STDOUT (last 500 chars) ===")
        print(stdout_text[-500:])
    else:
        print("SUCCESS!")
        print(f"Output file created: {output_file.exists()}")
        if output_file.exists():
            print(f"Output file size: {output_file.stat().st_size} bytes")
        print()
        print("=== STDOUT preview (first 500 chars) ===")
        print(stdout_text[:500])

finally:
    if Path(output_path).exists():
        os.unlink(output_path)
