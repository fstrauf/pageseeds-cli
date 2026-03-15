# Dashboard Guide

Reference guide for the Task Dashboard. For quick start, see [README.md](README.md).

## Workflow Phases

| Phase | Purpose | Key Tasks |
|-------|---------|-----------|
| **Collection** | Download data | `collect_gsc`, `collect_posthog` |
| **Investigation** | Analyze & find issues | `investigate_gsc`, `investigate_posthog` |
| **Research** | Find opportunities | `research_keywords`, `research_landing_pages` |
| **Implementation** | Execute fixes | `create_content`, `cluster_and_link`, `publish_content`, `landing_page_spec`, `fix_*` |
| **Verification** | Confirm & monitor | `indexing_diagnostics`, `analyze_gsc_performance` |

## Project Switch Preflight
On project activation (startup, switch, or add), dashboard now auto-runs initialization checks:
- creates missing `.github/automation` subdirectories used by tasks
- validates essential project files (`articles.json`)
- checks required CLI (`pageseeds`)
- checks Reddit auto-post auth readiness (`pageseeds reddit auth-status`) when token is configured
- checks `.gitignore` excludes automation data

This catches missing essentials before task execution.

## Orchestration Mode
Use main menu option `o. Orchestrate Now` to run a bounded autonomous loop.

- Inputs:
  - max steps for this run
  - optional Reddit auto-post override for this run
- Policy file:
  - `.github/automation/orchestrator_policy.json`
- Run artifacts:
  - `.github/automation/orchestrator_runs/<run_id>/events.jsonl`
  - `.github/automation/orchestrator_runs/<run_id>/summary.json`
  - `.github/automation/orchestrator_runs/<run_id>/summary.md`

Default policy allows autonomous modes only (`automatic`, `batchable`) and blocks interactive research task types.

## Scheduler Mode
Use main menu option `s. Scheduler` to manage and run scheduled cycles.

- Scheduler config is stored in `.github/automation/orchestrator_policy.json` under `scheduler`.
- Scheduler state is stored per project in `.github/automation/scheduler_state.json`.
- Global monitoring output is written to `output/monitoring/seo_scheduler/status.json`.
- Per-project monitoring output is written to `output/monitoring/seo_scheduler/projects/<website_id>.json`.
- Use `Scheduler -> 7. Configure Reddit Automation` to enable/disable per project and set cadence (recommended: `48h` = every 2 days).
- Use `Scheduler -> 8. Setup / Verify macOS Scheduler Daemon` for one-click install/repair and status checks of launchd jobs.
- On macOS, scheduler emits a desktop notification when new Reddit opportunities are generated.

Scheduler rule modes:
- `create_task`: creates a new task (deduped against open tasks of same type).
- `reminder_only`: emits reminder/status signals without creating tasks.

### Interactive Fixes
Some warnings can be fixed automatically:

| Warning | Fix | How |
|---------|-----|-----|
| `.gitignore doesn't exclude automation data` | Adds `.github/automation/` to `.gitignore` | Press `y` when prompted |

**Example:**
```
⚠ .gitignore doesn't exclude automation data
    Fix: Run setup_gitignore.py to exclude .github/automation/ from git commits.

Fix gitignore now? (y/n): y
✓ .gitignore updated successfully
```

## Task Type Reference

### Content Tasks

**`write_article`** - Write new article (DIRECT)
- Agent writes content directly
- Deterministic: Assigns ID, checks dates, builds filename
- Spawns: `cluster_and_link` task after completion

**`optimize_article`** - Improve existing article (DIRECT)
- Agent edits existing file directly
- Finds article by title match
- Preserves: Original ID, publish date, URL slug
- Does NOT spawn linking task

**`content_strategy`** - Complex planning (SPEC)
- Creates specification first
- For: pillar hubs, consolidation, architecture changes
- Requires dev context to implement

### Technical Tasks

**`technical_fix`** - Code/structural changes (SPEC)
- Creates specification first
- For: build config, routing, meta tags

**`fix_technical`** / **`fix_content`** - Investigation findings (SPEC)
- Created by investigation tasks
- May be spec or direct depending on issue

**`cluster_and_link`** - Add internal links
- Auto-created after each content task
- Agent: Runs SEO Step 3 workflow
- Updates: Content brief with linking status

**`content_cleanup`** - Validate structure
- Auto-created after every 4th article
- Agent: Validates frontmatter, checks sync
- Does NOT change dates (safety)

**`publish_content`** - Publish drafts
- Manual trigger (menu `p`)
- Phase 1: Structural cleanup (auto-runs)
- Phase 2: Date fixes & publish
- Only changes `draft` articles

## Execution Modes

Task **type** determines execution mode explicitly:

| Mode | Indicator | Task Types | Workflow |
|------|-----------|------------|----------|
| **direct** | `[write]` | `write_article`, `optimize_article` | Dashboard sets up → Agent writes |
| **spec** | `[spec]` | `content_strategy`, `technical_fix`, `landing_page_spec` | Agent writes spec → Dev implements |
| **workflow** | `[flow]` | `cluster_and_link`, `publish_content`, diagnostics, research tasks | Run specialized handler |
| **auto** | `[auto]` | `fix_*` (unknown types) | Agent decides at runtime |

### Task Type Determines Mode

No title parsing. Task type maps directly to mode:

