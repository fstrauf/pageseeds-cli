# External Use: Google Search Console Integration

**Copy this guide into other repositories** to enable AI agents to interact with Google Search Console via the centralized automation tooling.

---

## Quick Setup (5 minutes)

### 1. Install the CLI

```bash
# From the repo you want to use GSC in
pip install /path/to/automation/packages/pageseeds
```

Or with `uv`:
```bash
uv pip install /path/to/automation/packages/pageseeds
```

### 2. Set Up Credentials

**Option A: Service Account (Recommended)**

```bash
# Set environment variable
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
```

Or create `~/.config/automation/secrets.env`:
```bash
GSC_SERVICE_ACCOUNT_PATH=/path/to/service-account-key.json
```

**Option B: OAuth (Interactive)**

```bash
export GSC_REPORT_OAUTH_CLIENT_SECRETS=/path/to/oauth-client-secrets.json
```

### 3. Create Manifest (Optional but Recommended)

Create `automation/manifest.json`:

```json
{
  "website": "my-site-id",
  "url": "https://example.com",
  "gsc_site": "sc-domain:example.com",
  "sitemap": "https://example.com/sitemap.xml"
}
```

---

## Common Commands

### List Available GSC Sites

```bash
pageseeds automation seo gsc-indexing-report --list-sites
```

### Run Full Indexing Report

```bash
# With manifest
pageseeds automation seo gsc-indexing-report --manifest automation/manifest.json

# Or explicit parameters
pageseeds automation seo gsc-indexing-report \
  --site sc-domain:example.com \
  --sitemap-url https://example.com/sitemap.xml \
  --limit 200 \
  --workers 2
```

### Inspect Specific URLs

```bash
pageseeds automation seo gsc-indexing-report \
  --site sc-domain:example.com \
  --urls-file urls_to_check.txt \
  --limit 50
```

### Get Page-Specific Context

```bash
pageseeds automation seo gsc-page-context \
  --site sc-domain:example.com \
  --url https://example.com/specific-page
```

---

## Understanding Output

Reports are written to `automation/output/gsc_indexing/`:

| File | Purpose |
|------|---------|
| `*_action_queue.json` | **Primary** - Process this programmatically |
| `*_results.json` | Full inspection data |
| `*_summary.md` | Human-readable summary |
| `*_fix_plan.md` | Actionable recommendations |
| `*.csv` | Spreadsheet export |

### Action Queue JSON Structure

```json
{
  "meta": {
    "run_ts": "20250224_064358",
    "site_url": "sc-domain:example.com"
  },
  "counts": {
    "total_items": 150,
    "mapped_to_article": 120,
    "non_indexed_items": 25
  },
  "items": [
    {
      "priority": 10,
      "reason_code": "robots_blocked",
      "action": "Fix robots.txt / crawl allow; remove blocked URLs from sitemap until fixed.",
      "url": "https://example.com/page",
      "path": "/page",
      "verdict": "FAIL",
      "coverageState": "Excluded by 'noindex' tag",
      "indexingState": "INDEXING_ALLOWED",
      "robotsTxtState": "BLOCKED",
      "crawlAllowed": false,
      "indexingAllowed": true,
      "lastCrawlTime": "2025-02-20T12:34:56Z",
      "userCanonical": "https://example.com/page",
      "googleCanonical": "https://example.com/page",
      "mapped_to_article": true,
      "article": {
        "id": 42,
        "url_slug": "page",
        "status": "published",
        "file": "content/page.mdx",
        "basename": "page.mdx",
        "title": "Page Title"
      }
    }
  ]
}
```

### Reason Codes Reference

| Code | Priority | Issue | Action |
|------|----------|-------|--------|
| `robots_blocked` | 10 | Blocked by robots.txt | Fix robots.txt, remove from sitemap |
| `noindex` | 10 | Has noindex tag | Remove noindex for canonical URLs |
| `fetch_error` | 10 | HTTP error (4xx/5xx) | Fix page, remove broken URLs from sitemap |
| `canonical_mismatch` | 20 | Canonical mismatch | Align canonicals/redirects |
| `api_error` | 30 | API failed | Retry with smaller batch |
| `not_indexed_other` | 40-70 | Various indexing issues | Triage via coverage state |
| `indexed_pass` | 999 | ✓ Indexed | No action needed |

