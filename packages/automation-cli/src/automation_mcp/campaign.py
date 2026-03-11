from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


CAMPAIGN_SCHEMA_VERSION = 1
RUN_STATE_FILENAME = "state.json"
RUN_PLAN_FILENAME = "fix_plan.json"

# Disposition values
DISPOSITION_MUST_FIX = "must_fix"
DISPOSITION_SHOULD_DO = "should_do"
DISPOSITION_DEFER = "defer"
DISPOSITION_IGNORE = "ignore_with_reason"
VALID_DISPOSITIONS = {DISPOSITION_MUST_FIX, DISPOSITION_SHOULD_DO, DISPOSITION_DEFER, DISPOSITION_IGNORE}

# Priority buckets
BUCKET_CRITICAL = "critical"
BUCKET_GROWTH = "growth"
BUCKET_QUALITY = "quality"
BUCKET_ORDER = [BUCKET_CRITICAL, BUCKET_GROWTH, BUCKET_QUALITY]

# Execution statuses
STATUS_TODO = "todo"
STATUS_IN_PROGRESS = "in_progress"
STATUS_QA = "qa"
STATUS_DONE = "done"
STATUS_BLOCKED = "blocked"
VALID_STATUSES = {STATUS_TODO, STATUS_IN_PROGRESS, STATUS_QA, STATUS_DONE, STATUS_BLOCKED}

# Default WIP limit
DEFAULT_WIP_LIMIT = 5


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _campaigns_root(repo_root: Path) -> Path:
    return repo_root / ".github" / "automation" / "campaigns"


def _run_dir(campaigns_root: Path, run_id: str) -> Path:
    return campaigns_root / run_id


def _read_json(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return raw


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _append_index_line(index_path: Path, line_payload: dict) -> None:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with index_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(line_payload, ensure_ascii=False) + "\n")


def _make_run_id(campaign_name: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    suffix = uuid4().hex[:8]
    normalized = campaign_name.strip().lower().replace(" ", "-")
    safe = "".join(ch for ch in normalized if ch.isalnum() or ch in {"-", "_"})
    safe = safe or "campaign"
    return f"{safe}-{stamp}-{suffix}"


def _default_sources(sources: list[str] | None) -> list[str]:
    if sources:
        seen: set[str] = set()
        deduped: list[str] = []
        for source in sources:
            item = source.strip().lower()
            if not item or item in seen:
                continue
            seen.add(item)
            deduped.append(item)
        if deduped:
            return deduped
    return ["gsc", "posthog", "keywords"]


def _generate_finding_id(finding: dict) -> str:
    """Generate deterministic ID for a finding based on source, type, and key fields."""
    source = finding.get("source", "unknown")
    finding_type = finding.get("type", "unknown")
    url = finding.get("url", "")
    title = finding.get("title", "")
    
    # Create a deterministic hash
    content = f"{source}:{finding_type}:{url}:{title}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _categorize_bucket(finding: dict) -> str:
    """Categorize a finding into a priority bucket."""
    finding_type = finding.get("type", "").lower()
    severity = finding.get("severity", "").lower()
    
    # Critical: indexing failures, blocking analytics issues
    critical_types = {
        "indexing_failure", "not_indexed", "blocked", "error",
        "analytics_failure", "critical", "blocking"
    }
    
    # Growth: opportunities, new keywords, expansion
    growth_types = {
        "opportunity", "keyword_opportunity", "content_gap",
        "growth", "expansion", "new_keyword"
    }
    
    if finding_type in critical_types or severity in {"critical", "blocking", "high"}:
        return BUCKET_CRITICAL
    elif finding_type in growth_types or severity in {"medium", "growth"}:
        return BUCKET_GROWTH
    else:
        return BUCKET_QUALITY


def _run_subprocess_collect(
    cmd: list[str],
    cwd: Path,
    output_path: Path,
    timeout: int = 300,
) -> dict:
    """Run a collection subprocess and capture results."""
    result = {
        "success": False,
        "output_path": str(output_path),
        "stdout": "",
        "stderr": "",
        "returncode": -1,
        "error": "",
    }
    
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        result["returncode"] = proc.returncode
        result["stdout"] = proc.stdout
        result["stderr"] = proc.stderr
        
        if proc.returncode == 0:
            result["success"] = True
            # Try to parse JSON output
            try:
                parsed = json.loads(proc.stdout)
                result["parsed_output"] = parsed
            except json.JSONDecodeError:
                pass
        else:
            result["error"] = f"Process exited with code {proc.returncode}"
            
    except subprocess.TimeoutExpired:
        result["error"] = f"Timeout after {timeout}s"
    except Exception as exc:
        result["error"] = str(exc)
    
    # Write result to output path
    _write_json(output_path, result)
    return result


def _detect_sitemap_url(manifest_path: Path | None, repo_root: Path) -> str | None:
    """Try to detect sitemap URL from manifest or common locations."""
    # Try manifest first
    if manifest_path and manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text())
            base_url = manifest.get("url") or manifest.get("base_url")
            if base_url:
                return f"{base_url.rstrip('/')}/sitemap.xml"
        except Exception:
            pass
    
    # Try common sitemap locations
    common_paths = ["sitemap.xml", "sitemap_index.xml"]
    for path in common_paths:
        url = f"https://{repo_root.name}/{path}"
        # We'll return the guessed URL and let the CLI verify
        return url
    
    return None


