---
name: posthog-product-insights
description: Multi-site PostHog analytics pull + normalization + action recommendations grounded in this repo's project manifests/briefs.
---

# PostHog Product Insights

## Purpose

Pull consistent product analytics across all sites you operate, then produce a single prioritized action queue that is grounded in this repo’s project context (positioning, audiences, content pillars, and known workflows like SEO/Reddit).

This is designed for the case: "I run multiple sites, I don't want to sift dashboards, I want an agent to tell me what to do next."

## Inputs (Repo Context)

Multi-site mode (recommended):

- `general/<project>/manifest.json` (primary: URL + positioning; add PostHog config here)
- `general/<project>/*seo*_brief*.md` (positioning + target audience + content pillars)
- `general/<project>/articles.json` (optional: content backlog state)
- The CLI auto-discovers all manifests under `general/` with PostHog config

Single-site mode (one-off):

- Existing repo context files (readme/brief/content as available)
- PostHog access via one-off command flags (`--project-id`, `--api-key-env`, optional dashboards/insights)

Secrets:

- PostHog API keys must be passed via env vars (never committed).

## Configuration (Required)

Add a `analytics.posthog` block to each site’s `general/<project>/manifest.json`.

Minimal schema:

```json
{
  "analytics": {
    "posthog": {
      "base_url": "https://app.posthog.com",
      "project_id": 12345,
      "api_key_env": "POSTHOG_API_KEY_EXPENSE",
      "dashboard_names": ["Main Dashboard"],
      "insights": {
        "north_star": 111,
        "dau": 222
      },
      "pages": {
        "top_n": 10
      }
    }
  }
}
```

Notes:

- You can configure **either**:
  - `dashboard_names`: the script will discover that dashboard by name and pull all tile insights (no manual insight IDs), or
  - `insights`: explicit saved insight IDs.
- If you configure neither `dashboard_names` nor `insights`, the script will fall back to pinned dashboards (then the first dashboard) and pull those tiles. Use `--extra-insights` to sample additional saved insights.
- `insights` should point to **saved** insights in PostHog (trend/funnel/retention/HogQL/etc.). Name keys are for your workflow readability.
- `pages.top_n` controls how many page rows the script returns per site (best-effort from insight series labels; defaults to 10).
- If you run self-hosted PostHog, set `base_url` to that domain.
- `api_key_env` is the env var name that contains the API key for *that* site’s PostHog project.

## Tooling

Use the repo script (standard library only):

- `tools/posthog_help/posthog_report.py`
- `tools/posthog_help/posthog_action_queue.py`

Primary usage (multi-site, auto-discovers manifests):

```bash
automation-cli posthog report --repo-root . --refresh
```

Single-site usage (one-off):

```bash
automation-cli posthog report --repo-root . --project-id <id> --api-key-env POSTHOG --refresh
```

Project discovery (when setting `project_id` values):

```bash
automation-cli posthog list-projects --repo-root . --api-key-env POSTHOG
automation-cli posthog list-dashboards --repo-root . --project-id <id> --api-key-env POSTHOG
```

Tip: `--env-file` is optional. Secrets are auto-resolved from environment, machine-local secrets file, and repo/automation fallbacks.

This writes:

- `output/posthog/<YYYY-MM-DD>_summary.md`
- `output/posthog/<site_id>_<YYYY-MM-DD>_insights.json` (insights + dashboard inventory + page traffic + rule-first action candidates per site)

## Workflow

### Step 1: Determine Scope

- Default: Auto-discover manifests from `general/` directory (each folder with a `manifest.json` containing PostHog config becomes a site).
- For single-site: Use one-off mode (`--project-id` + `--api-key-env`).
- Do not create `.env` or manifest files as part of normal execution.
- If required config is missing, fail fast and report exactly which argument/env is missing.

### Step 2: Pull PostHog Data (Saved Insights + Dashboards + Page Signals)

Run:

```bash
# Multi-site (auto-discovers manifests):
automation-cli posthog report --repo-root . --refresh

# Single-site:
automation-cli posthog report --repo-root . --project-id <id> --api-key-env POSTHOG --refresh

# Disable incomplete data detection (use partial current-day data)
automation-cli posthog report --repo-root . --no-skip-incomplete
```

Data contract:

- For each `insights.<key> = <insight_id>`, fetch:
  - `GET /api/projects/{project_id}/insights/{insight_id}?refresh=true` (when `--refresh`)
- Also fetch dashboard inventory:
  - `GET /api/projects/{project_id}/dashboards/`
- Persist per-site JSON to `output/posthog/` (so later steps can be deterministic and reproducible).
- Build best-effort page traffic rows by extracting URL/path-like series labels from returned insight data.

### Step 3: Normalize Into an "Analytics Packet"

Transform each site’s raw insights into a compact packet an agent can reason over:

- **Topline**: DAU/WAU/MAU (or your north-star series), and WoW delta
- **Acquisition**: top referrers / UTM sources (and biggest movers WoW)
- **Activation**: signup/onboarding funnel step conversions (highlight worst drop-off)
- **Retention**: D1/D7/D30 (or chosen retention metric), and change vs previous period
- **Pages**: top pages from available insight breakdown series (URL/path labels) with latest values
- **Dashboards**: dashboard inventory snapshot (id/name/pinned/last-modified)
- **Content/SEO context (optional)**: drafts/ready_to_publish counts from `articles.json`

If an insight returns empty or missing fields:

