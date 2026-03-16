"""Google Search Console "Page with redirect" report processing.

Analyzes redirect issues and creates actionable fix tasks.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


@dataclass(frozen=True)
class RedirectRecord:
    """A single redirect from GSC Coverage report."""
    url: str
    last_crawled: str | None
    redirect_type: str = "unknown"  # canonicalization, moved_content, deprecated, unknown
    issue: str = ""  # The problem with this redirect
    priority: int = 50  # Fix priority (10 = highest)
    suggested_action: str = ""
    final_url: str | None = None  # Where it redirects to (detected)


def _classify_redirect(url: str) -> tuple[str, str, int, str]:
    """Classify a redirect URL into actionable categories.
    
    Returns:
        Tuple of (redirect_type, issue, priority, suggested_action)
    """
    parsed = urlparse(url)
    scheme = parsed.scheme
    netloc = parsed.netloc.lower()
    path = parsed.path
    
    # 1. HTTP to HTTPS (normal, but check if in sitemap)
    if scheme == "http":
        return (
            "canonicalization",
            "HTTP URL (should redirect to HTTPS)",
            30,
            "Ensure HTTPS redirect is in place; remove HTTP URLs from sitemap if present"
        )
    
    # 2. Non-www to www (or vice versa)
    if not netloc.startswith("www."):
        return (
            "canonicalization",
            "Non-www URL (should redirect to www)",
            30,
            "Ensure www redirect is in place; update sitemap to use www URLs"
        )
    
    # 3. Trailing slash issues
    if len(path) > 1 and path.endswith("/"):
        return (
            "canonicalization",
            "URL has trailing slash (may redirect to non-slash version)",
            40,
            "Standardize trailing slash behavior; ensure sitemap matches canonical preference"
        )
    
    # 4. Old URL patterns (content moved)
    old_patterns = [
        (r"/content/\d+_", "old_content_slug"),
        (r"/general/.*/content/", "legacy_path"),
        (r"/old[-_]?", "deprecated_path"),
    ]
    
    for pattern, redirect_type in old_patterns:
        if re.search(pattern, path, re.IGNORECASE):
            return (
                "moved_content",
                f"Old URL pattern detected: {pattern}",
                20,
                "Verify redirect points to correct new location; update internal links to new URL"
            )
    
    # 5. Parameter variations
    if "?" in url or "&" in url:
        return (
            "parameter_variation",
            "URL with parameters (may redirect to canonical version)",
            40,
            "Ensure canonical URL is in sitemap; consider if parameters are needed"
        )
    
    # 6. Default everything else
    return (
        "unknown",
        "Redirect reason unknown - manual review needed",
        50,
        "Manually verify if redirect is intentional; check for redirect chains"
    )


def parse_redirect_csv(csv_path: Path) -> list[RedirectRecord]:
    """Parse GSC "Page with redirect" CSV file.
    
    Expected CSV format:
    URL,Last crawled
    https://example.com/old-page,2024-01-15
    
    Args:
        csv_path: Path to the CSV file
        
    Returns:
        List of RedirectRecord objects
    """
    records = []
    
    try:
        content = csv_path.read_text(encoding="utf-8")
    except Exception as e:
        raise ValueError(f"Failed to read CSV: {e}")
    
    reader = csv.DictReader(content.splitlines())
    
    for row in reader:
        url = row.get("URL") or row.get("url") or row.get("Address") or row.get("address")
        last_crawled = row.get("Last crawled") or row.get("last_crawled") or row.get("Last Crawled")
        
        if not url:
            continue
        
        redirect_type, issue, priority, suggested_action = _classify_redirect(url)
        
        records.append(RedirectRecord(
            url=url,
            last_crawled=last_crawled,
            redirect_type=redirect_type,
            issue=issue,
            priority=priority,
            suggested_action=suggested_action
        ))
    
    # Sort by priority
    records.sort(key=lambda r: r.priority)
    return records


def generate_redirect_report(
    csv_path: Path,
    site_url: str,
    out_dir: Path,
    sitemap_urls: set[str] | None = None,
) -> dict[str, Any]:
    """Generate a full redirect analysis report.
    
    Args:
        csv_path: Path to the GSC "Page with redirect" CSV
        site_url: The site URL
        out_dir: Output directory
        sitemap_urls: Optional set of URLs from sitemap to check against
        
    Returns:
        Report metadata dict
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    site_slug = _slugify(site_url)
    
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Parse the CSV
    records = parse_redirect_csv(csv_path)
    
    # Check which are in sitemap (critical issue)
    in_sitemap = []
    not_in_sitemap = []
    
    for record in records:
        if sitemap_urls and record.url in sitemap_urls:
            in_sitemap.append(record)
        else:
            not_in_sitemap.append(record)
    
    # Group by redirect type
    by_type: dict[str, list[dict]] = {}
    for record in records:
        bucket = by_type.setdefault(record.redirect_type, [])
        bucket.append({
            "url": record.url,
            "last_crawled": record.last_crawled,
            "priority": record.priority,
            "issue": record.issue,
            "suggested_action": record.suggested_action,
            "in_sitemap": record in in_sitemap,
        })
    
    # Build action queue
    action_queue = {
        "meta": {
            "run_ts": timestamp,
            "site_url": site_url,
            "source_csv": str(csv_path),
            "total_redirects": len(records),
            "in_sitemap": len(in_sitemap),
            "not_in_sitemap": len(not_in_sitemap),
        },
        "counts": {
            "total_items": len(records),
            "by_type": {k: len(v) for k, v in by_type.items()},
        },
        "buckets": by_type,
        "items": [
            {
                "url": r.url,
                "last_crawled": r.last_crawled,
                "priority": r.priority,
                "redirect_type": r.redirect_type,
                "issue": r.issue,
                "suggested_action": r.suggested_action,
                "in_sitemap": r in in_sitemap,
            }
            for r in records
        ],
    }
    
    # Write outputs
    import json
    action_queue_path = out_dir / f"redirect_analysis_{timestamp}_{site_slug}_action_queue.json"
    action_queue_path.write_text(json.dumps(action_queue, indent=2))
    
    fix_plan_path = out_dir / f"redirect_analysis_{timestamp}_{site_slug}_fix_plan.md"
    fix_plan_content = _generate_redirect_fix_plan(site_url, timestamp, records, in_sitemap, by_type)
    fix_plan_path.write_text(fix_plan_content)
    
    summary_csv_path = out_dir / f"redirect_analysis_{timestamp}_{site_slug}_summary.csv"
    _write_redirect_summary_csv(summary_csv_path, records, in_sitemap)
    
    return {
        "site_url": site_url,
        "timestamp": timestamp,
        "total_redirects": len(records),
        "in_sitemap_count": len(in_sitemap),
        "output_dir": str(out_dir),
        "action_queue": str(action_queue_path),
        "fix_plan": str(fix_plan_path),
        "summary_csv": str(summary_csv_path),
        "redirect_types": list(by_type.keys()),
    }