def collect_gsc(
    repo_root: Path,
    run_root: Path,
    website_id: str,
    timeout: int = 600,
) -> dict:
    """Run GSC collection for the campaign."""
    artifacts_dir = run_root / "artifacts"
    output_path = artifacts_dir / "gsc_collection.json"
    
    # Look for manifest.json in common locations
    automation_dir = repo_root / ".github" / "automation"
    manifest_candidates = [
        automation_dir / "manifest.json",
        automation_dir / "seo_workspace.json",
        repo_root / "automation" / "manifest.json",
        repo_root / "manifest.json",
    ]
    manifest_path = None
    for candidate in manifest_candidates:
        if candidate.exists():
            manifest_path = candidate
            break
    
    # Look for service account key (machine-local or in repo secrets)
    service_account_candidates = [
        Path.home() / ".config" / "automation" / "gsc-service-account.json",
        repo_root / ".github" / "automation" / "secrets" / "gsc-service-account.json",
    ]
    service_account_path = None
    for candidate in service_account_candidates:
        if candidate.exists():
            service_account_path = candidate
            break
    
    # Detect sitemap URL
    sitemap_url = _detect_sitemap_url(manifest_path, repo_root)
    
    # Build the GSC indexing report command
    cmd = [
        "automation-cli", "seo", "gsc-indexing-report",
        "--repo-root", str(repo_root),
        "--limit", "500",
        "--workers", "2",
        "--include-raw",
    ]
    
    if manifest_path:
        cmd.extend(["--manifest", str(manifest_path)])
    if service_account_path:
        cmd.extend(["--service-account-path", str(service_account_path)])
    if sitemap_url:
        cmd.extend(["--sitemap-url", sitemap_url])
    
    # Run collection
    result = _run_subprocess_collect(cmd, repo_root, output_path, timeout)
    
    # Extract findings from the action queue if available
    findings = []
    if result.get("success") and output_path.exists():
        try:
            data = _read_json(output_path)
            if data.get("success") and "parsed_output" in data:
                # Look for action queue items in output
                parsed = data["parsed_output"]
                items = parsed.get("items", [])
                for item in items:
                    if isinstance(item, dict):
                        finding = {
                            "source": "gsc",
                            "type": item.get("reason_code", "unknown"),
                            "url": item.get("url", ""),
                            "title": item.get("article", {}).get("title", ""),
                            "severity": "critical" if "not indexed" in str(item.get("coverageState", "")).lower() else "medium",
                            "description": item.get("verdict", ""),
                            "coverage_state": item.get("coverageState", ""),
                            "mapped_to_article": item.get("mapped_to_article", False),
                            "file": item.get("article", {}).get("file", ""),
                            "raw_data": item,
                        }
                        findings.append(finding)
        except Exception as exc:
            result["finding_extraction_error"] = str(exc)
    
    result["findings"] = findings
    result["findings_count"] = len(findings)
    
    # Update the result file with findings
    _write_json(output_path, result)
    
    return result


def collect_posthog(
    repo_root: Path,
    run_root: Path,
    website_id: str,
    timeout: int = 300,
) -> dict:
    """Run PostHog collection for the campaign."""
    artifacts_dir = run_root / "artifacts"
    output_path = artifacts_dir / "posthog_collection.json"
    
    # Look for posthog_config.json in common locations
    automation_dir = repo_root / ".github" / "automation"
    config_candidates = [
        automation_dir / "posthog_config.json",
        repo_root / "automation" / "posthog_config.json",
        repo_root / "posthog_config.json",
    ]
    config_path = None
    for candidate in config_candidates:
        if candidate.exists():
            config_path = candidate
            break
    
    # Build the PostHog report command
    cmd = [
        "automation-cli", "posthog", "report",
        "--repo-root", str(repo_root),
    ]
    
    # PostHog config auto-loaded by the CLI if config file exists
    
    # Run collection
    result = _run_subprocess_collect(cmd, repo_root, output_path, timeout)
    
    # Extract findings from situations and action candidates
    findings = []
    if result.get("success") and output_path.exists():
        try:
            data = _read_json(output_path)
            if data.get("success") and "parsed_output" in data:
                parsed = data["parsed_output"]
                
                # Extract from situations
                for situation in parsed.get("situations", []):
                    if isinstance(situation, dict):
                        confidence = situation.get("confidence", "medium")
                        finding = {
                            "source": "posthog",
                            "type": "analytics_issue",
                            "url": "",  # May not have specific URL
                            "title": situation.get("label", "Analytics Issue"),
                            "severity": "critical" if confidence == "high" else "medium",
                            "description": situation.get("evidence", ""),
                            "confidence": confidence,
                            "raw_data": situation,
                        }
                        findings.append(finding)
                
                # Extract from action candidates
                for action in parsed.get("action_candidates", []):
                    if isinstance(action, dict):
                        priority = action.get("priority", "P3")
                        severity = "critical" if priority in ["P0", "P1"] else "medium"
                        finding = {
                            "source": "posthog",
                            "type": "action_candidate",
                            "url": "",
                            "title": action.get("next_step", "Action Item"),
                            "severity": severity,
                            "description": f"Owner: {action.get('owner_surface', 'unknown')}",
                            "priority": priority,
                            "raw_data": action,
                        }
                        findings.append(finding)
        except Exception as exc:
            result["finding_extraction_error"] = str(exc)
    
    result["findings"] = findings
    result["findings_count"] = len(findings)
    
    # Update the result file with findings
    _write_json(output_path, result)
    
    return result


