"""Report generation and output formatting."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

from .analytics import MoverMetrics, PageMetrics
from .indexing import InspectionRecord


def _slugify(value: str) -> str:
    """Create a safe filename slug."""
    import re
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "site"


def _ensure_dir(path: Path) -> Path:
    """Ensure directory exists."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def generate_indexing_report(
    site_url: str,
    inspections: Sequence[tuple[str, InspectionRecord, str, str, int]],
    out_dir: Path,
    include_raw: bool = False,
) -> dict[str, Any]:
    """Generate indexing report outputs.
    
    Args:
        site_url: Site property URL
        inspections: List of (url, record, reason_code, action, priority)
        out_dir: Output directory
        include_raw: Include raw API responses
        
    Returns:
        Report metadata dict
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    site_slug = _slugify(site_url)
    
    out_dir = _ensure_dir(out_dir)
    
    # Build bucketed results
    buckets: dict[str, list[dict]] = {}
    for url, record, reason_code, action, priority in inspections:
        bucket = buckets.setdefault(reason_code, [])
        item: dict[str, Any] = {
            "url": url,
            "priority": priority,
            "reason_code": reason_code,
            "action": action,
            "verdict": record.verdict,
            "coverage_state": record.coverage_state,
            "indexing_state": record.indexing_state,
            "robots_txt_state": record.robots_txt_state,
            "crawl_allowed": record.crawl_allowed,
            "indexing_allowed": record.indexing_allowed,
        }
        if include_raw:
            item["raw"] = record.raw
        bucket.append(item)
    
    # Build action queue
    action_queue = {
        "meta": {
            "run_ts": timestamp,
            "site_url": site_url,
            "total_inspected": len(inspections),
        },
        "counts": {
            "total_items": len(inspections),
            "by_reason": {k: len(v) for k, v in buckets.items()},
        },
        "buckets": buckets,
        "items": [
            {
                "url": url,
                "priority": priority,
                "reason_code": reason_code,
                "action": action,
                "verdict": record.verdict,
                "coverage_state": record.coverage_state,
            }
            for url, record, reason_code, action, priority in inspections
        ],
    }
    
    # Write outputs
    base_name = f"{timestamp}_{site_slug}"
    
    action_queue_path = out_dir / f"{base_name}_action_queue.json"
    action_queue_path.write_text(json.dumps(action_queue, indent=2))
    
    # Generate summary
    summary_lines = [
        f"# GSC Indexing Report: {site_url}",
        f"Generated: {datetime.now().isoformat()}",
        "",
        f"Total inspected: {len(inspections)}",
        "",
        "## Summary by Category",
        "",
    ]
    
    for reason_code, items in sorted(buckets.items(), key=lambda x: min(i["priority"] for i in x[1])):
        summary_lines.append(f"### {reason_code}: {len(items)}")
        summary_lines.append("")
        for item in items[:5]:  # Show top 5 per bucket
            summary_lines.append(f"- {item['url']}")
        if len(items) > 5:
            summary_lines.append(f"- ... and {len(items) - 5} more")
        summary_lines.append("")
    
    summary_path = out_dir / f"{base_name}_summary.md"
    summary_path.write_text("\n".join(summary_lines))
    
    return {
        "site_url": site_url,
        "timestamp": timestamp,
        "total_inspected": len(inspections),
        "output_dir": str(out_dir),
        "action_queue": str(action_queue_path),
        "summary": str(summary_path),
    }


def generate_site_scan_report(
    site_url: str,
    pages: Sequence[dict[str, Any]],
    out_dir: Path,
) -> dict[str, Any]:
    """Generate site scan report.
    
    Args:
        site_url: Site property URL
        pages: List of page data dicts
        out_dir: Output directory
        
    Returns:
        Report metadata dict
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    site_slug = _slugify(site_url)
    
    out_dir = _ensure_dir(out_dir)
    
    report = {
        "meta": {
            "generated_at": datetime.now().isoformat(),
            "site_url": site_url,
            "pages_analyzed": len(pages),
        },
        "pages": pages,
    }
    
    output_path = out_dir / f"gsc_site_scan_{timestamp}_{site_slug}.json"
    output_path.write_text(json.dumps(report, indent=2))
    
    return {
        "site_url": site_url,
        "timestamp": timestamp,
        "pages_analyzed": len(pages),
        "output_path": str(output_path),
    }


def generate_fix_plan(
    buckets: dict[str, list[dict]],
    out_path: Path,
) -> Path:
    """Generate markdown fix plan from bucketed issues.
    
    Args:
        buckets: Dict of reason_code -> list of items
        out_path: Output file path
        
    Returns:
        Path to generated file
    """
    lines = [
        "# GSC Fix Plan",
        "",
        f"Generated: {datetime.now().isoformat()}",
        "",
        "## Priority Order",
        "",
        "Fix in this order (most urgent first):",
        "",
    ]
    
    priority_order = [
        ("robots_blocked", "🔴 Robots.txt Blocked"),
        ("noindex", "🔴 Noindex Tag"),
        ("fetch_error", "🔴 Fetch Errors"),
        ("canonical_mismatch", "🟡 Canonical Mismatch"),
        ("not_indexed_crawled", "🟡 Not Indexed (Crawled)"),
        ("not_indexed_discovered", "🟡 Not Indexed (Discovered)"),
        ("not_indexed_other", "🟢 Other Indexing Issues"),
    ]
    
    for reason_code, title in priority_order:
        if reason_code not in buckets:
            continue
            
        items = buckets[reason_code]
        lines.append(f"### {title} ({len(items)} URLs)")
        lines.append("")
        
        if items:
            action = items[0].get("action", "Review and fix")
            lines.append(f"**Action:** {action}")
            lines.append("")
            lines.append("**Affected URLs:**")
            for item in items[:10]:
                lines.append(f"- {item['url']}")
            if len(items) > 10:
                lines.append(f"- ... and {len(items) - 10} more")
            lines.append("")
    
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines))
    return out_path
