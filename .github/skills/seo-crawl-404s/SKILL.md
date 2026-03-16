---
name: seo-crawl-404s
description: Automated website crawler to find 404 errors via PageSeeds dashboard CLI.
---

# SEO Crawl 404 Detection

Fully automated crawler that finds broken links (404s) by crawling your sitemap and internal links. Part of the PageSeeds dashboard CLI - no external CI needed.

## What This Does

Crawls your website to find:
- **Internal 404s**: Broken links between your pages
- **Sitemap 404s**: URLs in sitemap that return 404
- **Orphan 404s**: Pages linked internally but deleted

Unlike pre-commit hooks, this catches:
- Production-only issues (build differences)
- URLs that worked when committed but broke later
- Legacy URLs from before pre-commit existed

## When to Use This

Use this workflow when:
- You want fully automated 404 detection
- Pre-commit hooks are inconsistent or missing issues
- You need to validate production site health
- You want scheduled 404 checks via PageSeeds scheduler

## Comparison: Crawler vs GSC Coverage vs Pre-commit

| Method | Automated | Finds Internal 404s | Finds External 404s | Catches Production Issues |
|--------|-----------|---------------------|---------------------|---------------------------|
| **Crawler** | ✅ Yes | ✅ Yes | ❌ No | ✅ Yes |
| **GSC Coverage** | ❌ Manual export | ✅ Yes | ✅ Yes | ✅ Yes |
| **Pre-commit** | ✅ Yes | ✅ Yes | ❌ No | ❌ No |

**Best practice**: Use crawler for weekly automated checks + GSC Coverage quarterly for external 404s.

## Quick Start

### Run via Dashboard CLI

```bash
pageseeds automation seo crawl-404s \
  --site https://www.example.com \
  --max-pages 500 \
  --max-depth 3
```

### Run via Dashboard UI

Create or run the "Crawl for 404s" task type. The crawler will:
1. Fetch your sitemap
2. Crawl all internal links (up to max-pages)
3. Check status codes
4. Create `fix_404_redirects` tasks for any 404s found

## Configuration

Default settings (balanced for most sites):

```bash
--max-pages 500      # Stop after 500 pages
--max-depth 3        # Follow links 3 levels deep
--workers 5          # 5 concurrent requests
--delay-ms 100       # 100ms between requests
--timeout 30         # 30 second request timeout
```

For larger sites, increase limits:

```bash
pageseeds automation seo crawl-404s \
  --site https://www.example.com \
  --max-pages 2000 \
  --max-depth 5 \
  --workers 10
```

## Output

Generated in `{repo}/.github/automation/output/crawl_404s/`:

- `{timestamp}_{site}_action_queue.json` - Full structured data
- `{timestamp}_{site}_fix_plan.md` - Human-readable fix plan
- `{timestamp}_{site}_summary.csv` - Quick review spreadsheet

## Scheduling via PageSeeds

Add to your orchestrator policy (`orchestrator_policy.json`):

```json
{
  "id": "crawl_404s_weekly",
  "task_type": "crawl_404s",
  "mode": "create_task",
  "cadence_hours": 168,
  "priority": "medium",
  "phase": "verification",
  "enabled": true
}
```

The PageSeeds scheduler will:
1. Create a "Crawl for 404s" task weekly
2. Run the crawler when task is executed
3. Create `fix_404_redirects` tasks for any 404s found

## Task Creation

The crawler creates one task per **source page** with broken links:

```
Fix 3 broken links on /blog/old-post
Fix 5 404s in sitemap/direct access
Fix 12 broken links on /tools/calculator
```

Each task includes:
- The source page where broken links were found
- List of broken URLs
- Priority (high if ≥5 broken links)

## How to Fix

### 1. Check if content moved

If `/blog/old-post` should redirect to `/blog/new-post`:

```javascript
// next.config.js
async redirects() {
  return [
    {
      source: '/blog/old-post',
      destination: '/blog/new-post',
      permanent: true,
    },
  ];
}
```

### 2. Fix internal links

If a page links to a deleted URL, update the link:

```markdown
<!-- Before -->
[Old tool](/tools/deleted-tool)

<!-- After -->
[New tool](/tools/current-tool)
```

### 3. Remove from sitemap

If content is intentionally deleted, remove from sitemap:

```xml
<!-- Remove this from sitemap.xml -->
<url>
  <loc>https://example.com/deleted-page</loc>
</url>
```

### 4. Bulk redirects for patterns

For multiple similar 404s, use pattern matching:

```javascript
// Redirect all /old-blog/* to /blog/*
{
  source: '/old-blog/:slug*',
  destination: '/blog/:slug*',
  permanent: true,
}
```

## CLI Reference

### Basic crawl

```bash
pageseeds automation seo crawl-404s --site https://www.example.com
```

### With custom sitemap

```bash
pageseeds automation seo crawl-404s \
  --site https://www.example.com \
  --sitemap-url https://www.example.com/sitemap-index.xml
```

### Limited crawl (faster)

```bash
pageseeds automation seo crawl-404s \
  --site https://www.example.com \
  --max-pages 100 \
  --max-depth 2
```

### Deep crawl (slower, thorough)

```bash
pageseeds automation seo crawl-404s \
  --site https://www.example.com \
  --max-pages 2000 \
  --max-depth 5 \
  --workers 10 \
  --delay-ms 50
```

## Troubleshooting

### "No sitemap found"

Ensure your manifest.json has a sitemap URL:
```json
{
  "url": "https://www.example.com",
  "sitemap": "https://www.example.com/sitemap.xml"
}
```

### Crawl too slow

Increase workers and decrease delay:
```bash
--workers 10 --delay-ms 50
```

### Missing some pages

Increase depth and pages:
```bash
--max-pages 2000 --max-depth 5
```

### Timeout errors

Increase timeout for slow pages:
```bash
--timeout 60
```

## Integration with PageSeeds Dashboard

The dashboard task runner (`collection.py`) now includes:

```python
def _collect_crawl_404s(self, task: Task) -> bool:
    """Run crawler to find 404 errors."""
    # Runs: pageseeds automation seo crawl-404s ...
    # Then creates fix_404_redirects tasks

def _create_tasks_from_crawl_404s(self, crawl_file: Path) -> int:
    """Parse crawl 404 results and create fix tasks."""
    # Creates one task per source page with broken links
```

## Limitations

The crawler **cannot** find:
- External backlinks (use GSC Coverage for these)
- URLs not linked internally or in sitemap
- JavaScript-rendered links (static HTML only)
- URLs behind authentication

## See Also

- `seo-coverage-404s` - For external 404s from GSC Coverage
- `seo-indexing-diagnostics` - For indexing status
- `seo-indexing-remediation` - For fixing non-indexed content
