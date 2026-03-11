---
name: seo-indexing-diagnostics
description: Diagnose "Why pages aren't indexed" using Search Console URL Inspection across sitemap URLs; group root causes and generate a fix plan.
---

# SEO Indexing Diagnostics (Search Console)

## What This Does (And What It Can't)

Goal: identify why specific URLs are not indexed by pulling URL Inspection results from Google Search Console, grouping causes, and producing an actionable fix plan.

Important constraint: Search Console’s **Pages / Page indexing** report (“Why pages aren’t indexed”) is not available as a bulk export via the Search Console API. The API can:

- list accessible properties (`sites.list`)
- run performance queries (`searchanalytics.query`)
- inspect a **specific URL** (`urlInspection.index.inspect`)

So "retrieve everything" means: fetch a list of candidate URLs (usually from the site’s sitemap), then inspect each URL.

## Inputs

Repo-local:

- Sitemap URL (recommended): pass `--sitemap-url https://example.com/sitemap.xml`
- Search Console property (recommended): pass `--site sc-domain:example.com` (or a URL-prefix property)
- Optional: `--urls-file automation/urls_to_inspect.txt` (newline-delimited)

Credentials:

- Preferred: service account JSON key that has access to the Search Console property
- Fallback order used by the tool (no prompt needed in target repos):
  1) `--service-account-path`
  2) `GOOGLE_APPLICATION_CREDENTIALS` (when it points to a service-account JSON)
  3) `~/.config/automation/secrets.env` (`GSC_SERVICE_ACCOUNT_PATH` or `GOOGLE_APPLICATION_CREDENTIALS`)
  4) `/path/to/automation/.env` (`GSC_SERVICE_ACCOUNT_PATH` or `GOOGLE_APPLICATION_CREDENTIALS`)
  5) a single service-account JSON detected in `/path/to/automation/*.json`
- Optional OAuth mode: `--oauth-client-secrets`, `GSC_REPORT_OAUTH_CLIENT_SECRETS`, or matching keys in the same env files

## Tooling

Use the centralized CLI wrapper (tool code lives in the automation repo):

- `automation-cli seo gsc-indexing-report`

It will:

1. Fetch a sitemap (default: `<manifest.url>/sitemap.xml`, with fallback filenames).
2. Inspect URLs via URL Inspection API.
3. Write outputs under `automation/output/gsc_indexing/`:
   - `..._results.json`
   - `..._results.csv`
   - `..._summary.md`
   - `..._fix_plan.md` (deterministic bucketed fix plan; use this first)
   - `..._action_queue.json` + `..._action_queue.md` (deterministic remediation queue; use this for Step 7)

## Workflow

### Step 1: Run the indexing pull

Run from the repo root:

```bash
automation-cli seo gsc-indexing-report \
  --site sc-domain:example.com \
  --sitemap-url https://example.com/sitemap.xml
```

If you need to re-run with an explicit Search Console property:

- Domain property: `sc-domain:example.com`
- URL-prefix property: `https://www.example.com/`

```bash
automation-cli seo gsc-indexing-report \
  --site sc-domain:example.com \
  --sitemap-url https://example.com/sitemap.xml
```

### Step 2: Triage by buckets (what to fix first)

Use the generated `..._fix_plan.md` as the primary dashboard. It is deterministic and already bucketed.

If you need a compact overview, use `..._summary.md`. Focus on **non-indexed** buckets first, typically:

- `verdict != PASS`
- or `indexingState` / `coverageState` indicates excluded or not indexed

Prioritize buckets that:

- affect many URLs (high count)
- are fixable via templates/config (robots, canonical, redirects, noindex)
- are sitemap hygiene issues (wrong URLs, 404s, duplicates)

### Step 3: Map buckets to fixes (common patterns)

Use URL Inspection fields to drive actions:

- `robotsTxtState`, `pageFetchState`, `crawlAllowed`, `indexingAllowed`
- `userCanonical` vs `googleCanonical` (canonical conflicts)
- `coverageState` / `indexingState` (Google’s reason strings)
- `lastCrawlTime` (staleness)

Common fixes:

- **Submitted URL marked ‘noindex’ / indexingAllowed=false**: remove `noindex` or fix conditional meta tags.
- **Blocked by robots.txt / crawlAllowed=false**: adjust robots rules; ensure critical paths are allowed.
- **Duplicate / canonical mismatch**: fix canonical tags, redirects, and internal linking to consolidate to the preferred URL.
- **Alternate page with proper canonical**: remove from sitemap if it is intentionally alternate; ensure sitemap only lists canonical URLs.
- **Soft 404 / Not found / server errors**: fix routing, generate the page, or remove from sitemap.
- **Discovered/Crawled - currently not indexed**: improve internal links, ensure unique value, avoid thin/duplicate pages, verify rendering, reduce parameters, and ensure sitemap freshness.

### Step 4: Produce a fix plan

Deliverable should include:

- A table of the top “not indexed” buckets with counts.
- For each bucket: likely root cause, how to confirm, and the concrete fix (files/config to change, or sitemap change).
- A short “verify” section: how to rerun the inspection after fixes.

## Guardrails

- Do not assume sitemap URLs are correct; treat sitemap as a hypothesis that needs validation.
- Avoid giant runs first. Start with a limit (e.g. 200–500 URLs), verify correctness, then scale up.
- URL Inspection quotas are limited; re-check only the affected URLs after you implement fixes.
- Use only the predefined CLI path for Step 6 (`automation-cli seo gsc-indexing-report` and related `automation-cli seo ...` selectors).
- Do not call `seo-content-mcp` or other MCP servers for Step 6 discovery/routing.
- Resolve site/sitemap from explicit args and repo-local files (manifest/workspace config). If missing, stop and return a clear command asking for `--site` and `--sitemap-url` rather than using alternative tool paths.
