# SEO Content (CLI-first)

## ⚠️ MCP server is deprecated in this repo

This workspace is **CLI-first**. Run the Python code directly via `uv run` (no MCP server process).

Common commands:

```bash
uv run --directory packages/seo-content-cli seo-content-cli --help
uv run --directory packages/seo-content-cli seo-content-cli articles-summary --website-path general/expense
```

---

# SEO Content MCP Server (legacy)

A Model Context Protocol (MCP) server for managing SEO content lifecycle, including:
- Article synchronization with articles.json
- Smart date distribution to avoid clustering
- Content quality validation and cleaning
- Batch operations across multiple websites

## Canonical workflow docs

For the end-to-end system (automation vs production repos, what is mutable, safe deploy rules), see:

- `CONTENT_SYSTEM.md` (at the automation repo root)

## Features

### ✅ Test Distribution (Read-only)
- Preview how articles would be distributed across dates
- Test different scenarios without making changes
- Visualize distribution patterns

### ✅ Content Quality
- **Validate Content** - Check for issues without making changes
- **Clean Content** - Fix duplicate title headings and date mismatches
- Sync dates between articles.json and markdown frontmatter
- Remove duplicate H1 headings that match the title

### Article Sync (Coming soon)
- Sync articles.json with markdown content files
- Extract frontmatter metadata
- Update word counts and dates

### Date Distribution (Coming soon)
- Analyze article dates for issues
- Fix future dates and overlapping dates
- Smart redistribution of recent articles

## Installation

```bash
cd packages/seo-content-cli
uv sync
```

## Usage

### Legacy: MCP client setup (not used by this repo workflows)

If you still want to run this as an MCP server in another context, add to your MCP settings:

```json
{
  "mcpServers": {
    "seo-content": {
      "command": "uv",
      "args": [
        "--directory",
        "packages/seo-content-cli",
        "run",
        "seo-content-mcp"
      ],
      "env": {
        "WORKSPACE_ROOT": "<path-to-your-automation-repo>"
      }
    }
  }
}
```

Or copy the configuration from `claude_desktop_config.json`.

## Tools

### `seo_test_distribution`
Test date distribution for articles without making changes.

**Arguments:**
- `project_name` (string): Name of the project (e.g., "coffee", "expense")
- `article_count` (integer): Number of articles to distribute
- `earliest_date` (string): Earliest date in YYYY-MM-DD format

**Returns:** Distribution preview showing how articles would be spread across dates

### `seo_validate_content`
Validate content files without making changes. Reports issues found.

**Arguments:**
- `website_path` (string): Relative path to website (e.g., "general/coffee")

**Returns:** Validation report showing:
- Duplicate title headings (H1 that matches frontmatter title)
- Date mismatches between articles.json and markdown frontmatter
- Missing frontmatter

### `seo_clean_content`
Clean content files by fixing issues. **Makes actual file changes.**

**Arguments:**
- `website_path` (string): Relative path to website (e.g., "general/coffee")

**Returns:** Cleaning report showing what was fixed:
- Removes duplicate title headings
- Syncs dates from articles.json to markdown frontmatter
- Reports number of issues fixed

### `seo_analyze_dates`
Analyze article dates to find issues without making changes.

**Arguments:**
- `website_path` (string): Relative path to website (e.g., "general/coffee")

**Returns:** Analysis report showing:
- Total, past, and recent article counts
- Date issues (future dates, missing dates, invalid formats)
- Overlapping dates (multiple articles on same day)
- Recent article date range and distribution

### `seo_fix_dates`
Fix date issues by redistributing recent articles. **Makes actual file changes.**

**Arguments:**
- `website_path` (string): Relative path to website (e.g., "general/coffee")

**Returns:** Fix report showing:
- Number of articles fixed
- Before/after dates for each change
- New distribution details (range, spacing, uniqueness)
- Only affects articles from last 7 days

## SEO Ops tools (mirrors the Flask UI)

These tools read `WEBSITES_REGISTRY.json` and expose the same operational views/actions as the web UI
in `mcp/reddit-db-mcp` (overview, per-site metrics, drift, repo import, date analysis/scheduling, and
AI-friendly Markdown reports).

