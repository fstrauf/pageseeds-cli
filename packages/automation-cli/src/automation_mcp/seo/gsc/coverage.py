"""Google Search Console Coverage Report processing for 404 errors.

This module processes Coverage Drilldown CSV exports from GSC to identify
and classify 404 errors that need fixing.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Coverage404Record:
    """A single 404 error from Coverage Drilldown."""
    url: str
    last_crawled: str | None
    category: str  # Classification category
    reason: str    # Human-readable reason for the classification
    priority: int  # Priority for fixing (10 = highest, 100 = lowest)
    suggested_action: str
    path: str = field(default="")
    
    def __post_init__(self):
        object.__setattr__(
            self, 
            'path', 
            self.url.replace('https://', '').replace('http://', '').split('/', 1)[1] if '/' in self.url else ''
        )


def _classify_404(url: str) -> tuple[str, str, int, str]:
    """Classify a 404 URL into actionable categories.
    
    Returns:
        Tuple of (category, reason, priority, suggested_action)
    """
    url_lower = url.lower()
    path = url.replace('https://', '').replace('http://', '').split('/', 1)[1] if '/' in url else ''
    path_lower = path.lower()
    
    # 1. Malformed URLs (highest priority - fix immediately)
    if '/&' in url or '/$' in url or url.endswith('/&') or url.endswith('/$'):
        return (
            "malformed",
            "URL contains invalid characters (& or $)",
            10,
            "Fix internal links pointing to this malformed URL; add redirect if external backlinks exist"
        )
    
    # 2. Raw file paths (content files exposed)
    if path.endswith('.md') or path.endswith('.mdx') or '/content/' in path:
        if '.md' in path or '.mdx' in path:
            return (
                "raw_content_path",
                "Raw markdown file path exposed",
                15,
                "Add 301 redirect to the rendered page URL; remove from sitemap if present"
            )
    
    # 3. Old URL patterns that should redirect
    old_patterns = [
        (r'/content/\d+_', "old_content_slug", "Old content slug format"),
        (r'/general/days_to_expiry/content/', "legacy_content_path", "Legacy content path structure"),
    ]
    for pattern, category, reason in old_patterns:
        if re.search(pattern, path):
            return (
                category,
                f"{reason}: {path}",
                20,
                "Add 301 redirect to current canonical URL; update internal links"
            )
    
    # 4. Protocol/www mismatches
    if '://daystoexpiry.com' in url and '://www.daystoexpiry.com' not in url:
        return (
            "non_www",
            "Non-www URL variant (should redirect to www)",
            25,
            "Ensure non-www redirects to www; check canonical tags"
            )
    
    # 5. Trailing slash issues
    if path.endswith('/') and len(path) > 1:
        # Check if this might be a valid page with/without slash confusion
        return (
            "trailing_slash",
            "URL has trailing slash (possible canonical issue)",
            40,
            "Standardize trailing slash behavior; add 301 if needed"
        )
    
    # 6. Valid-looking URLs that might need content restored
    if re.match(r'^[a-z0-9/_-]+$', path_lower) and len(path) > 5:
        return (
            "valid_path_missing_content",
            "Valid URL path but content not found",
            30,
            "Either restore the content OR add 301 redirect to relevant replacement page"
        )
    
    # 7. Everything else
    return (
        "other",
        f"Other 404 error: {path}",
        50,
        "Investigate source of 404; add redirect or fix/remove referring links"
    )


def parse_coverage_csv(csv_path: Path) -> list[Coverage404Record]:
    """Parse a GSC Coverage Drilldown CSV file.
    
    Expected CSV format:
    URL,Last crawled
    https://example.com/broken-page,2024-01-15
    
    Args:
        csv_path: Path to the CSV file
        
    Returns:
        List of Coverage404Record objects
    """
    records = []
    
    try:
        content = csv_path.read_text(encoding='utf-8')
    except Exception as e:
        raise ValueError(f"Failed to read CSV: {e}")
    
    # Handle different CSV formats
    reader = csv.DictReader(content.splitlines())
    
    for row in reader:
        # Try different column name variations
        url = row.get('URL') or row.get('url') or row.get('Address') or row.get('address')
        last_crawled = row.get('Last crawled') or row.get('last_crawled') or row.get('Last Crawled')
        
        if not url:
            continue
            
        # Skip non-404 entries if the CSV has a status column
        status = row.get('Status') or row.get('status') or ''
        if status and '404' not in status and 'not found' not in status.lower():
            continue
        
        category, reason, priority, suggested_action = _classify_404(url)
        
        records.append(Coverage404Record(
            url=url,
            last_crawled=last_crawled,
            category=category,
            reason=reason,
            priority=priority,
            suggested_action=suggested_action
        ))
    
    # Sort by priority
    records.sort(key=lambda r: r.priority)
    return records


def generate_coverage_404_report(
    csv_path: Path,
    site_url: str,
    out_dir: Path,
) -> dict[str, Any]:
    """Generate a full 404 analysis report from Coverage CSV.
    
    Args:
        csv_path: Path to the Coverage Drilldown CSV
        site_url: The site URL (e.g., https://www.example.com)
        out_dir: Output directory for reports
        
    Returns:
        Report metadata dict
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    site_slug = _slugify(site_url)
    
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Parse the CSV
    records = parse_coverage_csv(csv_path)
    
    # Group by category
    buckets: dict[str, list[dict]] = {}
    for record in records:
        bucket = buckets.setdefault(record.category, [])
        bucket.append({
            "url": record.url,
            "path": record.path,
            "last_crawled": record.last_crawled,
            "priority": record.priority,
            "reason": record.reason,
            "suggested_action": record.suggested_action,
        })
    
    # Build action queue
    action_queue = {
        "meta": {
            "run_ts": timestamp,
            "site_url": site_url,
            "source_csv": str(csv_path),
            "total_records": len(records),
        },
        "counts": {
            "total_items": len(records),
            "by_category": {k: len(v) for k, v in buckets.items()},
        },
        "buckets": buckets,
        "items": [
            {
                "url": r.url,
                "path": r.path,
                "last_crawled": r.last_crawled,
                "priority": r.priority,
                "category": r.category,
                "reason": r.reason,
                "suggested_action": r.suggested_action,
            }
            for r in records
        ],
    }
    
    # Write action queue JSON
    action_queue_path = out_dir / f"coverage_404_{timestamp}_{site_slug}_action_queue.json"
    action_queue_path.write_text(_json_dumps(action_queue))
    
    # Generate fix plan markdown
    fix_plan_path = out_dir / f"coverage_404_{timestamp}_{site_slug}_fix_plan.md"
    fix_plan_content = _generate_fix_plan_markdown(site_url, timestamp, buckets, records)
    fix_plan_path.write_text(fix_plan_content)
    
    # Generate summary CSV for easy review
    summary_csv_path = out_dir / f"coverage_404_{timestamp}_{site_slug}_summary.csv"
    _write_summary_csv(summary_csv_path, records)
    
    return {
        "site_url": site_url,
        "timestamp": timestamp,
        "total_404s": len(records),
        "output_dir": str(out_dir),
        "action_queue": str(action_queue_path),
        "fix_plan": str(fix_plan_path),
        "summary_csv": str(summary_csv_path),
        "categories": list(buckets.keys()),
    }


def _slugify(value: str) -> str:
    """Create a safe filename slug."""
    import re
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_").strip("_")
    return value or "site"


def _json_dumps(data: Any) -> str:
    """JSON dump with nice formatting."""
    import json
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _generate_fix_plan_markdown(
    site_url: str,
    timestamp: str,
    buckets: dict[str, list[dict]],
    records: list[Coverage404Record]
) -> str:
    """Generate a markdown fix plan from 404 records."""
    lines = [
        f"# Coverage 404 Fix Plan: {site_url}",
        f"",
        f"Generated: {datetime.now().isoformat()}",
        f"Total 404s: {len(records)}",
        f"",
        "## Quick Stats",
        f"",
    ]
    
    # Category summary
    lines.append("| Category | Count | Priority |")
    lines.append("|----------|-------|----------|")
    priority_names = {
        10: "🔴 Critical",
        15: "🔴 High",
        20: "🟡 High",
        25: "🟡 Medium-High",
        30: "🟡 Medium",
        40: "🟢 Low-Medium",
        50: "🟢 Low",
    }
    for category, items in sorted(buckets.items(), key=lambda x: min(i["priority"] for i in x[1])):
        min_priority = min(i["priority"] for i in items)
        priority_label = priority_names.get(min_priority, "🟢 Low")
        lines.append(f"| {category} | {len(items)} | {priority_label} |")
    
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # Detailed sections by category
    category_order = ["malformed", "raw_content_path", "old_content_slug", "legacy_content_path", 
                      "non_www", "valid_path_missing_content", "trailing_slash", "other"]
    
    for category in category_order:
        if category not in buckets:
            continue
            
        items = buckets[category]
        lines.append(f"## {category}: {len(items)} URLs")
        lines.append("")
        lines.append(f"**Action:** {items[0]['suggested_action']}")
        lines.append("")
        lines.append("**Affected URLs:**")
        lines.append("")
        
        for item in items[:15]:  # Show first 15
            lines.append(f"- `{item['path']}` (last crawled: {item['last_crawled'] or 'unknown'})")
        
        if len(items) > 15:
            lines.append(f"- ... and {len(items) - 15} more")
        
        lines.append("")
    
    # Next steps section
    lines.extend([
        "## Recommended Implementation Order",
        "",
        "1. **Malformed URLs** (/&, /$) - Fix immediately",
        "2. **Raw content paths** (.md files) - Add redirects",
        "3. **Old URL patterns** - Add 301 redirects to new locations",
        "4. **Valid missing content** - Decide: restore content or redirect",
        "5. **Other** - Investigate and fix referring links",
        "",
        "## Implementation Notes",
        "",
        "For Next.js projects, add redirects to `next.config.js`:",
        "```javascript",
        "async redirects() {",
        "  return [",
        "    // Example: old content slug to new URL",
        "    {",
        "      source: '/content/:id_*',",
        "      destination: '/blog/:id_*',",
        "      permanent: true,",
        "    },",
        "    // Example: raw .md to rendered page",
        "    {",
        "      source: '/general/days_to_expiry/content/:slug.md',",
        "      destination: '/blog/:slug',",
        "      permanent: true,",
        "    },",
        "  ];",
        "},",
        "```",
    ])
    
    return "\n".join(lines)


def _write_summary_csv(csv_path: Path, records: list[Coverage404Record]) -> None:
    """Write a summary CSV for easy review."""
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['URL', 'Path', 'Category', 'Priority', 'Last Crawled', 'Suggested Action'])
        for r in records:
            writer.writerow([r.url, r.path, r.category, r.priority, r.last_crawled, r.suggested_action])