def _extract_content_gaps_from_seo_brief(brief_path: Path) -> list[dict]:
    """Parse SEO content brief markdown to extract content gaps.
    
    Looks for patterns like:
    "⚠️ **\"Title\"** (Est. XXX vol, KD: Y) - PRIORITY priority"
    """
    findings = []
    
    if not brief_path.exists():
        return findings
    
    content = brief_path.read_text(encoding="utf-8")
    lines = content.split("\n")
    
    for line in lines:
        line = line.strip()
        # Look for content gap markers
        if "⚠️" in line or "Content Gap" in line or "MISSING" in line:
            # Try to extract keyword/title
            import re
            
            # Pattern: "**\"Title\"** (Est. XXX vol, KD: Y)"
            title_match = re.search(r'\*\*["\']([^"\']+)["\']\*\*', line)
            volume_match = re.search(r'Est\.\s*(\d+)\s*vol', line, re.IGNORECASE)
            kd_match = re.search(r'KD:\s*(\d+)', line)
            priority_match = re.search(r'(HIGH|MEDIUM|LOW)\s*priority', line, re.IGNORECASE)
            
            if title_match:
                title = title_match.group(1)
                volume = int(volume_match.group(1)) if volume_match else 0
                kd = int(kd_match.group(1)) if kd_match else 50
                priority = priority_match.group(1).upper() if priority_match else "MEDIUM"
                
                # Determine severity based on KD
                if kd <= 5:
                    severity = "critical"
                elif kd <= 15:
                    severity = "high"
                elif kd <= 30:
                    severity = "medium"
                else:
                    severity = "low"
                
                finding = {
                    "source": "keywords",
                    "type": "content_gap",
                    "title": title,
                    "keyword": title.lower().replace(":", "").strip(),
                    "difficulty": kd,
                    "volume": volume,
                    "priority": priority,
                    "severity": severity,
                    "description": f"Content gap: {title} (KD {kd}, {volume} vol/month)",
                }
                findings.append(finding)
    
    return findings


def collect_keywords(
    repo_root: Path,
    run_root: Path,
    website_id: str,
    timeout: int = 300,
) -> dict:
    """Run keyword research collection for the campaign.
    
    Reads from project's SEO content brief to find content gaps.
    """
    artifacts_dir = run_root / "artifacts"
    output_path = artifacts_dir / "keywords_collection.json"
    
    findings = []
    sources_used = []
    
    # 1. Try to read project's SEO content brief
    automation_dir = repo_root / ".github" / "automation"
    seo_brief_candidates = [
        automation_dir / "websites" / website_id / f"{website_id}_seo_content_brief.md",
        automation_dir / "websites" / website_id / "seo_content_brief.md",
        repo_root / "automation" / "seo_content_brief.md",
        repo_root / "seo_content_brief.md",
    ]
    
    for brief_path in seo_brief_candidates:
        if brief_path.exists():
            gaps = _extract_content_gaps_from_seo_brief(brief_path)
            findings.extend(gaps)
            sources_used.append(f"seo_brief:{brief_path.name}")
            break
    
    # 2. Also check for keyword research manifest (for explicit keyword lists)
    automation_dir = repo_root / ".github" / "automation"
    manifest_candidates = [
        automation_dir / "keyword_research_manifest.json",
        repo_root / "automation" / "keyword_research_manifest.json",
    ]
    
    for manifest_path in manifest_candidates:
        if manifest_path.exists():
            try:
                manifest = _read_json(manifest_path)
                
                # Convert target keywords to findings
                for kw in manifest.get("target_keywords", []):
                    finding = {
                        "source": "keywords",
                        "type": "keyword_opportunity",
                        "keyword": kw.get("keyword", ""),
                        "title": f"Target: '{kw.get('keyword', '')}'",
                        "difficulty": kw.get("difficulty", 0),
                        "volume": kw.get("volume", 0),
                        "priority": kw.get("priority", "medium"),
                        "cluster": kw.get("cluster", ""),
                        "severity": "critical" if kw.get("difficulty", 50) <= 5 else "medium" if kw.get("difficulty", 50) <= 20 else "low",
                        "description": f"KD {kw.get('difficulty', '?')} | {kw.get('volume', '?')} vol/month",
                    }
                    findings.append(finding)
                
                sources_used.append(f"manifest:{manifest_path.name}")
            except Exception:
                pass
            break
    
    # Remove duplicates (by title)
    seen_titles = set()
    unique_findings = []
    for f in findings:
        title = f.get("title", "").lower()
        if title and title not in seen_titles:
            seen_titles.add(title)
            unique_findings.append(f)
    findings = unique_findings
    
    result = {
        "success": True,
        "output_path": str(output_path),
        "findings": findings,
        "findings_count": len(findings),
        "sources": sources_used,
    }
    
    if not findings:
        result["note"] = "No keyword findings. Ensure SEO content brief exists with content gaps marked by ⚠️"
    
    _write_json(output_path, result)
    return result


def collect_campaign_data(
    *,
    repo_root: Path,
    run_id: str,
    sources: list[str] | None = None,
    dry_run: bool = False,
) -> dict:
    """Run deterministic collection for all configured sources."""
    campaigns_root = _campaigns_root(repo_root)
    run_root = _run_dir(campaigns_root, run_id)
    state_path = run_root / RUN_STATE_FILENAME
    
    if not state_path.exists():
        raise FileNotFoundError(f"Campaign state not found: {state_path}")
    
    state = _read_json(state_path)
    website_id = state.get("website_id", "")
    selected_sources = _default_sources(sources) if sources else state.get("sources", ["gsc", "posthog", "keywords"])
    
    if dry_run:
        return {
            "success": True,
            "dry_run": True,
            "run_id": run_id,
            "sources": selected_sources,
            "would_collect": selected_sources,
        }
    
    results = {}
    all_findings = []
    
    for source in selected_sources:
        if source == "gsc":
            results["gsc"] = collect_gsc(repo_root, run_root, website_id)
            all_findings.extend(results["gsc"].get("findings", []))
        elif source == "posthog":
            results["posthog"] = collect_posthog(repo_root, run_root, website_id)
            all_findings.extend(results["posthog"].get("findings", []))
        elif source == "keywords":
            results["keywords"] = collect_keywords(repo_root, run_root, website_id)
            all_findings.extend(results["keywords"].get("findings", []))
    
    # Update state
    now = _now_utc_iso()
    state["status"] = "collect_complete"
    state["current_phase"] = "plan"
    state["updated_at"] = now
    state["collection_results"] = {
        "sources": list(results.keys()),
        "total_findings": len(all_findings),
        "completed_at": now,
    }
    state["next_action"] = f"automation-cli campaign plan --repo-root {repo_root} --run-id {run_id}"
    state["notes"] = "Collection complete. Run 'campaign plan' to merge findings into fix plan."
    
    _write_json(state_path, state)
    
    # Update index
    index_path = campaigns_root / "index.jsonl"
    _append_index_line(index_path, {
        "schema_version": CAMPAIGN_SCHEMA_VERSION,
        "run_id": run_id,
        "event": "collection_complete",
        "total_findings": len(all_findings),
        "timestamp": now,
    })
    
    return {
        "success": True,
        "run_id": run_id,
        "sources": selected_sources,
        "results": results,
        "total_findings": len(all_findings),
        "findings": all_findings,
        "next_action": state["next_action"],
    }