- Treat it as either (a) "no traffic" or (b) "instrumentation drift".
- Prefer "instrumentation drift" when other insights have normal volume but one critical funnel is empty.

### Step 4: Derive Situations (Rule-First)

Before any LLM-style reasoning, classify each site into 1–3 situations using deterministic rules:

- **Acquisition drop**: traffic metric down >20% WoW and conversion rate stable
- **Conversion drop**: traffic stable but signup/activation conversion down >20% WoW
- **Activation bottleneck**: largest funnel step drop-off worsened WoW or is >2x other steps
- **Retention decay**: D7 down materially (define threshold) while activation stable
- **Channel opportunity**: one referrer/source up materially with acceptable conversion
- **Tracking issue**: critical insight empty/flatline or the series breaks abruptly

Store:

- Situation label
- Evidence (which insight + metric + delta)
- Confidence (High/Med/Low) based on data completeness

Script output now includes deterministic first-pass classifications in `situations` and `action_candidates`.
Agent should refine these with project context rather than ignoring them.

### Step 5: Recommend Actions (Repo-Grounded)

Generate actions that are:

- concrete
- scoped
- tied to a specific metric and expected impact
- mapped to an execution surface in your ecosystem:
  - marketing ops (SEO/Reddit workflows in this repo)
  - product engineering work (create an issue in the site’s `source_repo_local_path`)
  - instrumentation fixes (PostHog event/schema)

Action mapping rules:

- If **Acquisition drop** and referrers show SEO decline:
  - Run SEO diagnostics (`seo-indexing-diagnostics`) for that site and fix indexing buckets.
- If **Acquisition drop** but referrers show paid/social decline:
  - Pause low-performing campaigns, reallocate to the best channel, and validate landing page performance.
- If **Conversion drop**:
  - Review the top landing pages driving signups; ship 1–2 landing page improvements and rerun funnel.
- If **Activation bottleneck**:
  - Identify the worst step; propose 1 UX fix + 1 instrumentation improvement; optionally add feature flag experiment.
- If **Retention decay**:
  - Identify "aha moment" event; propose lifecycle nudges (email/in-app) and one product capability improvement.
- If **Channel opportunity**:
  - Double down: create content/features that match that channel’s audience and landing intent.
- If **Tracking issue**:
  - Create a task to audit event names/properties; add a "tracking health" insight (events per day, distinct users).

Each action must include:

- `project`
- `priority` (P0/P1/P2)
- `owner_surface` (automation-repo workflow vs source repo engineering vs PostHog config)
- `expected_impact`
- `evidence` (metric + delta + time window)
- `next_step` (a command to run, or a concrete repo change)

### Step 6: View Extracted Fields (No Custom Code)

Use the `view` command to extract specific fields from the latest insights JSON without writing Python/jq:

```bash
# View situations detected by rules
automation-cli posthog view --field situations

# View action candidates  
automation-cli posthog view --field action_candidates

# View insights with latest values
automation-cli posthog view --field insights

# View page traffic
automation-cli posthog view --field page_traffic

# View breakdown values (referring domains, browsers, etc.)
automation-cli posthog view --field breakdowns

# JSON output for programmatic use
automation-cli posthog view --field situations --format json
```

**Rule**: DO NOT write ad-hoc Python/jq to parse JSON files. Use `automation-cli posthog view`.

### Step 7: Produce Deliverables

Primary deliverable: `output/posthog/<YYYY-MM-DD>_summary.md` with:

1. Cross-site summary table:
   - Site
   - Topline metric latest + WoW
   - Biggest risk (situation)
   - Biggest opportunity (situation)
   - Recommended next action (one-liner)
2. Prioritized action queue (top 5–15 actions total)
3. Per-site section:
   - 3–6 bullet observations (with evidence)
   - 3–5 actions (with priority + owner surface)
4. Tracking/config gaps:
   - Sites missing PostHog config
   - Insights failing to return data

Per-site machine-readable deliverable (`<site_id>_<date>_insights.json`) includes:

- `insights`: pulled insight records + lightweight trend deltas
- `dashboards`: dashboard inventory metadata
- `page_traffic`: top page rows extracted from insight series labels
- `situations`: deterministic rule-first labels with evidence
- `action_candidates`: deterministic action stubs for agent refinement

Then build the deterministic cross-site action queue:

```bash
automation-cli posthog action-queue --repo-root . --write-md
```

This writes:

- `output/posthog/<YYYY-MM-DD>_action_queue.json`
- `output/posthog/<YYYY-MM-DD>_action_queue.md`

### Step 7: Agent Interpretation Pass

Use the JSON packets as the primary source and generate final recommendations by:

1. Confirming each suggested action has direct metric evidence (`insight`, `delta`, window).
2. Translating generic actions into concrete repo next steps (commands or code-change targets).
3. Prioritizing by impact and confidence:
   - P0: tracking blind spots / broken analytics
   - P1: clear regressions in acquisition/conversion/retention
   - P2: opportunities and optimization tasks
4. Producing a single cross-site queue (5-15 tasks) with no duplicates.

## Guardrails

- Do not overfit to one-day noise; prefer 7-day windows and WoW deltas.
- Don’t recommend shipping product changes from analytics alone without:
  - the specific funnel step evidence, and
  - at least one confirmation step (session recording review, survey, or a quick user test).
- Do not propose actions that require secrets to be committed; use env vars only.
- If metrics disagree (e.g., DAU up but signups down hard), call it out as a likely instrumentation mismatch or segmentation issue.