def _slugify(value: str) -> str:
    """Create a safe filename slug."""
    import re
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_").strip("_")
    return value or "site"


def _generate_redirect_fix_plan(
    site_url: str,
    timestamp: str,
    records: list[RedirectRecord],
    in_sitemap: list[RedirectRecord],
    by_type: dict[str, list[dict]]
) -> str:
    """Generate a markdown fix plan from redirect records."""
    lines = [
        f"# Redirect Analysis Fix Plan: {site_url}",
        f"",
        f"Generated: {datetime.now().isoformat()}",
        f"Total redirects: {len(records)}",
        f"**In sitemap (CRITICAL): {len(in_sitemap)}**",
        f"",
        "## Quick Stats",
        f"",
    ]
    
    # Type summary
    lines.append("| Redirect Type | Count | In Sitemap? | Priority |")
    lines.append("|---------------|-------|-------------|----------|")
    priority_names = {
        10: "🔴 Critical",
        20: "🟡 High",
        30: "🟢 Normal",
        40: "🔵 Low",
        50: "⚪ Info",
    }
    for redirect_type, items in sorted(by_type.items(), key=lambda x: min(i["priority"] for i in x[1])):
        min_priority = min(i["priority"] for i in items)
        priority_label = priority_names.get(min_priority, "⚪ Info")
        in_smap = sum(1 for i in items if i["in_sitemap"])
        lines.append(f"| {redirect_type} | {len(items)} | {in_smap} | {priority_label} |")
    
    lines.append("")
    
    # Critical: Redirects in sitemap
    if in_sitemap:
        lines.append("## 🚨 CRITICAL: Redirects in Sitemap")
        lines.append("")
        lines.append("These URLs redirect but are still in your sitemap. **Remove them immediately.**")
        lines.append("")
        for record in in_sitemap[:20]:
            lines.append(f"- `{record.url}` ({record.redirect_type})")
        if len(in_sitemap) > 20:
            lines.append(f"- ... and {len(in_sitemap) - 20} more")
        lines.append("")
        lines.append("### How to fix")
        lines.append("1. Remove these URLs from your sitemap.xml")
        lines.append("2. Ensure the **final destination URLs** are in the sitemap instead")
        lines.append("")
    
    # Detailed sections by type
    lines.append("---")
    lines.append("")
    
    type_order = ["moved_content", "canonicalization", "parameter_variation", "unknown"]
    
    for redirect_type in type_order:
        if redirect_type not in by_type:
            continue
        
        items = by_type[redirect_type]
        in_smap_count = sum(1 for i in items if i["in_sitemap"])
        
        lines.append(f"## {redirect_type}: {len(items)} URLs")
        if in_smap_count > 0:
            lines.append(f"**⚠️ {in_smap_count} of these are in your sitemap**")
        lines.append("")
        lines.append(f"**Action:** {items[0]['suggested_action']}")
        lines.append("")
        lines.append("**Affected URLs:**")
        lines.append("")
        
        for item in items[:15]:
            smap_note = " [IN SITEMAP]" if item["in_sitemap"] else ""
            lines.append(f"- `{item['url']}`{smap_note}")
        
        if len(items) > 15:
            lines.append(f"- ... and {len(items) - 15} more")
        
        lines.append("")
    
    # Implementation guide
    lines.extend([
        "## Implementation Priority",
        "",
        "Fix in this order:",
        "",
        "1. **🚨 CRITICAL: Remove redirects from sitemap** - Wastes crawl budget",
        "2. **Moved content redirects** - Ensure redirects point to correct new pages",
        "3. **Update internal links** - Change links to point directly to final URLs",
        "4. **Canonicalization redirects** - Verify HTTP→HTTPS, non-www→www are working",
        "",
        "## Checking Redirects",
        "",
        "Test a redirect:",
        "```bash",
        "curl -I https://example.com/old-url",
        "# Look for: HTTP/2 301 or HTTP/2 308",
        "# Look for: location: https://example.com/new-url",
        "```",
        "",
        "## Next.js Redirect Example",
        "",
        "For intentional redirects (moved content):",
        "",
        "```javascript",
        "// next.config.js",
        "async redirects() {",
        "  return [",
        "    {",
        "      source: '/old-blog/:slug*',",
        "      destination: '/blog/:slug*',",
        "      permanent: true, // 301 redirect",
        "    },",
        "  ];",
        "}",
        "```",
    ])
    
    return "\n".join(lines)


def _write_redirect_summary_csv(csv_path: Path, records: list[RedirectRecord], in_sitemap: list[RedirectRecord]) -> None:
    """Write a summary CSV for easy review."""
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['URL', 'Redirect Type', 'Priority', 'In Sitemap', 'Issue', 'Suggested Action'])
        for r in records:
            is_in_smap = "YES" if r in in_sitemap else "NO"
            writer.writerow([r.url, r.redirect_type, r.priority, is_in_smap, r.issue, r.suggested_action])