```python
mode_map = {
    "write_article": "direct",
    "optimize_article": "direct", 
    "content_strategy": "spec",
    "technical_fix": "spec",
    "landing_page_spec": "spec",
    "research_keywords": "workflow",
    "research_landing_pages": "workflow",
    "cluster_and_link": "workflow",
    "publish_content": "workflow",
    # ... etc
}
```

### Diagnostic Tasks

**`indexing_diagnostics`** - Check GSC
- Manual trigger (menu `i`)
- Runs: `pageseeds automation seo gsc-indexing-report`
- Creates: `fix_indexing` tasks from results

**`fix_indexing`** - Fix indexing issues
- Created by diagnostics
- May be direct or spec depending on issue

### Collection Tasks

**`collect_gsc`** - Download GSC data
- CLI: `pageseeds automation seo gsc-indexing-report`
- Output: `artifacts/gsc_collection.json`
- Spawns: `investigate_gsc` task

**`investigate_gsc`** - Analyze GSC data
- Agent: Reads collection, identifies issues
- Creates: `fix_technical` tasks

### Reddit Tasks

**`reddit_opportunity_search`** - Find Reddit engagement opportunities
- Searches seed subreddits/queries from `reddit_config.md`
- Scores posts (0-10) based on relevance, engagement, accessibility
- Drafts replies following brand voice and product mention rules
- **Auto-creates**: `reddit_reply` tasks for each opportunity
- Saves: `artifacts/reddit/search_{project}_{timestamp}.md`
- **⚠️ Config required** (in target repo): `project_summary.md`, `reddit_config.md`, `brandvoice.md`
  - See [Reddit Task Management > Required Configuration](#required-configuration-target-repo)

**`reddit_reply`** - Post reply to Reddit thread
- Human reviews drafted reply from opportunity search
- Options:
  1. Copy reply and mark posted (manual posting)
  2. Auto-post to Reddit (requires `REDDIT_REFRESH_TOKEN`)
  3. Skip opportunity (records in history to prevent re-suggestion)
  4. Keep for later review
- Bulk workflow supports:
  - opportunity list + multi-select (`1,3,5` or `all`)
  - optional bulk find/replace on selected reply drafts
  - one-shot confirmation that auto-sends all selected replies
- Token lookup precedence:
  1. process env
  2. `~/.config/automation/secrets.env`
  3. target repo `.env.local`
  4. target repo `.env`
  5. automation workspace `.env`
- Preflight check command: `pageseeds reddit auth-status` (shows auth-ready vs token/module problems)
- **History tracking**: Posted/skipped posts recorded in `.github/automation/reddit/_posted_history.json`
- **Deduplication**: Already-posted posts won't appear in future searches
- **Bulk review path**: `Menu -> 1 (View/Work on Tasks) -> t (Bulk by Type) -> reddit_reply`

### Research Tasks

**`research_keywords`** - Interactive long-tail keyword research
- **Goal**: Find 8-10 high-opportunity long-tail keyword candidates
- **Criteria**: 
  - Keyword Difficulty: LOW (<30 ideal, max 40)
  - Search Volume: 100-500+ monthly searches
  - Specificity: 3-5 word phrases
  - Intent: Clear problem/question
- **Interactive Flow**:
  1. Agent researches and presents keyword candidates table
  2. User selects which keywords to pursue (e.g., "1,3,5")
  3. Tasks created only for selected keywords
- **User Selection**: Enter numbers like "1,3,5" or "all" or "none"
- Creates: `write_article`, `optimize_article` tasks (user-selected only)
- Saves: `task_results/{TASK-ID}/research.json`

**`custom_keyword_research`** - Agentic keyword research with user-defined themes
- **Goal**: Find keywords based on custom product themes and criteria
- **How to create**: Task menu → `x` (Custom Keywords), enter themes interactively
- **How it works**:
  1. AI agent reads instructions from `keyword_research_instructions.md`
  2. AI executes `pageseeds seo` commands directly (subprocess)
  3. AI analyzes results and selects best keywords
  4. Gets difficulty data via `batch-keyword-difficulty`
  5. Presents results for user selection
- **Parameters** (set when creating task):
  - `custom_themes`: List of product/theme descriptions (required)
  - `custom_criteria`: Focus instructions (e.g., "focus on beginners")
  - `exclude_terms`: Terms to exclude from results
  - `min_volume`: Minimum search volume threshold (default: 100)
  - `max_kd`: Maximum keyword difficulty (default: 40)
- **Execution Time**: 3-10 minutes depending on theme complexity
- **Creates**: `write_article` tasks for selected keywords
- **Technical Details**:
  - Uses instruction file pattern (no MCP servers)
  - AI runs CLI tools via subprocess
  - Parses JSON output directly
  - Results extracted from file or stdout fallback
- **Note**: Tasks created before schema v4 may lack `custom_themes` metadata. See Troubleshooting section for cleanup.

### Landing Page Tasks

**`research_landing_pages`** - Find landing page keyword opportunities
- **Goal**: Find 8-10 keywords with commercial/transactional intent for dedicated landing pages
- **Difference from `research_keywords`**:
  - Focuses on **conversion intent** (not just traffic)
  - Creates **landing page specs** (not articles)
  - Targets **commercial keywords** (alternative, comparison, category)
- **Criteria**:
  - Intent: Transactional/Commercial/Comparison
  - Keyword Difficulty: <40 (ideally <30)
  - Search Volume: 200+ monthly (higher value justifies investment)
  - Patterns: "alternative", "vs", "best [category]", "[solution] for [audience]"
- **Interactive Flow**:
  1. Agent researches commercial-intent keywords
  2. Presents landing page candidates with type classification
  3. User selects which opportunities to pursue
  4. Creates `landing_page_spec` tasks for selection
- **Creates**: `landing_page_spec` tasks (user-selected only)
- **Saves**: `task_results/{TASK-ID}/research.json`
- **Skill Reference**: `.github/skills/landing-page-keyword-research/SKILL.md`

**`landing_page_spec`** - Create landing page specification (SPEC)
- **Goal**: Create detailed specification for a landing page implementation
- **How it works**:
  1. Agent reads research data from parent `research_landing_pages` task
  2. Writes comprehensive specification to `.github/automation/specs/landing_page_{keyword}.md`
  3. Specification includes:
     - Target keyword and search intent analysis
     - Page structure (hero, features, social proof, FAQ, CTAs)
     - SEO requirements (title, meta, URL, headers)
     - Content guidelines and messaging
     - Design and technical notes
     - Acceptance criteria
- **Output**: Specification file in `specs/` directory
- **Next Steps**: Developer implements from specification in target repo
- **Mode**: `[spec]` - Pauses for human review/implementation

### Performance Tasks

**`analyze_gsc_performance`** - Analyze GSC ranking data for optimization opportunities
- **Goal**: Identify pages ranking in positions 3-15 (quick wins) and declining pages
- **How it works**:
  1. Runs `pageseeds automation seo gsc-site-scan` to fetch performance data
  2. Analyzes pages by position, impressions, and trends
  3. Categorizes opportunities:
     - **Quick Wins (Positions 3-15)**: Small improvements → big gains
     - **Decliners**: Pages losing impressions (needs attention)
     - **Top Performers (Positions 1-3)**: Protect and expand
  4. Presents interactive selection UI
  5. Creates `optimize_article` tasks for selected pages
- **Interactive Flow**:
  1. Scans top pages by impressions + biggest decliners
  2. Displays categorized opportunities with metrics
  3. User selects pages to optimize (e.g., "1,3,5")
  4. Creates optimization tasks automatically
- **Creates**: `optimize_article` tasks with performance context
- **Saves**: `task_results/{TASK-ID}/performance_analysis.json`
- **Menu Access**: Main menu option `g. GSC Performance Analysis`
- **Autonomy**: `automatic` - Can run in batch mode

## Configuration Reference

### WEBSITES_REGISTRY.json Fields

```json
{
  "id": "coffeesite",
  "name": "Coffee Blog",
  "path": "./general/coffee",
  "manifest": "./general/coffee/manifest.json",
  "articles": "./general/coffee/articles.json",
  "source_repo_local_path": "/path/to/your/coffee-site",
  "source_content_dir": "/path/to/your/coffee-site/src/blog/posts"
}
```

| Field | Purpose |
|-------|---------|
| `id` | Matches `website_id` in projects.json |
| `source_content_dir` | Where .mdx files are written |
| `articles` | Path to articles.json (metadata) |
| `source_repo_local_path` | Target repo root (for reference) |

### Project Config (`~/.config/automation/projects.json`)

```json
{
  "projects": [{
    "name": "Coffee Blog",
    "website_id": "coffeesite",
    "repo_root": "/path/to/your/coffee-site"
  }]
}
```

## Task ID Assignment (Universal Numbering)

Tasks use a universal numbering system: `{PROJECT_CODE}-{SEQUENCE}`

| Project | Code | Example IDs |
|---------|------|-------------|
| Coffee Blog (coffeesite) | COF | COF-001, COF-002, COF-003 |
| My Project (myproject) | MYP | MYP-001, MYP-002 |

**Features:**
- Sequence persists across sessions (stored in task_list.json metadata)
- Human-readable and referenceable
- Shown in dashboard next to each task

## Article ID Assignment

```python
next_id = max(a['id'] for a in articles) + 1
filename = f"{next_id:03d}_{slug}.mdx"
```

- 3-digit zero-padded (001, 002, ..., 165)
- Sequential, no gaps
- Stored in `articles.json` at automation repo

## Filename vs URL Slug Convention

The system uses **two different values** for organization vs. public URLs:

| Field | Format | Purpose | Example |
|-------|--------|---------|---------|
| **filename** | `{id:03d}_{slug}.mdx` | File organization (sorted by ID) | `104_spy_vs_spx_options.mdx` |
| **url_slug** | `{slug}` | Clean URL for website | `spy-vs-spx-options` |

**Key rule:** The `url_slug` field should **NOT** include the numeric ID prefix. It's automatically generated by stripping the ID from the filename.

```python
# Filename: 104_spy_vs_spx_options.mdx
url_slug = re.sub(r'^\d+_', '', filename)  # → spy_vs_spx_options
url_slug = url_slug.replace('_', '-')      # → spy-vs-spx-options
```

This is enforced by:
- `ArticleManager.add_article()` - creates slugs without ID prefix
- `check_slug_alignment()` - validates slugs don't have ID prefix
- `check_article_slug_alignment()` (CLI) - same validation for diagnose command

## Date Safety Rules

| Rule | Enforcement |
|------|-------------|
| 1+ day gap | Checked in publish phase |
| No future dates | Changed to today if found |
| Unique dates | Redistributed if overlap |
| **Published protected** | Never changed after publish |

## File Locations

```
automation/                              # This repo
├── general/coffee/
│   ├── articles.json                    # Metadata, IDs, dates
│   ├── coffee_seo_content_brief.md      # Strategy doc
│   └── manifest.json                    # URL, GSC site
└── dashboard_ptk/
    ├── main.py                          # Dashboard entry point
    ├── dashboard/                       # Core dashboard package
    │   ├── cli.py                       # Main menu router/composition
    │   ├── cli_verification.py          # Verify/setup flows
    │   ├── cli_articles.py              # Articles submenu flows
    │   ├── cli_task_actions.py          # Task action flows
    │   ├── cli_projects.py              # Projects menu flows
    │   ├── batch.py                     # Batch processing
    │   ├── config.py                    # Task type mappings
    │   ├── core/                        # State management
    │   ├── models/                      # Task, Project, BatchConfig
    │   ├── storage/                     # Task persistence
    │   ├── tasks/                       # Task runners
    │   ├── ui/                          # Console rendering
    │   └── utils/                       # Article helpers
    └── README.md                        # Quick start

coffee-site/                             # Target repo
├── src/blog/posts/
│   ├── 165_article.mdx                  # Content files
│   └── ...
└── .github/automation/
    ├── task_list.json                   # Tasks for this project
    ├── artifacts/                       # GSC data, Reddit searches
    │   ├── gsc_collection.json
    │   └── reddit/
    │       └── search_{project}_{timestamp}.md
    ├── specs/                           # Specifications
    ├── reddit/
    │   └── _posted_history.json         # Reddit engagement history
    ├── reddit_config.md                 # Reddit search config
    └── brandvoice.md                    # Brand voice guidelines
```

## Agent Prompts

Content creation uses this structure:

```
PROJECT: {website_id}
TOPIC: {article_title}
OUTPUT_FILE: {full_path}
PUBLISH_DATE: {YYYY-MM-DD}
TARGET_KEYWORD: {keyword}

INSTRUCTIONS:
1. Write comprehensive article
2. Use WriteFile tool to save to OUTPUT_FILE
3. Include frontmatter with title, description, date
4. Write 800-1500 words
5. Include H2/H3 headings
```

## CLI Tools Reference

### pageseeds content

```bash
# Content validation
pageseeds content --workspace-root automation/general/coffee validate-content --website-path .

# Comprehensive diagnostic (articles.json vs content files)
pageseeds content --workspace-root automation/general/coffee diagnose --website-path .
pageseeds content --workspace-root automation/general/coffee diagnose --website-path . --verbose

# Fix nextArticleId (sets to max_id + 1)
pageseeds content --workspace-root automation/general/coffee fix-next-id --website-path .
pageseeds content --workspace-root automation/general/coffee fix-next-id --website-path . --dry-run

# Date analysis
pageseeds content --workspace-root automation/general/coffee analyze-dates --website-path .

# Fix dates (only recent/draft articles)
pageseeds content --workspace-root automation/general/coffee fix-dates --website-path .

# Sync and validate (check index/content gaps, optionally sync dates)
pageseeds content --workspace-root automation/general/coffee sync-and-validate --website-path .
pageseeds content --workspace-root automation/general/coffee sync-and-validate --website-path . --apply-sync

# Scan internal links
pageseeds content --workspace-root automation/general/coffee scan-internal-links --website-path .

# Generate linking plan
pageseeds content --workspace-root automation/general/coffee generate-linking-plan --website-path . --missing-only

# Add article links
pageseeds content --workspace-root automation/general/coffee add-article-links --website-path . --source-id {ID} --target-ids {ID1} {ID2}
```

### pageseeds automation

```bash
# GSC indexing report
pageseeds automation seo gsc-indexing-report \
  --site sc-domain:example.com \
  --sitemap-url https://example.com/sitemap.xml \
  --limit 200 \
  --workers 2
```

## Menu Actions

| Key | Action |
|-----|--------|
| `1` | Enter task work loop |
| `2` | Switch project |
| `v` | Verify setup (registry, content dir, articles.json) |
| `p` | Publish articles (cleanup + publish) |
| `i` | Indexing diagnostics (GSC check) |
| `r` | Reset project (clear tasks, keep config) |
| `d` | Delete project (remove from dashboard) |
| `q` | Quit |

In task loop:
| Key | Action |
|-----|--------|
| `1` | Work on task (includes review tasks) |
| `2` | Mark reviewed done (supports multi-select) |
| `v` | View specifications |
| `b` | **Batch Mode** - Process multiple tasks autonomously |
| `t` | **Bulk by Type** - Batch specific task types only |
| `3` | Add more tasks |
| `d` | **Delete task(s)** - Remove one or more tasks (requires confirmation) |
| `r` | Reset project (with confirmation) |
| `q` | Back to main menu |

### Delete Task(s)

Delete one or more tasks that are no longer needed.

**Input formats:**
- Single number: `3` (delete task #3)
- Multiple numbers: `1,3,5` (delete tasks #1, #3, #5)
- Task IDs: `COF-001,COF-003` (delete by task ID)
- Mixed: `2,COF-005` (combine numbers and IDs)

**Restrictions:**
- Cannot delete completed (`done`) tasks
- Requires typing "delete" to confirm
- Shows summary of all tasks before bulk deletion
- Shows warning for in-progress tasks

**Use cases:**
- Remove duplicate or mistakenly created tasks
- Clean up tasks that are no longer relevant
- Cancel tasks that cannot be completed
- Bulk cleanup of old tasks

### Work on Task

Select and work on available tasks.

**Task states shown:**
- `○` To Do - Ready to start
- `◐` In Progress - Continue working
- `👁` Review - Choose to continue or mark done

**Review tasks:** When selecting a task in "review" status, you can:
1. Continue working on it (more changes needed)
2. Mark as done (review complete)

### Mark Reviewed Tasks Done (Multi-Select)

When you have multiple tasks in "review" status, you can mark them done individually or in bulk:

```
Tasks in Review:

  1. Fix GSC access: examplesite (39 URLs blocked)
  2. GSC Service Account Permission Failure
  3. Article Mapping Completely Broken
  4. No Indexing Data Available
  5. Potential URL Property Mismatch
  a. Mark all done
  c. Cancel

Enter: 1 or 1,3,5 or 'a' for all

Choice: 1,3,5
✓ Marked 3 done
```

**Input formats:**
- Single number: `2` (mark task #2 as done)
- Multiple numbers: `1,3,5` (mark tasks #1, #3, #5 as done)
- All: `a` (mark all review tasks as done)

## Batch Mode (Autonomous Execution)

Batch mode allows the dashboard to process multiple tasks without human intervention.

### Task Autonomy Levels

Tasks are classified by how autonomously they can run:

| Level | Types | Behavior |
|-------|-------|----------|
| **automatic** | `collect_gsc`, `investigate_gsc`, `research_keywords`, `custom_keyword_research`, `research_landing_pages`, `analyze_gsc_performance`, `cluster_and_link`, `content_cleanup`, `reddit_opportunity_search` | Run fully autonomously |
| **batchable** | `write_article`, `optimize_article`, `reddit_reply` | Can batch but may need review after |
| **spec** | `content_strategy`, `technical_fix`, `landing_page_spec`, `fix_*` | Pause for human (requires dev work) |
| **manual** | `publish_content`, `indexing_diagnostics` | Always require human |

### Using Batch Mode

1. From the task loop, press `b` to enter batch mode
2. Review the preview of tasks ready for batch processing
3. Set max tasks to process (1-20)
4. Confirm whether to auto-process content tasks
5. The dashboard will execute tasks sequentially until:
   - All ready tasks are processed
   - Max task limit is reached
   - An error occurs (if `pause_on_error` is enabled)
   - A spec/manual task is encountered
   - User interrupts with `Ctrl+C`

### Batch Configuration

Default settings:
- Max tasks: 10
- Pause on error: Yes
- Pause on spec task: Yes
- Rate limit delay: 5 seconds between tasks

### Progress Indicators

Long-running agent tasks now show real-time progress:

```
▶ Task 9: LEA-051 - Link article: When to Hire Your First CTO...
   Type: cluster_and_link | Autonomy: automatic

Cluster & Link Task: Link article: When to Hire Your First CTO...
Running SEO Step 3: Clustering and Internal Linking

Running clustering and linking workflow...
This may take 3-5 minutes. Press Ctrl+C to cancel.

⠼ Working... (45s elapsed)   ← Single line spinner with elapsed time
```

Tasks with progress indicators:
- `cluster_and_link` - Shows spinner during linking workflow
- `research_keywords` - Shows spinner during research
- `custom_keyword_research` - Shows spinner during agentic research
- `write_article` - Shows spinner during content writing
- `optimize_article` - Shows spinner during content optimization

The spinner displays on a single line and updates with elapsed time so you know the task is still running.

### Safety Features

- **Never auto-publishes** - Publishing always requires human confirmation
- **Pauses on errors** - Failed tasks stop the batch (configurable)
- **Interruptible** - Press `Ctrl+C` to stop gracefully
- **Progress tracking** - Shows completion status and any errors

---

## Bulk by Type (Selective Batch Processing)

When you have many tasks but only want to process a specific type (e.g., only optimizations, skipping new articles due to date constraints).

### Use Cases

| Scenario | Solution |
|----------|----------|
| Date constraints blocking writes | Run `optimize_article` tasks only |
| Focus on technical fixes | Run `fix_*` tasks batch |
| Clean up old research | Run `research_keywords` first |
| Linking backlog | Batch `cluster_and_link` tasks |

### How to Use

1. From task loop, press `t` for **Bulk by Type**
2. Select task type from the list (shows ready counts)
3. For most task types: configure max tasks and confirm
4. For `reddit_reply`: review opportunities, select exact items, choose action, then confirm

### Reddit Reply Review and Send Flow

When batch processing `reddit_reply` tasks, the dashboard runs a selection-first flow:

1. Shows a numbered list with subreddit, post date, age, and title
2. Lets you select opportunities (`1,3,5` or `all`)
3. Optionally applies a bulk find/replace to selected draft replies
4. Applies one action to selected tasks

| Choice | Action | When to Use |
|--------|--------|-------------|
| `1` | Auto-post selected replies | Uses one final confirmation, then posts all selected |
| `2` | Copy + mark selected posted | Manual Reddit posting |
| `3` | Skip selected opportunities | Cleanup while recording history |
| `4` | Keep selected for later | Cancels the batch |

**Example workflow:**
```
📦 Bulk by Type
Selected: reddit_reply
Ready tasks: 4

Reddit Opportunity Review
  #  Subreddit            Posted       Age               Title
  1  r/ynab               2026-03-08   2 days            ...
  2  r/investing          2026-03-05   5 days            ...
  3  r/personalfinance    2026-02-20   19 days (stale)   ...

Select opportunities: 1,2
Apply bulk find/replace to selected replies? y
Action: 1 (auto-post selected)
Final confirmation: auto-post 2 selected replies now? yes
```

This keeps Reddit posting intentional: you choose exact opportunities, optionally adjust drafts in bulk, and then execute selected replies in one confirmed run.

### Smart Type Selection

The menu shows:
- Task type icon (⚡ automatic, 📝 batchable, 📋 spec, 👤 manual)
- Number of ready tasks per type
- Only types with ready tasks are shown

### Date Constraint Handling

When selecting `write_article`:
- Shows warning about date requirements
- Suggests `optimize_article` as alternative
- Tasks may fail if date spacing insufficient

When selecting `optimize_article`:
- Shows confirmation that it's date-safe
- Can run anytime without scheduling concerns
- No publish date conflicts

## Reset Behavior

Main Menu `r` → "Reset project":

**Deletes:**
- All tasks from task_list.json (except Reddit tasks - see below)
- Collected artifacts (GSC data, etc.)
- Research results
- Generated specifications

**Preserved (SAFE):**
- **Reddit tasks** (`reddit_opportunity_search`, `reddit_reply`) - Prevents duplicate posting
- articles.json (your article registry)
- Content files (.mdx) in src/blog/posts/
- Project configuration
- Reddit posting history (`.github/automation/reddit/_posted_history.json`)

**Why Preserve Reddit Tasks?**
Reddit tasks track which posts you've already engaged with. Resetting them could lead to accidentally replying to the same post twice. They're preserved to prevent this.

**Requires:** type "reset", then "DELETE" if tasks exist

## Delete Project Behavior

Main Menu `d` → "Delete project":

**Deletes:**
- Project entry from `~/.config/automation/projects.json`

**Preserved (SAFE):**
- All content files (.mdx)
- articles.json metadata
- Target repository
- Task history (in repo's `.github/automation/`)

**Requires:** type the exact project name to confirm

**Use case:** Clean up old or test projects from the dashboard without affecting any actual content. The project can be re-added later by editing `projects.json`.

## Troubleshooting

### Task status not saving

Tasks complete but status reverts on restart.

**Cause:** `save()` not called after status change.

**Fix (Immediate):** Ensure code uses `StateManager` which auto-saves:
```python
sm = StateManager(project)
sm.update_task_status(task.id, "done")  # Auto-saves
```

**Legacy code fix:** Add `self.task_list.save()` after any status change:
```python
task.status = "done"
self.task_list.save()  # Required!
```

### Duplicate task IDs

Multiple tasks share the same ID (e.g., two "COF-001" tasks).

**Fix:** Run cleanup script to fix existing duplicates:
```python
from dashboard.core import StateManager
sm = StateManager(project)
sm._deduplicate_task_ids()  # Removes duplicates
```

**Prevention:** Always use `StateManager.create_task()` which checks for ID collisions.

### Article ID always starts at 1

New articles get ID 001 even though articles 001-165 exist.

**Cause:** `get_next_id()` not receiving correct `repo_root`.

**Fix:** Pass `repo_root` from project:
```python
# Correct
article_id = get_next_id(repo_root=self.project.repo_root)

# Incorrect (uses hardcoded wrong path)
article_id = get_next_id()
```

### Delete task doesn't work

Task still appears after deletion.

**Cause:** `delete_task()` only removed first matching task.

**Fix:** Use `StateManager.delete_task()` which removes ALL matching IDs, or update `TaskList.delete_task()` to use list filter:
```python
# Correct (removes ALL matching)
self.tasks = [t for t in self.tasks if t.id != task_id]

# Incorrect (only removes first)
for task in self.tasks:
    if task.id == task_id:
        self.tasks.remove(task)  # Stops after first!
```

### "Content file missing" in publish

Articles.json has entry but no `.mdx` file exists.

**Fix:**
1. Write content (run content task)
2. Or remove entry via cleanup script

### "Date in future"

Draft article has date > today.

**Fix:**
- Publish workflow offers to change to today
- Only applies to drafts

### "Date overlap"

Two articles share same date.

**Fix:**
- Publish redistributes draft dates
- Published articles never changed

### Preventing Articles.json Drift

Run diagnostics periodically to catch issues early:

```bash
# Quick health check
pageseeds content diagnose --website-path /path/to/project

# Recommended: Run before publishing
pageseeds content diagnose --website-path /path/to/project --verbose
```

**Best practices:**
1. Run `diagnose` before publishing new articles
2. Fix any `nextArticleId` issues immediately
3. Resolve date mismatches before they accumulate
4. Keep content files as source of truth

### Articles.json out of sync

**Diagnose issues:**
```bash
# Comprehensive diagnostic
pageseeds content diagnose --website-path /path/to/project

# With verbose output (shows all mismatches)
pageseeds content diagnose --website-path /path/to/project --verbose
```

This checks:
- `nextArticleId` correctness
- ID gaps
- Duplicate dates in JSON
- Duplicate dates in frontmatter
- Date mismatches between JSON and content files
- Missing content files
- Orphaned content files (not in JSON)
- **Slug/filename alignment** - url_slug should match filename (minus numeric prefix)

**Slug alignment check:**
The dashboard validates that `url_slug` in articles.json matches the content filename (without the numeric prefix). 

Examples of correct alignment:
| Filename | url_slug | Status |
|----------|----------|--------|
| `01_cash_secured_puts_playbook.mdx` | `cash_secured_puts_playbook` | ✓ Aligned |
| `102_wheel_strategy.mdx` | `wheel_strategy` | ✓ Aligned |
| `article_without_prefix.mdx` | `article_without_prefix` | ✓ Aligned |

**Fix common issues:**
```bash
# Fix nextArticleId if incorrect
pageseeds content fix-next-id --website-path /path/to/project

# Sync frontmatter dates from articles.json
pageseeds content sync-and-validate --website-path /path/to/project --apply-sync

# Fix slug alignment (update url_slug to match filenames)
python3 -c "
import json, re
with open('.github/automation/articles.json') as f:
    data = json.load(f)
for a in data['articles']:
    filename = a['file'].split('/')[-1].replace('.mdx', '')
    a['url_slug'] = re.sub(r'^\d+_', '', filename)
with open('.github/automation/articles.json', 'w') as f:
    json.dump(data, f, indent=2)
print('Fixed!')
"
```

**Legacy cleanup script:** `dashboard_ptk/cleanup_articles.py`

Options:
- Analyze state
- Remove phantom drafts
- Fix published→draft for missing content

### Date clusters (multiple articles same date)

Multiple articles share the same publish date (e.g., 6 articles on Jan 30), breaking the 2-day gap rule.

**Fix:** Run the cluster redistribution tool:
```bash
cd /path/to/your/automation
python3 dashboard_ptk/fix_date_clusters.py --apply
```

**What it does:**
1. Identifies clusters (2+ articles on same date)
2. Redistributes cluster articles with 2-day gaps
3. Fits drafts into newly created gaps
4. Preserves isolated article dates where possible
5. Ensures all dates are ≤ today

**Dry run first:**
```bash
python3 dashboard_ptk/fix_date_clusters.py  # Shows changes without applying
```

## Reddit Task Management

### Required Configuration (Target Repo)

> ⚠️ **Reddit tasks require project-specific config files in the target repo.**
> These are NOT installed by `pageseeds automation repo init` - you must create them.

Create these files in `{repo}/.github/automation/`:

| File | Required | Purpose |
|------|----------|---------|
| `project_summary.md` | ✅ Yes | Website/product description |
| `reddit_config.md` | ✅ Yes | Seed subreddits, queries, product mention rules |
| `brandvoice.md` | ✅ Yes | Tone and voice guidelines |
| `reddit/_reply_guardrails.md` | Auto-created | Reply formatting rules (created on first run) |

**Example reddit_config.md:**
```markdown
# Reddit Configuration

## Product
- Name: Your Product Name
- Description: What it does

## Seed Subreddits
- r/subreddit1
- r/subreddit2

## Seed Queries
- "keyword phrase"
- "alternative phrase"

## Product Mention Rules
- REQUIRED: Always mention product name
- RECOMMENDED: Mention when natural
- OPTIONAL: Mention if relevant
- OMIT: Never mention product

## Excluded Subreddits
- r/personalfinance (too broad)
```

**Example brandvoice.md:**
```markdown
# Brand Voice

## Tone
- Direct and helpful
- No emojis or marketing speak

## Forbidden Phrases
- "game-changing"
- "revolutionary"
```

### The Critique Workflow (Applies to ALL Replies)

Every single Reddit reply must go through this critique pass:

> Act as an old man copy editor at a respected newspaper who believes deeply in respecting your reader's time. Review your drafted reply and ask:
> 1. Is every sentence earning its place?
> 2. Can any words be cut without losing meaning?
> 3. Is the tone conversational, not corporate?
> 4. Does it sound like something you'd say to a friend over coffee?
> 5. Does it respect the reader's intelligence and time?

**Then: Revise ruthlessly.**

This is NON-NEGOTIABLE and applies to all projects regardless of mention stance.

**Quick init for new projects:**
```bash
cd /path/to/target/repo
mkdir -p .github/automation/reddit
# Create: .github/automation/project_summary.md
# Create: .github/automation/reddit_config.md
# Create: .github/automation/brandvoice.md
```

---

### History Tracking

Reddit tasks maintain a history file to prevent duplicate engagement:

**Location**: `{repo}/.github/automation/reddit/_posted_history.json`

**Contains**:
- `posted`: Array of posts you've already replied to
- `skipped`: Array of posts you chose to skip (won't suggest again)
- `metadata`: Last updated timestamp

**Automatic Deduplication**:
- Opportunity search checks history before including posts
- Already-posted posts are excluded from results
- Skipped posts won't appear in future searches

### Reset Behavior with Reddit

When resetting a project (Main Menu `r`):
- **Posted Reddit tasks are preserved** - prevents duplicate posting
- Unposted/skipped Reddit tasks are removed (will be rediscovered)
- To clear skipped entries and allow rediscovery, manually delete them from history

---

## Architecture

```
dashboard/
├── cli.py           # Main menu router/composition
├── cli_verification.py  # Verify/setup flows
├── cli_articles.py  # Articles submenu flows
├── cli_task_actions.py  # Task action flows
├── cli_projects.py  # Projects menu flows
├── batch.py         # Batch processing
├── config.py        # Constants, task type mappings
├── core/            # NEW: Robust state management
│   ├── __init__.py
│   └── state_manager.py
├── models/          # Task, Project, BatchConfig
├── storage/         # TaskList (JSON persistence)
├── ui/              # Console, rendering
├── tasks/           # Task runners by type
│   ├── collection.py
│   ├── content.py
│   ├── linking.py
│   └── ...
├── utils/           # Article helpers
└── tests/           # Test suite
    └── test_state_manager.py
```

**Key files:**
- `config.py` - Centralized: `PHASES`, `EXECUTION_MODE_MAP`, `AUTONOMY_MODE_MAP`
- `tasks/content.py` - Article creation/optimization logic
- `tasks/implementation.py` - Task dispatcher (direct/spec/workflow/auto)
- `utils/articles.py` - articles.json operations
- `core/state_manager.py` - Robust state management (new)

---

## State Management (Robust Architecture)

The dashboard uses a robust state management system to prevent data loss, duplicate IDs, and path resolution bugs.

### Issues Fixed

| Issue | Root Cause | Solution |
|-------|------------|----------|
| **Task status not persisting** | `save()` not called after status changes | Auto-save on every change via `StateManager` |
| **Duplicate task IDs** | No collision check when creating tasks | ID uniqueness enforced in `create_task()` |
| **Delete only removed one task** | `list.remove()` stops at first match | Filter list to remove ALL matching IDs |
| **Article ID reset to 1** | `get_next_id()` used hardcoded wrong path | Pass `repo_root` from project config |
| **Content not found** | Symlinks not resolved | Added `resolve()` in `get_content_dir()` |
| **Dead code paths** | Success code after `return False` | Restructured conditionals, early returns |

### Core Services

#### StateManager

**Location:** `dashboard/core/state_manager.py`

Provides atomic state operations with automatic persistence:

```python
from dashboard.core import StateManager

sm = StateManager(project)

# Create task (auto-saves, validates, generates unique ID)
task = sm.create_task("write_article", "My Article", "implementation")

# Update status (validates transitions, auto-saves)
sm.update_task_status(task.id, "done")

# Atomic batch operation (rolls back on failure)
with sm.atomic():
    sm.create_task(...)
    sm.update_task(...)
    sm.delete_task(...)
```

**Features:**
- **Auto-save**: Every state change automatically persisted
- **Atomic operations**: All-or-nothing with rollback on failure
- **Validation**: Pre-save validation prevents bad data
- **Duplicate prevention**: ID uniqueness enforced

**Key Methods:**
- `create_task(type, title, phase)` - Creates with guaranteed unique ID
- `update_task_status(id, status)` - Validates status transitions
- `delete_task(id)` - Removes ALL matching IDs (handles duplicates)
- `get_ready_tasks()` - Returns unlocked tasks sorted by priority
- `reset_all()` - Atomic reset with backup

#### PathResolver

Resolves paths consistently across the project:

```python
from dashboard.core import PathResolver

resolver = PathResolver(project)

# Find content directory (follows symlinks)
content_dir = resolver.get_content_dir()
# Checks: content/, src/content/, src/blog/posts/, posts/, blog/

# Find articles.json
articles_json = resolver.get_articles_json_path()
```

#### TaskValidator

Validates task data integrity:

```python
from dashboard.core import TaskValidator

validator = TaskValidator()
validator.validate_task(task)  # Raises StateError if invalid
```

**Validates:**
- Task ID presence
- Status in valid set (todo, in_progress, review, done, cancelled)
- Phase in valid set (collection, investigation, research, implementation, verification)
- Title presence

### Error Handling

**StateError Exception:**
- Clear error messages
- Distinguishes validation vs system errors

```python
from dashboard.core import StateError

try:
    sm.create_task(...)
except StateError as e:
    console.print(f"[red]Cannot create task: {e}[/red]")
```

### Testing

**Test Suite:** `dashboard/tests/test_state_manager.py`

**Keyword Research Tests:** `dashboard/tests/test_keyword_research.py`

Run keyword research tests before using the feature:
```bash
cd dashboard_ptk
source .venv/bin/activate
python3 tests/test_keyword_research.py
```

**Tests cover:**
- MCP configuration check (ensures no conflicts)
- `pageseeds seo` availability
- `keyword-generator` command functionality
- `batch-keyword-difficulty` command functionality
- Instructions file completeness
- JSON extraction logic

**Expected output:** 6/7 tests passing (AI execution test may timeout but is not critical)

```bash
cd dashboard_ptk/dashboard/tests
python test_state_manager.py
```

**Coverage:**
- Path resolution with symlinks
- Task validation
- State persistence
- Unique ID generation
- Duplicate detection and cleanup
- Task deletion
- Dependency resolution

### Legacy custom_keyword_research Tasks

**Error:** `Task has no product/context configured. Add themes/criteria to task metadata.`

**Cause:** Task created before schema v4 refactor without `custom_themes` metadata.

**Fix (Quick):**
1. Delete the task (task loop → `d`)
2. Create new task (task loop → `x` for Custom Keywords)
3. Enter themes when prompted

**Fix (Batch cleanup):**
```bash
cd dashboard_ptk

# Preview what will be removed
python migrate_cleanup_legacy_tasks.py --dry-run

# Remove all legacy tasks (creates backups)
python migrate_cleanup_legacy_tasks.py --apply
```

**Prevention:** Always use menu `x` to create custom keyword research tasks (ensures proper metadata).

### Migration from Old Code

The old `TaskList` class still works but requires manual `save()` calls:

```python
# OLD (fragile - easy to forget save)
task_list = TaskList(automation_dir)
task_list.tasks.append(task)
task_list.save()  # Must remember to call this!

# NEW (robust - auto-saves)
sm = StateManager(project)
sm.create_task(...)  # Auto-saves, validates
```

Gradually migrate runners to use `StateManager` for all task operations.
