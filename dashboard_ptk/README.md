# Task Dashboard

A task-centered workflow for SEO automation. No campaigns, just tasks.

## Quick Start

```bash
cd /path/to/pageseeds-cli/dashboard_ptk
pip install prompt-toolkit rich
./run.sh
```

Primary user entrypoint is `pageseeds`. `run.sh` is intended for local dashboard package development.

## Core Workflow

```
Research → Create Content → Link → Publish → Monitor
     ↑                                    ↓
     └────────── Iterate ←───────────────┘
```

## Menu Options

```
1. View/Work on Tasks     - Main task loop
2. Projects               - Switch / add / manage websites
v. Verify Setup           - Check configuration
a. Articles               - Sync / repair / validate articles.json + files
o. Orchestrate Now        - Run bounded autonomous loop
p. Publish Articles       - Validate & publish drafts
i. Indexing Diagnostics   - Check GSC status
g. GSC Performance        - Find optimization opportunities
h. Reddit History         - View posted/skipped history
c. PostHog Config Check   - Check all project configs
s. Scheduler              - View / configure / run scheduler cycle
r. Reset Project          - Clear tasks, start fresh
d. Delete Project         - Remove project from dashboard
q. Quit
```

### Task Loop Options

```
1. Work on a task         - Manual task selection
2. Mark reviewed done     - Complete reviewed tasks
v. View specifications    - View spec files
b. Batch Mode             - Autonomous task processing ⭐
t. Bulk by Type           - Batch specific types only ⭐
3. Add more tasks         - Create new tasks
q. Back
```

## Task Types

| Type | Mode | What It Does | Auto-Created |
|------|------|--------------|--------------|
| `write_article` | direct | Write new article | From research |
| `optimize_article` | direct | Improve existing article | From research |
| `content_strategy` | spec | Plan pillar hubs, consolidation | From research |
| `technical_fix` | spec | Code/structural changes | From investigation |
| `cluster_and_link` | workflow | Add internal links | After each article |
| `content_cleanup` | workflow | Validate structure | After 4th article |
| `publish_content` | workflow | Publish drafts | Manual (`p`) |
| `collect_gsc` | workflow | Download GSC data | Yes |
| `collect_posthog` | workflow | Download PostHog data | Yes |
| `investigate_gsc` | workflow | Analyze findings | Yes |
| `research_keywords` | workflow | Find opportunities | Yes |
| `custom_keyword_research` | workflow | Research with custom themes | Menu `x` |
| `indexing_diagnostics` | workflow | Check indexing | Manual (`i`) |
| `analyze_gsc_performance` | workflow | Find ranking optimization opportunities | Manual (`g`) |
| `reddit_opportunity_search` | workflow | Find Reddit engagement opportunities | Manual |
| `reddit_reply` | manual | Post reply to Reddit thread | From opportunity search |
| `fix_*` | auto | Fix issues | From diagnostics |

## Content Workflow

### 1. Research (Agent) - Interactive
- Runs **long-tail keyword research** (low difficulty, decent volume)
- Presents **8-10 keyword candidates** with metrics table
- **User selects** which keywords to pursue (e.g., "1,3,5" or "all")
- Creates tasks **only for selected keywords**
- Shows: Keyword, Volume, KD, Opportunity Score, Intent

**Example Research Flow:**
```
📊 Keyword Opportunities for coffee
┌────┬─────────────────────────────┬────────┬──────┬─────┬──────────────┐
│  # │ Keyword                     │ Volume │ KD   │ Opp │ Intent       │
├────┼─────────────────────────────┼────────┼──────┼─────┼──────────────┤
│  1 │ best pour over coffee maker │ 1,200  │ 28   │ 🟢  │ transactional│
│  2 │ how to grind coffee beans   │ 800    │ 15   │ 🟢  │ informational│
│  3 │ coffee grinder vs pre-ground│ 450    │ 22   │ 🟡  │ informational│
└────┴─────────────────────────────┴────────┴──────┴─────┴──────────────┘

Select keywords to create article tasks:
Enter numbers (1-10) separated by commas, or 'all' for all
Your selection: 1,2
✓ Created 2 tasks
```