Lower priority = more urgent. Filter: `priority <= 20` for critical issues.

---

## Code Examples

### Python: Process Action Queue

```python
import json
from pathlib import Path

def load_latest_queue(output_dir: Path = Path("automation/output/gsc_indexing")):
    """Load most recent action queue."""
    files = list(output_dir.glob("*_action_queue.json"))
    if not files:
        raise FileNotFoundError("No action queue found")
    latest = max(files, key=lambda p: p.stat().st_mtime)
    return json.loads(latest.read_text())

def get_critical_issues(queue_data: dict):
    """Get issues with priority <= 20 (robots, noindex, fetch errors)."""
    items = queue_data.get("items", [])
    return [
        item for item in items 
        if item.get("priority", 999) <= 20 
        and item.get("reason_code") != "indexed_pass"
    ]

def get_issues_by_type(queue_data: dict, reason_code: str):
    """Get all items with specific issue type."""
    items = queue_data.get("items", [])
    return [item for item in items if item.get("reason_code") == reason_code]

# Usage
queue = load_latest_queue()
critical = get_critical_issues(queue)
blocked = get_issues_by_type(queue, "robots_blocked")
noindex = get_issues_by_type(queue, "noindex")

print(f"Critical issues: {len(critical)}")
print(f"Robots blocked: {len(blocked)}")
print(f"Noindex tags: {len(noindex)}")

for item in critical[:5]:
    print(f"- [{item['reason_code']}] {item['url']}")
    print(f"  Action: {item['action']}")
```

### Python: Run Report Programmatically

```python
import subprocess
from pathlib import Path

def run_gsc_report(
    site: str,
    sitemap_url: str,
    output_dir: Path = Path("automation/output/gsc_indexing"),
    limit: int = 200
) -> Path:
    """Run GSC indexing report and return path to action queue."""
    
    cmd = [
        "pageseeds", "automation", "seo", "gsc-indexing-report",
        "--site", site,
        "--sitemap-url", sitemap_url,
        "--limit", str(limit),
        "--workers", "2",
        "--out-dir", str(output_dir)
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        raise RuntimeError(f"GSC report failed: {result.stderr}")
    
    # Find the action queue file that was just created
    queue_files = list(output_dir.glob("*_action_queue.json"))
    return max(queue_files, key=lambda p: p.stat().st_mtime)

# Usage
queue_path = run_gsc_report(
    site="sc-domain:example.com",
    sitemap_url="https://example.com/sitemap.xml"
)
print(f"Report saved to: {queue_path}")
```

### Shell: Quick Analysis

```bash
#!/bin/bash
# Quick GSC health check

SITE="sc-domain:example.com"
SITEMAP="https://example.com/sitemap.xml"

echo "Running GSC report..."
pageseeds automation seo gsc-indexing-report \
  --site "$SITE" \
  --sitemap-url "$SITEMAP" \
  --limit 500 \
  --workers 4

# Find latest action queue
QUEUE=$(ls -t automation/output/gsc_indexing/*_action_queue.json | head -1)

echo ""
echo "Summary from: $QUEUE"
echo "---"

# Extract key stats using Python
python3 << EOF
import json
with open("$QUEUE") as f:
    data = json.load(f)

print(f"Total URLs: {data['counts']['total_items']}")
print(f"Non-indexed: {data['counts']['non_indexed_items']}")
print(f"Mapped to content: {data['counts']['mapped_to_article']}")
print("")

# Count by reason code
from collections import Counter
reasons = Counter(item['reason_code'] for item in data['items'])
print("Issues by type:")
for reason, count in reasons.most_common():
    if reason != 'indexed_pass':
        print(f"  - {reason}: {count}")

# Top priority issues
high_priority = [i for i in data['items'] if i['priority'] <= 20]
if high_priority:
    print(f"\nTop {min(5, len(high_priority))} critical issues:")
    for item in high_priority[:5]:
        print(f"  [{item['reason_code']}] {item['url']}")
EOF
```

### TypeScript: Node.js Processing