def plan_campaign(
    *,
    repo_root: Path,
    run_id: str,
    auto_disposition: dict[str, str] | None = None,
    dry_run: bool = False,
) -> dict:
    """Merge collection findings into fix_plan.json with required dispositions."""
    campaigns_root = _campaigns_root(repo_root)
    run_root = _run_dir(campaigns_root, run_id)
    state_path = run_root / RUN_STATE_FILENAME
    fix_plan_path = run_root / RUN_PLAN_FILENAME
    artifacts_dir = run_root / "artifacts"
    
    if not state_path.exists():
        raise FileNotFoundError(f"Campaign state not found: {state_path}")
    
    state = _read_json(state_path)
    now = _now_utc_iso()
    
    # Load existing fix plan
    fix_plan = _read_json(fix_plan_path) if fix_plan_path.exists() else {
        "schema_version": CAMPAIGN_SCHEMA_VERSION,
        "run_id": run_id,
        "campaign_name": state.get("campaign_name", ""),
        "status": "draft",
        "items": [],
        "counts": {
            "total": 0,
            "must_fix_open": 0,
            "should_do_open": 0,
            "defer": 0,
            "ignore_with_reason": 0,
            "done": 0,
            "blocked": 0,
        },
        "coverage": {
            "all_findings_triaged": True,
            "must_fix_gate_passed": True,
        },
        "updated_at": now,
    }
    
    # Load findings from artifacts
    all_findings = []
    for artifact_file in artifacts_dir.glob("*_collection.json"):
        try:
            data = _read_json(artifact_file)
            findings = data.get("findings", [])
            all_findings.extend(findings)
        except Exception:
            pass
    
    # Build items from findings
    new_items = []
    existing_ids = {item.get("id") for item in fix_plan.get("items", [])}
    
    auto_disp = auto_disposition or {}
    
    for finding in all_findings:
        finding_id = _generate_finding_id(finding)
        
        # Skip duplicates
        if finding_id in existing_ids:
            continue
        
        # Determine bucket
        bucket = _categorize_bucket(finding)
        
        # Determine disposition (default based on bucket)
        if bucket == BUCKET_CRITICAL:
            default_disp = DISPOSITION_MUST_FIX
        elif bucket == BUCKET_GROWTH:
            default_disp = DISPOSITION_SHOULD_DO
        else:
            default_disp = DISPOSITION_SHOULD_DO
        
        # Check for auto-disposition rules
        source = finding.get("source", "")
        finding_type = finding.get("type", "")
        disposition = auto_disp.get(f"{source}:{finding_type}", auto_disp.get(source, default_disp))
        
        item = {
            "id": finding_id,
            "source": finding.get("source", "unknown"),
            "type": finding.get("type", "unknown"),
            "bucket": bucket,
            "disposition": disposition,
            "status": STATUS_TODO,
            "url": finding.get("url", ""),
            "title": finding.get("title", ""),
            "description": finding.get("description", ""),
            "severity": finding.get("severity", "medium"),
            "created_at": now,
            "updated_at": now,
            "assigned_to": "",
            "notes": "",
            "file": finding.get("file", ""),
            "raw_finding": finding.get("raw_data", finding),
        }
        
        new_items.append(item)
        existing_ids.add(finding_id)
    
    if dry_run:
        return {
            "success": True,
            "dry_run": True,
            "run_id": run_id,
            "new_items_count": len(new_items),
            "new_items": new_items,
        }
    
    # Merge new items into fix plan
    items = fix_plan.get("items", [])
    items.extend(new_items)
    
    # Sort by bucket priority, then severity
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    items.sort(key=lambda x: (
        BUCKET_ORDER.index(x.get("bucket", BUCKET_QUALITY)),
        severity_order.get(x.get("severity", "medium"), 2),
        x.get("created_at", ""),
    ))
    
    fix_plan["items"] = items
    fix_plan["status"] = "planned"
    fix_plan["updated_at"] = now
    
    # Recalculate counts
    counts = {"total": len(items), "must_fix_open": 0, "should_do_open": 0, 
              "defer": 0, "ignore_with_reason": 0, "done": 0, "blocked": 0}
    
    for item in items:
        disp = item.get("disposition")
        status = item.get("status")
        
        if disp == DISPOSITION_MUST_FIX and status != STATUS_DONE:
            counts["must_fix_open"] += 1
        elif disp == DISPOSITION_SHOULD_DO and status == STATUS_TODO:
            counts["should_do_open"] += 1
        elif disp == DISPOSITION_DEFER:
            counts["defer"] += 1
        elif disp == DISPOSITION_IGNORE:
            counts["ignore_with_reason"] += 1
        elif status == STATUS_DONE:
            counts["done"] += 1
        elif status == STATUS_BLOCKED:
            counts["blocked"] += 1
    
    fix_plan["counts"] = counts
    fix_plan["coverage"] = {
        "all_findings_triaged": all(item.get("disposition") in VALID_DISPOSITIONS for item in items),
        "must_fix_gate_passed": counts["must_fix_open"] == 0,
    }
    
    _write_json(fix_plan_path, fix_plan)
    
    # Update state
    state["status"] = "plan_complete"
    state["current_phase"] = "execute"
    state["updated_at"] = now
    state["next_action"] = f"automation-cli campaign execute --repo-root {repo_root} --run-id {run_id}"
    state["notes"] = f"Plan complete with {len(items)} items. {counts['must_fix_open']} must-fix items open."
    
    _write_json(state_path, state)
    
    # Update index
    _append_index_line(campaigns_root / "index.jsonl", {
        "schema_version": CAMPAIGN_SCHEMA_VERSION,
        "run_id": run_id,
        "event": "plan_complete",
        "total_items": len(items),
        "new_items": len(new_items),
        "timestamp": now,
    })
    
    return {
        "success": True,
        "run_id": run_id,
        "total_items": len(items),
        "new_items": len(new_items),
        "counts": counts,
        "coverage": fix_plan["coverage"],
        "next_action": state["next_action"],
    }