### 2. Create Content (Deterministic → Agent)
```
Dashboard: Get next ID, check dates, build filename
Agent: Write article content
Dashboard: Update articles.json, create linking task
```

### 3. Cluster & Link (Agent)
- Adds internal links (hub-spoke + cross-cluster)
- Updates content brief

### 4. Publish (Deterministic → Agent)
```
Phase 1: Validate structure (cleanup)
Phase 2: Check dates, fix if needed, publish drafts
```

**Safety:** Only changes dates for `draft` articles. Never touches published.

## Configuration

### Reddit Tasks (Requires Project Setup)

Reddit tasks need project-specific config files in the **target repo's** `.github/automation/` directory:

```bash
cd /path/to/target/repo
mkdir -p .github/automation/reddit

# Required files:
# - .github/automation/{project}.md      (website description)
# - .github/automation/reddit_config.md  (subreddits, queries, rules)
# - .github/automation/brandvoice.md     (tone guidelines)
```

See [GUIDE.md](GUIDE.md#required-configuration-target-repo) for examples.

### 1. Projects (`~/.config/automation/projects.json`)
```json
{
  "projects": [{
    "name": "Coffee Blog",
    "website_id": "coffeesite",
    "repo_root": "/path/to/your/coffee-site"
  }]
}
```

### 2. Registry (`WEBSITES_REGISTRY.json`)
```json
{
  "websites": [{
    "id": "coffee",
    "source_content_dir": "/path/to/your/coffee-site/src/blog/posts",
    "articles": "./general/coffee/articles.json"
  }]
}
```

## File Locations

| What | Where |
|------|-------|
| Task state | `{repo}/.github/automation/task_list.json` |
| Articles registry | `automation/general/{site}/articles.json` |
| Content files | `{repo}/src/blog/posts/` (from registry) |
| GSC artifacts | `{repo}/.github/automation/artifacts/` |
| Reddit config | `{repo}/.github/automation/{project}.md` |
| Reddit config | `{repo}/.github/automation/reddit_config.md` |
| Reddit config | `{repo}/.github/automation/brandvoice.md` |
| Reddit history | `{repo}/.github/automation/reddit/_posted_history.json` |
| Specs | `{repo}/.github/automation/specs/` |

## Deterministic vs Agent

**Deterministic (Dashboard):**
- ID assignment (sequential)
- Date gap checking
- Filename generation
- articles.json updates
- Task spawning

**Agent (Kimi):**
- Writing article content
- Adding internal links
- Structural analysis
- Content cleanup validation

## Batch Mode (Autonomous Processing)

Process multiple tasks without human intervention:

```
Menu → 1 (View/Work on Tasks) → b (Batch Mode)
```

**Autonomous Tasks (automatic):**
- `collect_gsc`, `investigate_gsc` - Data collection & analysis
- `research_keywords` - Keyword research
- `cluster_and_link` - Internal linking
- `content_cleanup` - Validation & cleanup
- `reddit_opportunity_search` - Find Reddit opportunities

**Batchable Tasks (with confirmation):**
- `write_article` - Content creation
- `optimize_article` - Content optimization
- `reddit_reply` - Reddit engagement (human reviews before posting)

**Manual Tasks (always pause):**
- `publish_content` - Publishing (safety first)
- `content_strategy` - Requires planning
- `technical_fix` - Requires dev environment

Configure batch size, auto-approval, and error handling in the batch menu.

## Orchestration and Scheduler

### Orchestrate Now (bounded run)
```
Menu → o
```

- Runs ready tasks through policy gates (`.github/automation/orchestrator_policy.json`)
- Persists run events + summaries in `.github/automation/orchestrator_runs/<run_id>/`

### Scheduler Management
```
Menu → s
```

- View/edit scheduler settings and rules
- Configure per-project Reddit automation cadence (`Option 7`, recommended `48h` for every 2 days)
- Install/repair and verify macOS launchd daemon from dashboard (`Option 8`)
- Run a scheduler cycle for current project or all projects
- Read global status from `output/monitoring/seo_scheduler/status.json`
- On macOS, scheduler sends a notification when new `reddit_reply` opportunities are generated

### Bulk by Type

Process only specific task types (useful when date constraints block `write_article`):

```
Menu → 1 (View/Work on Tasks) → t (Bulk by Type)
```

**Example workflow when dates are constrained:**
```
1. Check task loop - see 5 write_article tasks (can't run, date conflict)
2. Press 't' for Bulk by Type
3. Select 'optimize_article' type
4. Batch process optimizations while waiting for dates to free up
```

The bulk menu shows:
- All task types with ready counts
- Autonomy icons (⚡ 📝 📋 👤)
- Smart warnings for date-sensitive types
- Type-safe batching (optimizations don't conflict with publish dates)
- For Reddit workflow: choose `reddit_reply` type to open an opportunity list, select exact items, optionally bulk-edit reply text, then run a single-confirmation bulk send

## Common Tasks

### Publish Draft Articles
```
Menu → p
1. Validates structure (Phase 1)
2. Lists drafts ready to publish
3. Fixes date issues (drafts only)
4. Changes status: draft → published
```

### Check Indexing Status
```
Menu → i
1. Runs GSC URL inspection
2. Generates fix plan
3. Creates fix tasks
```

### Reset Project
```
Main Menu → r
- Deletes all tasks, artifacts, specs
- **Preserves Reddit tasks** (prevents duplicate posting)
- Keeps project config, articles, content
- Requires "reset" + "DELETE" confirmation
```

### Delete Project
```
Main Menu → d
- Removes project from dashboard configuration
- Does NOT delete content files, articles.json, or repo
- Requires typing project name to confirm
- Useful for cleaning up old or test projects
```

## Troubleshooting

**"Content file missing" in publish:**
- Article entry exists but no `.mdx` file
- Remove entry from articles.json or write content

**"Date in future":**
- Publish will offer to change to today
- Only fixes drafts, never published

**"Date overlap":**
- Two articles on same date
- Publish redistributes draft dates only

**"Task has no product/context configured" (custom_keyword_research):**
- Legacy task from before schema v4 (missing `custom_themes` metadata)
- Delete the task (menu `d`), then create new via menu `x`
- Or run: `python migrate_cleanup_legacy_tasks.py --apply`

## CLI Commands (for reference)

```bash
# Validate content
pageseeds content --workspace-root automation/general/coffee validate-content --website-path .

# Check dates
pageseeds content --workspace-root automation/general/coffee analyze-dates --website-path .

# GSC indexing
pageseeds automation seo gsc-indexing-report --site sc-domain:example.com --sitemap-url https://example.com/sitemap.xml
```

## Data Flow

```
1. Research → Creates content tasks
2. Content task → Writes .mdx to repo
              → Updates articles.json
              → Creates linking task
3. Linking task → Adds internal links
                → Updates brief
4. After 4th article → Creates cleanup task
5. Publish (manual) → Validates & publishes drafts
6. Indexing (manual) → Checks GSC → Creates fix tasks
```

## Key Principles

1. **Content lives in target repo only** - not in automation/
2. **articles.json in automation/** - tracks metadata, IDs, dates
3. **Sequential article IDs** - via articles.json max + 1
4. **Universal task IDs** - `{CODE}-{SEQ}` format (e.g., COF-001)
5. **Task types determine execution** - no title parsing, explicit types
6. **Date safety** - never change published article dates
7. **Draft gate** - all changes go through `status: draft`
