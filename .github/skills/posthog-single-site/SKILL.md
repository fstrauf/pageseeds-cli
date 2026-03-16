---
name: posthog-single-site
description: Single-site PostHog analytics pull for repo-local usage (no multi-site registry required).
---

# PostHog Single-Site Analytics

## Purpose

Pull PostHog analytics for a single application/repo without requiring multi-site registry configuration. This is designed for repos that are themselves the application (like call-analyzer), not repos that manage multiple sites.

## Project Structure

Repo-local workspace:

- Workspace root: `automation/`
- PostHog config: `automation/posthog_config.json` (optional, for persistent settings)
- Output: `automation/output/posthog/`

## Configuration

### Option 1: Command-line flags (simplest)

```bash
pageseeds posthog report \
  --repo-root . \
  --project-id 12345 \
  --api-key-env POSTHOG_API_KEY \
  --dashboard-name "Main Dashboard" \
  --refresh
```

### Option 2: Config file in automation/ (for repeated runs)

Create `automation/posthog_config.json`:

```json
{
  "project_id": 12345,
  "api_key_env": "POSTHOG_API_KEY",
  "dashboard_names": ["Main Dashboard"],
  "base_url": "https://app.posthog.com"
}
```

Then run:
```bash
pageseeds posthog report --repo-root . --refresh
```

The CLI will auto-detect `automation/posthog_config.json` if present.

## Tooling

Use the centralized CLI wrapper:

```bash
# List your PostHog projects (to find project_id)
pageseeds posthog list-projects --repo-root . --api-key-env POSTHOG_API_KEY

# List dashboards for a project
pageseeds posthog list-dashboards --repo-root . --project-id 12345 --api-key-env POSTHOG_API_KEY

# Pull analytics report
pageseeds posthog report --repo-root . --project-id 12345 --api-key-env POSTHOG_API_KEY --refresh

# Generate action queue from insights
pageseeds posthog action-queue --repo-root . --write-md

# Disable incomplete data detection (if you want current day's partial data)
pageseeds posthog report --repo-root . --no-skip-incomplete
```

## Authentication

PostHog API keys are auto-resolved from (in order):

1. Environment variables (already set in shell)
2. `~/.config/pageseeds/secrets.env` (preferred machine-local location)
3. Repo-local `.env` in current working directory

Required: Environment variable containing your PostHog API key (e.g., `POSTHOG_API_KEY`)

## Workflow

### Step 1: Get PostHog credentials

Ensure you have:
- PostHog project ID (numeric)
- PostHog API key (personal API key, not the public project key)

Set the API key in `~/.config/pageseeds/secrets.env`:
```
POSTHOG_API_KEY=phx_...
```

### Step 2: Discover project info (first time)

```bash
# List projects to confirm access
pageseeds posthog list-projects --repo-root . --api-key-env POSTHOG_API_KEY

# List dashboards to find which to pull
pageseeds posthog list-dashboards --repo-root . --project-id <ID> --api-key-env POSTHOG_API_KEY
```

### Step 3: Configure (optional but recommended)

Create `automation/posthog_config.json` with your project details:

```json
{
  "project_id": 12345,
  "api_key_env": "POSTHOG_API_KEY",
  "dashboard_names": ["Main Dashboard"]
}
```

### Step 4: Run the report

With config file:
```bash
pageseeds posthog report --repo-root . --refresh
```

Or with flags:
```bash
pageseeds posthog report \
  --repo-root . \
  --project-id 12345 \
  --api-key-env POSTHOG_API_KEY \
  --refresh
```

**Note on incomplete data**: PostHog shows current-day data as a dotted line when incomplete. The CLI automatically detects this (if last value is < 60% of recent average, it uses the previous complete day instead). This prevents false "dramatic drop" alerts. To disable this and use partial current-day data, add `--no-skip-incomplete`.

### Step 5: Review outputs

Check generated files in `automation/output/posthog/`:
- `<date>_summary.md` - Executive summary with key metrics
- `<site>_<date>_insights.json` - Full data for programmatic use
- `<date>_action_queue.md` - Prioritized recommendations

### Step 6: View specific fields (no custom code)

Use the `view` command to extract specific fields without writing Python/jq:

```bash
# View situations detected by rules
pageseeds posthog view --field situations

# View action candidates
pageseeds posthog view --field action_candidates

# View insights with values
pageseeds posthog view --field insights

# View page traffic
pageseeds posthog view --field page_traffic

# View breakdown values (referring domains, browsers, etc.)
pageseeds posthog view --field breakdowns

# JSON format for programmatic use
pageseeds posthog view --field situations --format json
```

**DO NOT** write ad-hoc Python scripts to parse the JSON files. Use the `view` command.

### Step 7: Build action queue

```bash
pageseeds posthog action-queue --repo-root . --write-md
```

## Guardrails

- Do not commit API keys to the repo
- Start with small limits if you have many insights
- URL Inspection quotas are limited; use refresh sparingly
- Use only the predefined CLI path for analytics pulls

## Comparison to Multi-Site Workflow

| | Single-Site (this skill) | Multi-Site (posthog-product-insights) |
|---|---|---|
| Use case | One app per repo | Managing multiple sites from one repo |
| Config location | `automation/posthog_config.json` | `general/<site>/manifest.json` |
| Discovery | Single config file | Auto-scans `general/` directory |
| Registry required | No | No (auto-discovers from filesystem) |
| Best for | call-analyzer, single apps | expense, coffee, multi-site operations |