def execute_campaign_batch(
    *,
    repo_root: Path,
    run_id: str,
    wip_limit: int = DEFAULT_WIP_LIMIT,
    dry_run: bool = False,
) -> dict:
    """Process next batch of items respecting WIP limit and priority."""
    campaigns_root = _campaigns_root(repo_root)
    run_root = _run_dir(campaigns_root, run_id)
    state_path = run_root / RUN_STATE_FILENAME
    fix_plan_path = run_root / RUN_PLAN_FILENAME
    decisions_dir = run_root / "decisions"
    
    if not state_path.exists():
        raise FileNotFoundError(f"Campaign state not found: {state_path}")
    
    if not fix_plan_path.exists():
        raise FileNotFoundError(f"Fix plan not found: {fix_plan_path}")
    
    state = _read_json(state_path)
    fix_plan = _read_json(fix_plan_path)
    now = _now_utc_iso()
    
    items = fix_plan.get("items", [])
    
    # Count current in_progress items (WIP)
    wip_items = [item for item in items if item.get("status") == STATUS_IN_PROGRESS]
    current_wip = len(wip_items)
    
    if current_wip >= wip_limit:
        return {
            "success": True,
            "run_id": run_id,
            "batch_size": 0,
            "wip_status": "at_limit",
            "current_wip": current_wip,
            "wip_limit": wip_limit,
            "message": f"WIP limit reached ({current_wip}/{wip_limit}). Complete in-progress items before starting new ones.",
        }
    
    # Find items to start (respecting priority buckets)
    available_slots = wip_limit - current_wip
    to_start = []
    
    for bucket in BUCKET_ORDER:
        for item in items:
            if len(to_start) >= available_slots:
                break
            if item.get("status") != STATUS_TODO:
                continue
            if item.get("disposition") == DISPOSITION_DEFER:
                continue
            if item.get("disposition") == DISPOSITION_IGNORE:
                continue
            if item.get("bucket") == bucket:
                to_start.append(item)
    
    if dry_run:
        return {
            "success": True,
            "dry_run": True,
            "run_id": run_id,
            "batch_size": len(to_start),
            "would_start": [{"id": item["id"], "title": item.get("title", "")} for item in to_start],
            "wip_limit": wip_limit,
            "current_wip": current_wip,
        }
    
    # Start items (update status)
    started_items = []
    for item in to_start:
        item["status"] = STATUS_IN_PROGRESS
        item["updated_at"] = now
        item["started_at"] = now
        started_items.append(item)
        
        # Record decision
        decision = {
            "timestamp": now,
            "item_id": item["id"],
            "action": "start",
            "previous_status": STATUS_TODO,
            "new_status": STATUS_IN_PROGRESS,
        }
        decision_path = decisions_dir / f"{item['id']}_start.json"
        _write_json(decision_path, decision)
    
    # Update fix plan
    fix_plan["updated_at"] = now
    _write_json(fix_plan_path, fix_plan)
    
    # Update state
    state["updated_at"] = now
    if started_items:
        state["status"] = "execute_in_progress"
        state["notes"] = f"Execution in progress. {len(started_items)} items started, {current_wip + len(started_items)} in progress."
    
    # Check if all items are done
    all_done = all(
        item.get("status") in {STATUS_DONE, STATUS_BLOCKED}
        or item.get("disposition") in {DISPOSITION_DEFER, DISPOSITION_IGNORE}
        for item in items
    )
    
    if all_done:
        state["status"] = "execute_complete"
        state["current_phase"] = "complete"
        state["notes"] = "Execution complete. All items processed."
        state["next_action"] = ""
    
    _write_json(state_path, state)
    
    # Update index
    _append_index_line(campaigns_root / "index.jsonl", {
        "schema_version": CAMPAIGN_SCHEMA_VERSION,
        "run_id": run_id,
        "event": "execute_batch",
        "started_count": len(started_items),
        "timestamp": now,
    })
    
    return {
        "success": True,
        "run_id": run_id,
        "batch_size": len(started_items),
        "started_items": [{"id": item["id"], "title": item.get("title", "")} for item in started_items],
        "wip_status": f"{current_wip + len(started_items)}/{wip_limit}",
        "current_phase": state.get("current_phase", "execute"),
        "next_action": state.get("next_action", ""),
    }