### `seo_ops_overview`
Multi-site overview (counts, latest published, issue totals). Read-only.

### `seo_ops_site_metrics`
Per-site metrics for a single `website_id`. Read-only.

### `seo_ops_drift`
Compute drift between automation `content/` and the real repo content dir by basename + sha256.
Read-only.

### `seo_ops_import_preview`
Preview syncing automation `articles.json` from repo frontmatter. Read-only.

### `seo_ops_import_apply`
Apply syncing automation `articles.json` from repo frontmatter. Writes automation only (repo stays read-only).

### `seo_ops_dates_analyze`
Analyze automation-side dates (future/missing/bad/overlaps). Read-only.

### `seo_ops_schedule_preview`
Preview draft-safe date scheduling for automation-side articles. Read-only.

Arguments:
- `website_id` (string, required)
- `spacing_days` (integer, default: 2)
- `statuses` (string[], default: ["ready_to_publish"]): Only schedule articles with these statuses

### `seo_ops_schedule_apply`
Apply draft-safe date scheduling: updates automation `articles.json` + automation content frontmatter. Repo stays read-only.

Arguments:
- `website_id` (string, required)
- `spacing_days` (integer, default: 2)
- `statuses` (string[], default: ["ready_to_publish"]): Only schedule articles with these statuses

### `seo_ops_report_overview_markdown`
Generate an AI-friendly Markdown overview report across all sites. Read-only.

### `seo_ops_report_site_markdown`
Generate an AI-friendly per-site Markdown report. Read-only (unless you call apply tools).

### `seo_ops_validate_index`
Validate `articles.json` entries against both automation content files and the real repo content dir.
Useful for catching index entries that are missing in BOTH places (and therefore can never have dates).
Read-only.

### `seo_ops_sync_and_optimize` 🚀 NEW UNIFIED WORKFLOW
**The all-in-one tool for content sync and optimization.**

Orchestrates the complete workflow treating production repo as source of truth:
1. **Import from production** - Sync dates/metadata from production repo
2. **Analyze dates** - Detect future dates, overlaps, poor distribution
3. **Schedule dates (automation-only)** - Redistribute dates for *mutable* (not-in-production) articles (if auto_fix enabled)
4. **Check drift** - Identify new files missing in production, plus mismatches that require review
5. **Validate** - Ensure content is ready
6. **Deploy (optional)** - Copy *new* files to production (if auto_deploy enabled)

**Arguments:**
- `website_id` (string, required): Website ID from WEBSITES_REGISTRY.json
- `auto_fix` (boolean, default: false): Apply date fixes if true and dry_run is false
- `spacing_days` (integer, default: 2): Days to space between redistributed articles
- `max_recent_days` (integer, default: 7): Reserved for future use (currently scheduling is based on "mutable" logic)
- `dry_run` (boolean, default: true): Safety check - prevents changes even if auto_fix is true
- `auto_deploy` (boolean, default: false): If true (and dry_run false), copy new files missing in production into the production repo
- `target_statuses` (string[], default: ["ready_to_publish"]): Statuses eligible for scheduling and deploy filtering

**Returns:** Structured JSON with:
- Phase results (import_sync, date_analysis, date_optimization, drift_check, validation)
- Summary (articles_in_sync, date_issues_found, files_ready_to_push, validation_errors)
- Recommended actions (what to do next)
- Deployment instructions (which files to copy where)

**Notes:**
- Date scheduling can be filtered; default is `ready_to_publish`.
- Drift mismatches indicate repo-present files differ; they should be reviewed and are not auto-deployed by default.

**Usage Examples:**

Preview mode (default - read-only):
```json
{
  "website_id": "days_to_expiry"
}
```

Apply mode (sync and fix):
```json
{
  "website_id": "days_to_expiry",
  "auto_fix": true,
  "dry_run": false
}
```

**Agent-Friendly Features:**
- Structured phase outputs for parsing
- Clear status for each phase (completed/skipped/error)
- Actionable recommendations
- Deployment instructions with file paths
- Error messages include suggestions

## Development

```bash
# Install in development mode
pip install -e .

# Run the server
seo-content-mcp
```

## License

MIT
