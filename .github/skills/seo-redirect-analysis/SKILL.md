---
name: seo-redirect-analysis
description: Process GSC "Page with redirect" reports to identify and fix redirect issues.
---

# SEO Redirect Analysis

Process Google Search Console "Page with redirect" reports to identify problematic redirects that waste crawl budget or indicate site architecture issues.

## What This Does

Analyzes GSC "Page with redirect" data to find:
- **Redirects in sitemap** (CRITICAL) - Wastes crawl budget
- **HTTP→HTTPS redirects** - Normal but shouldn't be in sitemap
- **Non-www→www redirects** - Normal but shouldn't be in sitemap  
- **Old content redirects** - Moved/deleted pages
- **Redirect chains** - Multiple hops (inefficient)

## Why This Matters

| Issue | Impact |
|-------|--------|
| Redirects in sitemap | Wastes Google's crawl budget on useless URLs |
| Internal links to redirected URLs | Slower page load, wasted link equity |
| Redirect chains | Poor user experience, diluted SEO value |
| Unnecessary redirects | Confusing signals to search engines |

## Quick Start

### 1. Export from GSC

1. Go to [Google Search Console](https://search.google.com/search-console)
2. Select your property
3. Go to **Coverage** → **Page with redirect**
4. Click **EXPORT** → Download CSV
5. Save to: `{repo}/.github/automation/page_with_redirect.csv`

### 2. Process via CLI

```bash
pageseeds automation seo gsc-redirect-analysis \
  --csv-file .github/automation/page_with_redirect.csv \
  --site https://www.daystoexpiry.com
```

### 3. Review Tasks Created

The system creates tasks like:
- `🚨 Remove 5 redirects from sitemap` (HIGH priority)
- `Fix 12 canonicalization redirects` (NORMAL priority)
- `Fix 3 moved_content redirects` (NORMAL priority)

## Redirect Types Detected

| Type | Description | Priority | Action |
|------|-------------|----------|--------|
| **canonicalization** | HTTP→HTTPS, non-www→www | Normal | Ensure redirects work; remove from sitemap |
| **moved_content** | Old URLs that moved | Medium | Update internal links; verify redirect target |
| **parameter_variation** | URLs with query params | Low | Review if params needed; canonicalize |
| **unknown** | Unclassified redirects | Low | Manual review needed |

## Critical Issue: Redirects in Sitemap

**This is the #1 issue to fix.** 

When Google sees a redirect URL in your sitemap, it:
1. Wastes crawl budget on useless URLs
2. Gets confused about which URL is canonical
3. May not index the final destination properly

### How to Fix

Remove redirect URLs from `sitemap.xml`:

```xml
<!-- REMOVE these: -->
<url>
  <loc>http://daystoexpiry.com/</loc>  <!-- redirects to HTTPS -->
</url>
<url>
  <loc>https://daystoexpiry.com/</loc>  <!-- redirects to www -->
</url>

<!-- KEEP only the final destination: -->
<url>
  <loc>https://www.daystoexpiry.com/</loc>
</url>
```

### Next.js Sitemap Fix

If using `next-sitemap`, ensure it generates correct URLs:

```javascript
// next-sitemap.config.js
module.exports = {
  siteUrl: 'https://www.daystoexpiry.com',  // Use www + HTTPS
  generateIndexSitemap: false,
  // ...
}
```

## Scheduling

Add to `orchestrator_policy.json`:

```json
{
  "id": "redirect_analysis_monthly",
  "task_type": "gsc_redirect_analysis",
  "mode": "create_task",
  "cadence_hours": 720,
  "priority": "medium",
  "phase": "verification",
  "enabled": true
}
```

## CLI Reference

### Basic analysis

```bash
pageseeds automation seo gsc-redirect-analysis \
  --csv-file page_with_redirect.csv \
  --site https://www.daystoexpiry.com
```

### With custom output

```bash
pageseeds automation seo gsc-redirect-analysis \
  --csv-file page_with_redirect.csv \
  --site https://www.daystoexpiry.com \
  --out-dir ./output
```

## Output Files

Generated in `.github/automation/output/gsc_redirects/`:

- `redirect_analysis_{timestamp}_{site}_action_queue.json` - Full data
- `redirect_analysis_{timestamp}_{site}_fix_plan.md` - Human-readable report
- `redirect_analysis_{timestamp}_{site}_summary.csv` - Spreadsheet format

## Task Creation

Tasks are created by priority:

1. **🚨 CRITICAL**: Redirects in sitemap (fix immediately)
2. **Medium**: Moved content redirects (review redirects)
3. **Normal**: Canonicalization redirects (remove from sitemap)

## How to Fix Redirects

### 1. Remove from Sitemap (Critical)

```bash
# Edit sitemap.xml or regenerate with correct URLs
# Only include final destination URLs
```

### 2. Update Internal Links

Find links pointing to redirect URLs:

```bash
# Example: Find links to HTTP version
grep -r "http://daystoexpiry.com" src/
```

Update to final destination:

```markdown
<!-- Before -->
[Link](http://daystoexpiry.com/page)

<!-- After -->
[Link](https://www.daystoexpiry.com/page)
```

### 3. Fix Redirect Chains

A → B → C should be A → C directly:

```javascript
// Before (chain)
/old-page → /blog/old-page → /blog/new-page

// After (direct)
/old-page → /blog/new-page
```

## Troubleshooting

### "No redirect CSV found"

Export from GSC Coverage > Page with redirect and save as:
```
{repo}/.github/automation/page_with_redirect.csv
```

### All redirects are "canonicalization"

This is normal! Just ensure they're not in your sitemap.

### Redirects keep appearing

Check:
1. Sitemap generator config (use correct base URL)
2. Internal links (update to final URLs)
3. External backlinks (can't control, but monitor)

## Comparison: Redirects vs 404s vs Coverage

| Report | What It Shows | Priority |
|--------|---------------|----------|
| **Page with redirect** | URLs that redirect (waste crawl budget) | Medium-High |
| **Not found (404)** | Broken URLs (bad UX) | High |
| **Crawled - currently not indexed** | Quality issues | High |

**Recommendation**: Fix 404s first, then redirects, then indexing issues.

## See Also

- `seo-crawl-404s` - Find broken internal links
- `seo-coverage-404s` - Process GSC 404 exports
- `seo-indexing-diagnostics` - Check indexing status