def transition_item(
    *,
    repo_root: Path,
    run_id: str,
    item_id: str,
    new_status: str,
    notes: str = "",
    assigned_to: str = "",
) -> dict:
    """Transition an item to a new status."""
    if new_status not in VALID_STATUSES:
        raise ValueError(f"Invalid status: {new_status}. Must be one of {VALID_STATUSES}")
    
    campaigns_root = _campaigns_root(repo_root)
    run_root = _run_dir(campaigns_root, run_id)
    fix_plan_path = run_root / RUN_PLAN_FILENAME
    decisions_dir = run_root / "decisions"
    
    if not fix_plan_path.exists():
        raise FileNotFoundError(f"Fix plan not found: {fix_plan_path}")
    
    fix_plan = _read_json(fix_plan_path)
    now = _now_utc_iso()
    
    # Find item
    item = None
    for i in fix_plan.get("items", []):
        if i.get("id") == item_id:
            item = i
            break
    
    if item is None:
        raise ValueError(f"Item not found: {item_id}")
    
    previous_status = item.get("status")
    
    # Update item
    item["status"] = new_status
    item["updated_at"] = now
    if new_status == STATUS_DONE:
        item["completed_at"] = now
    if notes:
        item["notes"] = notes
    if assigned_to:
        item["assigned_to"] = assigned_to
    
    # Recalculate counts
    counts = {"total": 0, "must_fix_open": 0, "should_do_open": 0, 
              "defer": 0, "ignore_with_reason": 0, "done": 0, "blocked": 0}
    
    for it in fix_plan.get("items", []):
        counts["total"] += 1
        disp = it.get("disposition")
        status = it.get("status")
        
        if disp == DISPOSITION_MUST_FIX and status != STATUS_DONE:
            counts["must_fix_open"] += 1
        elif disp == DISPOSITION_SHOULD_DO and status == STATUS_TODO:
            counts["should_do_open"] += 1
        elif disp == DISPOSITION_DEFER:
            counts["defer"] += 1
        elif disp == DISPOSITION_IGNORE:
            counts["ignore_with_reason"] += 1
        elif status == STATUS_DONE:
            counts["done"] += 1
        elif status == STATUS_BLOCKED:
            counts["blocked"] += 1
    
    fix_plan["counts"] = counts
    fix_plan["coverage"] = {
        "all_findings_triaged": all(it.get("disposition") in VALID_DISPOSITIONS for it in fix_plan.get("items", [])),
        "must_fix_gate_passed": counts["must_fix_open"] == 0,
    }
    fix_plan["updated_at"] = now
    
    _write_json(fix_plan_path, fix_plan)
    
    # Record decision
    decision = {
        "timestamp": now,
        "item_id": item_id,
        "action": "transition",
        "previous_status": previous_status,
        "new_status": new_status,
        "notes": notes,
    }
    decision_path = decisions_dir / f"{item_id}_{new_status}.json"
    _write_json(decision_path, decision)
    
    return {
        "success": True,
        "run_id": run_id,
        "item_id": item_id,
        "previous_status": previous_status,
        "new_status": new_status,
        "counts": counts,
        "coverage": fix_plan["coverage"],
    }