```typescript
import { readFileSync, statSync } from 'fs';
import { globSync } from 'glob';

interface GSCActionItem {
  priority: number;
  reason_code: string;
  action: string;
  url: string;
  path: string;
  verdict: string;
  coverageState: string;
  indexingState: string;
  robotsTxtState: string;
  pageFetchState: string;
  crawlAllowed: boolean | null;
  indexingAllowed: boolean | null;
  lastCrawlTime: string;
  userCanonical: string;
  googleCanonical: string;
  mapped_to_article: boolean;
  article?: {
    id: number;
    url_slug: string;
    status: string;
    file: string;
    basename: string;
    title: string;
  };
}

interface GSCActionQueue {
  meta: {
    run_ts: string;
    site_url: string;
    articles_json?: string;
  };
  counts: {
    total_items: number;
    mapped_to_article: number;
    not_mapped: number;
    non_indexed_items: number;
  };
  items: GSCActionItem[];
}

function loadLatestQueue(outputDir = 'automation/output/gsc_indexing'): GSCActionQueue {
  const files = globSync(`${outputDir}/*_action_queue.json`);
  if (files.length === 0) throw new Error('No action queue files found');
  
  files.sort((a, b) => statSync(b).mtimeMs - statSync(a).mtimeMs);
  return JSON.parse(readFileSync(files[0], 'utf-8'));
}

function getCriticalIssues(queue: GSCActionQueue): GSCActionItem[] {
  return queue.items.filter(
    item => item.priority <= 20 && item.reason_code !== 'indexed_pass'
  );
}

function getIssuesByType(queue: GSCActionQueue, reasonCode: string): GSCActionItem[] {
  return queue.items.filter(item => item.reason_code === reasonCode);
}

// Usage
const queue = loadLatestQueue();
const critical = getCriticalIssues(queue);

console.log(`Total URLs: ${queue.counts.total_items}`);
console.log(`Critical issues: ${critical.length}`);

for (const issue of critical.slice(0, 5)) {
  console.log(`[${issue.reason_code}] ${issue.url}`);
}
```

---

## CLI Reference

### `seo gsc-indexing-report`

| Flag | Description | Default |
|------|-------------|---------|
| `--site` | GSC property ID | Auto-detect |
| `--sitemap-url` | Sitemap URL | From manifest |
| `--urls-file` | File with URLs to check | - |
| `--limit` | Max URLs to inspect | 500 |
| `--workers` | Concurrent threads | 2 |
| `--out-dir` | Output directory | `automation/output/gsc_indexing` |
| `--include-raw` | Include raw API data | false |
| `--list-sites` | List available sites | - |
| `--manifest` | Path to manifest.json | - |

### `seo gsc-page-context`

| Flag | Description | Default |
|------|-------------|---------|
| `--site` | GSC property ID | Required |
| `--url` | Page URL to inspect | Required |
| `--compare-days` | Short trend window | 7 |
| `--long-compare-days` | Long trend window | 28 |

---

## Troubleshooting

### "No service account path found"

Set credentials:
```bash
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json
```

### "Cannot auto-detect automation repo root"

Run from automation repo or set:
```bash
export AUTOMATION_REPO_ROOT=/path/to/automation
```

### "Site not found"

Service account needs GSC access:
1. Go to Google Search Console → Settings → Users and Permissions
2. Add service account email as "Full" or "Restricted" user

### Domain mismatch

Check `manifest.json` has correct `url` and `gsc_site` values.

---

## Best Practices

1. **Use manifest.json** - Avoid repeating site/sitemap in every command
2. **Process action_queue.json** - Don't parse markdown, use the structured JSON
3. **Filter by priority** - Focus on `priority <= 20` first (critical issues)
4. **Check `mapped_to_article`** - Connect GSC data to your content system
5. **Run regularly** - Weekly/monthly indexing audits
6. **Use service accounts** - More reliable than OAuth for automation

---

## Source

- Tool code: `automation/tools/seo_help/gsc_indexing_report.py`
- CLI wrapper: `automation/packages/pageseeds/src/pageseeds/cli.py`
- Full docs: `automation/dashboard_ptk/GUIDE.md`