def carry_over_items(
    *,
    repo_root: Path,
    from_run_id: str,
    to_run_id: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Carry over unfinished should_do items from a completed campaign to a new one."""
    campaigns_root = _campaigns_root(repo_root)
    from_run_root = _run_dir(campaigns_root, from_run_id)
    from_fix_plan_path = from_run_root / RUN_PLAN_FILENAME
    
    if not from_fix_plan_path.exists():
        raise FileNotFoundError(f"Source fix plan not found: {from_fix_plan_path}")
    
    from_fix_plan = _read_json(from_fix_plan_path)
    now = _now_utc_iso()
    
    # Find items to carry over
    items_to_carry = []
    for item in from_fix_plan.get("items", []):
        # Carry over should_do items that aren't done
        if item.get("disposition") == DISPOSITION_SHOULD_DO:
            if item.get("status") not in {STATUS_DONE, STATUS_BLOCKED}:
                # Bump priority (move to critical if old)
                item_copy = dict(item)
                item_copy["id"] = f"{item['id']}_carry_{uuid4().hex[:8]}"
                item_copy["bucket"] = BUCKET_CRITICAL if item.get("bucket") == BUCKET_QUALITY else item.get("bucket", BUCKET_GROWTH)
                item_copy["carried_from"] = from_run_id
                item_copy["carry_count"] = item.get("carry_count", 0) + 1
                item_copy["status"] = STATUS_TODO
                item_copy["created_at"] = now
                item_copy["updated_at"] = now
                item_copy["notes"] = f"Carried from {from_run_id}. {item.get('notes', '')}"
                items_to_carry.append(item_copy)
    
    if dry_run:
        return {
            "success": True,
            "dry_run": True,
            "from_run_id": from_run_id,
            "items_to_carry": len(items_to_carry),
            "carried_items": [{"id": item["id"], "title": item.get("title", "")} for item in items_to_carry],
        }
    
    # Create new run or use existing
    if to_run_id:
        to_run_root = _run_dir(campaigns_root, to_run_id)
        to_fix_plan_path = to_run_root / RUN_PLAN_FILENAME
        if not to_fix_plan_path.exists():
            raise FileNotFoundError(f"Target fix plan not found: {to_fix_plan_path}")
        to_fix_plan = _read_json(to_fix_plan_path)
    else:
        # Create new campaign run
        from_state_path = from_run_root / RUN_STATE_FILENAME
        from_state = _read_json(from_state_path) if from_state_path.exists() else {}
        
        result = create_campaign_run(
            repo_root=repo_root,
            campaign_name=from_fix_plan.get("campaign_name", "default"),
            cadence=from_state.get("cadence", "biweekly"),
            website_id=from_state.get("website_id", ""),
            sources=from_state.get("sources", ["gsc", "posthog", "keywords"]),
        )
        
        to_run_id = result["run_id"]
        to_run_root = _run_dir(campaigns_root, to_run_id)
        to_fix_plan_path = to_run_root / RUN_PLAN_FILENAME
        to_fix_plan = _read_json(to_fix_plan_path)
    
    # Add carried items
    items = to_fix_plan.get("items", [])
    items.extend(items_to_carry)
    
    # Sort
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    items.sort(key=lambda x: (
        BUCKET_ORDER.index(x.get("bucket", BUCKET_QUALITY)),
        severity_order.get(x.get("severity", "medium"), 2),
        x.get("created_at", ""),
    ))
    
    to_fix_plan["items"] = items
    to_fix_plan["status"] = "planned"
    to_fix_plan["updated_at"] = now
    to_fix_plan["carried_from"] = from_run_id
    
    # Recalculate counts
    counts = {"total": len(items), "must_fix_open": 0, "should_do_open": 0, 
              "defer": 0, "ignore_with_reason": 0, "done": 0, "blocked": 0}
    
    for item in items:
        disp = item.get("disposition")
        status = item.get("status")
        
        if disp == DISPOSITION_MUST_FIX and status != STATUS_DONE:
            counts["must_fix_open"] += 1
        elif disp == DISPOSITION_SHOULD_DO and status == STATUS_TODO:
            counts["should_do_open"] += 1
        elif disp == DISPOSITION_DEFER:
            counts["defer"] += 1
        elif disp == DISPOSITION_IGNORE:
            counts["ignore_with_reason"] += 1
        elif status == STATUS_DONE:
            counts["done"] += 1
        elif status == STATUS_BLOCKED:
            counts["blocked"] += 1
    
    to_fix_plan["counts"] = counts
    to_fix_plan["coverage"] = {
        "all_findings_triaged": True,
        "must_fix_gate_passed": counts["must_fix_open"] == 0,
    }
    
    _write_json(to_fix_plan_path, to_fix_plan)
    
    # Update state
    state_path = to_run_root / RUN_STATE_FILENAME
    state = _read_json(state_path)
    state["status"] = "carry_over_complete"
    state["current_phase"] = "execute"
    state["updated_at"] = now
    state["carried_from"] = from_run_id
    state["carried_items_count"] = len(items_to_carry)
    state["next_action"] = f"automation-cli campaign execute --repo-root {repo_root} --run-id {to_run_id}"
    _write_json(state_path, state)
    
    # Update index
    _append_index_line(campaigns_root / "index.jsonl", {
        "schema_version": CAMPAIGN_SCHEMA_VERSION,
        "run_id": to_run_id,
        "event": "carry_over",
        "from_run_id": from_run_id,
        "carried_items": len(items_to_carry),
        "timestamp": now,
    })
    
    return {
        "success": True,
        "from_run_id": from_run_id,
        "to_run_id": to_run_id,
        "carried_items_count": len(items_to_carry),
        "new_total_items": len(items),
    }


def archive_campaign(
    *,
    repo_root: Path,
    run_id: str,
    dry_run: bool = False,
) -> dict:
    """Archive a completed campaign run."""
    campaigns_root = _campaigns_root(repo_root)
    run_root = _run_dir(campaigns_root, run_id)
    archive_root = campaigns_root / "archive" / run_id
    
    if not run_root.exists():
        raise FileNotFoundError(f"Campaign run not found: {run_root}")
    
    if dry_run:
        return {
            "success": True,
            "dry_run": True,
            "run_id": run_id,
            "would_move_from": str(run_root),
            "would_move_to": str(archive_root),
        }
    
    # Move to archive
    import shutil
    archive_root.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(run_root), str(archive_root))
    
    now = _now_utc_iso()
    _append_index_line(campaigns_root / "index.jsonl", {
        "schema_version": CAMPAIGN_SCHEMA_VERSION,
        "run_id": run_id,
        "event": "archived",
        "archived_at": now,
        "archive_path": str(archive_root),
    })
    
    return {
        "success": True,
        "run_id": run_id,
        "archived_to": str(archive_root),
    }


def prune_campaigns(
    *,
    repo_root: Path,
    keep_count: int = 10,
    dry_run: bool = False,
) -> dict:
    """Prune old campaign runs, keeping only the most recent ones."""
    campaigns_root = _campaigns_root(repo_root)
    
    # Get all run directories
    run_dirs = [d for d in campaigns_root.iterdir() if d.is_dir() and d.name != "archive"]
    
    # Sort by mtime (most recent first)
    run_dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)
    
    to_prune = run_dirs[keep_count:]
    
    if dry_run:
        return {
            "success": True,
            "dry_run": True,
            "total_runs": len(run_dirs),
            "keep_count": keep_count,
            "would_prune": len(to_prune),
            "prune_list": [d.name for d in to_prune],
        }
    
    pruned = []
    for d in to_prune:
        try:
            import shutil
            shutil.rmtree(d)
            pruned.append(d.name)
        except Exception as exc:
            pruned.append({"name": d.name, "error": str(exc)})
    
    return {
        "success": True,
        "total_runs": len(run_dirs),
        "kept": keep_count,
        "pruned": len(pruned),
        "pruned_list": pruned,
    }


def create_campaign_run(
    *,
    repo_root: Path,
    campaign_name: str,
    cadence: str,
    website_id: str,
    sources: list[str] | None = None,
    dry_run: bool = False,
) -> dict:
    run_id = _make_run_id(campaign_name)
    now = _now_utc_iso()
    campaigns_root = _campaigns_root(repo_root)
    run_root = _run_dir(campaigns_root, run_id)
    artifacts_dir = run_root / "artifacts"
    decisions_dir = run_root / "decisions"
    state_path = run_root / RUN_STATE_FILENAME
    fix_plan_path = run_root / RUN_PLAN_FILENAME
    index_path = campaigns_root / "index.jsonl"
    selected_sources = _default_sources(sources)

    state_payload = {
        "schema_version": CAMPAIGN_SCHEMA_VERSION,
        "run_id": run_id,
        "campaign_name": campaign_name,
        "cadence": cadence,
        "website_id": website_id,
        "repo_root": str(repo_root),
        "created_at": now,
        "updated_at": now,
        "status": "collect_pending",
        "current_phase": "collect",
        "sources": selected_sources,
        "paths": {
            "run_root": str(run_root),
            "state_path": str(state_path),
            "fix_plan_path": str(fix_plan_path),
            "artifacts_dir": str(artifacts_dir),
            "decisions_dir": str(decisions_dir),
        },
        "next_action": f"automation-cli campaign collect --repo-root {repo_root} --run-id {run_id}",
        "notes": "Deterministic collection is pending.",
    }

    fix_plan_payload = {
        "schema_version": CAMPAIGN_SCHEMA_VERSION,
        "run_id": run_id,
        "campaign_name": campaign_name,
        "status": "draft",
        "items": [],
        "counts": {
            "total": 0,
            "must_fix_open": 0,
            "should_do_open": 0,
            "defer": 0,
            "ignore_with_reason": 0,
            "done": 0,
            "blocked": 0,
        },
        "coverage": {
            "all_findings_triaged": True,
            "must_fix_gate_passed": True,
        },
        "updated_at": now,
    }

    index_line = {
        "schema_version": CAMPAIGN_SCHEMA_VERSION,
        "run_id": run_id,
        "campaign_name": campaign_name,
        "cadence": cadence,
        "website_id": website_id,
        "status": state_payload["status"],
        "current_phase": state_payload["current_phase"],
        "created_at": now,
        "updated_at": now,
        "state_path": str(state_path),
    }

    if not dry_run:
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        decisions_dir.mkdir(parents=True, exist_ok=True)
        _write_json(state_path, state_payload)
        _write_json(fix_plan_path, fix_plan_payload)
        _append_index_line(index_path, index_line)

    return {
        "success": True,
        "dry_run": dry_run,
        "run_id": run_id,
        "campaign_name": campaign_name,
        "cadence": cadence,
        "website_id": website_id,
        "repo_root": str(repo_root),
        "sources": selected_sources,
        "paths": {
            "run_root": str(run_root),
            "state_path": str(state_path),
            "fix_plan_path": str(fix_plan_path),
            "index_path": str(index_path),
        },
        "next_action": state_payload["next_action"],
    }


def _latest_run_id_from_index(index_path: Path) -> str:
    if not index_path.exists():
        raise FileNotFoundError(f"Campaign index not found: {index_path}")
    lines = index_path.read_text(encoding="utf-8").splitlines()
    for line in reversed(lines):
        text = line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("run_id"):
            return str(payload["run_id"])
    raise ValueError(f"No valid run entries found in index: {index_path}")


def load_campaign_state(*, repo_root: Path, run_id: str) -> dict:
    state_path = _run_dir(_campaigns_root(repo_root), run_id) / RUN_STATE_FILENAME
    if not state_path.exists():
        raise FileNotFoundError(f"Campaign state not found for run_id '{run_id}': {state_path}")
    state = _read_json(state_path)
    state["_state_path"] = str(state_path)
    return state


def load_latest_campaign_state(*, repo_root: Path) -> dict:
    index_path = _campaigns_root(repo_root) / "index.jsonl"
    run_id = _latest_run_id_from_index(index_path)
    state = load_campaign_state(repo_root=repo_root, run_id=run_id)
    state["_resolved_latest"] = True
    return state


def campaign_status(*, repo_root: Path, run_id: str | None = None) -> dict:
    state = load_campaign_state(repo_root=repo_root, run_id=run_id) if run_id else load_latest_campaign_state(repo_root=repo_root)
    fix_plan_path = Path(str(state.get("paths", {}).get("fix_plan_path", ""))).expanduser()
    fix_plan: dict = {}
    fix_plan_error = ""
    if fix_plan_path:
        if fix_plan_path.exists():
            try:
                fix_plan = _read_json(fix_plan_path)
            except Exception as exc:  # noqa: BLE001
                fix_plan_error = str(exc)
        else:
            fix_plan_error = f"Missing fix plan: {fix_plan_path}"

    counts = fix_plan.get("counts", {}) if isinstance(fix_plan, dict) else {}
    coverage = fix_plan.get("coverage", {}) if isinstance(fix_plan, dict) else {}
    must_fix_open = int(counts.get("must_fix_open", 0) or 0) if isinstance(counts, dict) else 0
    gate_passed = must_fix_open == 0
    status = {
        "success": True,
        "repo_root": str(repo_root),
        "run_id": str(state.get("run_id") or ""),
        "campaign_name": str(state.get("campaign_name") or ""),
        "cadence": str(state.get("cadence") or ""),
        "website_id": str(state.get("website_id") or ""),
        "status": str(state.get("status") or ""),
        "current_phase": str(state.get("current_phase") or ""),
        "sources": state.get("sources", []),
        "paths": state.get("paths", {}),
        "fix_plan_counts": counts if isinstance(counts, dict) else {},
        "coverage": {
            "all_findings_triaged": bool(coverage.get("all_findings_triaged", True)) if isinstance(coverage, dict) else True,
            "must_fix_gate_passed": bool(coverage.get("must_fix_gate_passed", gate_passed))
            if isinstance(coverage, dict)
            else gate_passed,
        },
        "must_fix_open": must_fix_open,
        "next_action": str(state.get("next_action") or ""),
        "fix_plan_error": fix_plan_error,
        "state_path": str(state.get("_state_path") or ""),
        "resolved_latest": bool(state.get("_resolved_latest", False)),
    }
    return status
