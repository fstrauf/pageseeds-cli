"""Plain Python CLI for automation workflows.

Goal: run the same underlying functions as the MCP server, but without
starting any MCP servers. Intended to be executed via uv, e.g.:

  uv run --directory packages/automation-cli automation-cli reddit pending --project expense --severity CRITICAL
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from .campaign import (
    archive_campaign,
    campaign_status,
    carry_over_items,
    collect_campaign_data,
    create_campaign_run,
    execute_campaign_batch,
    plan_campaign,
    prune_campaigns,
    transition_item,
)
from . import version_check


def _print_json(data: object) -> None:
    sys.stdout.write(json.dumps(data, indent=2, ensure_ascii=False))
    sys.stdout.write("\n")


def _read_text_arg(text: str | None, text_file: str | None) -> str:
    if text is not None and text_file is not None:
        raise SystemExit("Provide only one of --reply-text or --reply-text-file")

    if text is not None:
        return text

    if text_file is None:
        return ""

    if text_file == "-":
        return sys.stdin.read()

    return Path(text_file).read_text(encoding="utf-8")


def _read_json_arg(json_text: str | None, json_file: str | None) -> object:
    if json_text is not None and json_file is not None:
        raise SystemExit("Provide only one of --json or --json-file")

    if json_text is not None:
        return json.loads(json_text)

    if json_file is None:
        raise SystemExit("Provide one of --json or --json-file")

    if json_file == "-":
        return json.loads(sys.stdin.read())

    return json.loads(Path(json_file).read_text(encoding="utf-8"))


def _find_ancestor_dir_with(start: Path, rel: Path) -> Path | None:
    """Find the nearest ancestor directory that contains `rel`."""
    start = start.resolve()
    for p in (start,) + tuple(start.parents):
        if (p / rel).exists():
            return p
    return None


def _iter_copy_plan(src_root: Path, dst_root: Path) -> list[dict[str, str]]:
    """Return a list of file copy operations (src->dst), excluding obvious junk."""
    ops: list[dict[str, str]] = []
    for src_path in src_root.rglob("*"):
        if src_path.is_dir():
            continue
        if src_path.name in {".DS_Store"}:
            continue
        if src_path.suffix in {".pyc"}:
            continue
        rel = src_path.relative_to(src_root)
        if "__pycache__" in rel.parts:
            continue
        if rel.name == ".gitkeep":
            continue
        dst_path = dst_root / rel
        ops.append({"src": str(src_path), "dst": str(dst_path)})
    return ops


def _apply_copy_plan(
    ops: list[dict[str, str]],
    *,
    dry_run: bool,
    force: bool,
) -> dict[str, object]:
    copied: list[dict[str, str]] = []
    skipped_existing: list[dict[str, str]] = []
    failures: list[dict[str, str]] = []

    for op in ops:
        src = Path(op["src"])
        dst = Path(op["dst"])
        if dst.exists() and not force:
            skipped_existing.append(op)
            continue
        try:
            if not dry_run:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            copied.append(op)
        except Exception as exc:  # noqa: BLE001
            failures.append({"src": str(src), "dst": str(dst), "error": str(exc)})

    return {
        "copied": copied,
        "skipped_existing": skipped_existing,
        "failures": failures,
        "success": len(failures) == 0,
    }


def _read_json_file(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json_file(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _safe_relpath(path: Path) -> str:
    return str(path.as_posix())


def _ensure_symlink(*, link_path: Path, target_path: Path, force: bool, dry_run: bool) -> dict[str, str]:
    """Create/replace a symlink."""
    result: dict[str, str] = {"link": str(link_path), "target": str(target_path)}

    if link_path.exists() or link_path.is_symlink():
        if not force:
            result["action"] = "skipped_exists"
            return result
        if not dry_run:
            if link_path.is_dir() and not link_path.is_symlink():
                shutil.rmtree(link_path)
            else:
                link_path.unlink()

    if not dry_run:
        link_path.parent.mkdir(parents=True, exist_ok=True)
        link_path.symlink_to(target_path)
    result["action"] = "linked"
    return result


def _ensure_copy_file(*, dst_path: Path, src_path: Path, force: bool, dry_run: bool) -> dict[str, str]:
    result: dict[str, str] = {"dst": str(dst_path), "src": str(src_path)}
    if dst_path.exists():
        if not force:
            result["action"] = "skipped_exists"
            return result
        if not dry_run:
            dst_path.unlink()
    if not dry_run:
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, dst_path)
    result["action"] = "copied"
    return result


def _ensure_copy_dir(*, dst_dir: Path, src_dir: Path, force: bool, dry_run: bool) -> dict[str, str]:
    result: dict[str, str] = {"dst": str(dst_dir), "src": str(src_dir)}
    if dst_dir.exists() or dst_dir.is_symlink():
        if not force:
            result["action"] = "skipped_exists"
            return result
        if not dry_run:
            # shutil.rmtree refuses symlinks; treat symlink targets as "the link itself".
            if dst_dir.is_symlink():
                dst_dir.unlink()
            else:
                shutil.rmtree(dst_dir)
    if not dry_run:
        dst_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src_dir, dst_dir)
    result["action"] = "copied"
    return result


def _try_relpath(repo_root: Path, p: Path) -> str:
    """Return a repo-relative path if possible, else absolute."""
    try:
        return str(p.resolve().relative_to(repo_root.resolve()).as_posix())
    except Exception:
        return str(p.resolve())


def _seo_init(args: argparse.Namespace) -> None:
    repo_root = Path(args.repo_root).expanduser().resolve() if args.repo_root else Path.cwd().resolve()
    workspace_dir = (repo_root / str(args.workspace_dir)).resolve()

    # Clean, single-site workspace: no registry file required.
    # We keep `articles.json` in the workspace and point `content` at the canonical content dir.
    site_id = (getattr(args, "site_id", "") or getattr(args, "website_id", "") or "").strip()
    content_dir_arg = (args.content_dir or args.source_content_dir or "").strip()
    if not content_dir_arg:
        raise SystemExit("Missing --content-dir (or legacy --source-content-dir)")

    source_repo = Path(args.source_repo).expanduser().resolve() if getattr(args, "source_repo", "") else repo_root
    content_target = Path(content_dir_arg).expanduser()
    if not content_target.is_absolute():
        content_target = (source_repo / content_target).resolve()
    else:
        content_target = content_target.resolve()

    link_mode = (args.link_mode or "symlink").strip().lower()
    if link_mode not in {"symlink", "copy"}:
        raise SystemExit("--link-mode must be one of: symlink, copy")

    reset_articles = bool(getattr(args, "reset_articles", False))
    dry_run = bool(args.dry_run)
    force = bool(args.force)

    content_path = workspace_dir / "content"
    articles_path = workspace_dir / "articles.json"
    config_path = workspace_dir / "seo_workspace.json"
    legacy_registry = workspace_dir / "WEBSITES_REGISTRY.json"
    legacy_sites_dir = workspace_dir / "sites"

    planned: list[dict[str, object]] = []

    planned.append({"action": "mkdir", "path": str(workspace_dir)})
    if not dry_run:
        workspace_dir.mkdir(parents=True, exist_ok=True)

    # Remove legacy files if present (only when forced).
    if force and legacy_registry.exists():
        planned.append({"action": "cleanup", "path": str(legacy_registry), "reason": "remove_legacy_registry"})
        if not dry_run:
            legacy_registry.unlink()
    if force and legacy_sites_dir.exists():
        planned.append({"action": "cleanup", "path": str(legacy_sites_dir), "reason": "remove_legacy_sites_dir"})
        if not dry_run:
            shutil.rmtree(legacy_sites_dir)

    # Ensure workspace articles.json exists (optionally seeded from a source file).
    seed_articles = (args.articles_json or "").strip()
    if seed_articles:
        seed_path = Path(seed_articles).expanduser().resolve()
        planned.append(
            _ensure_copy_file(
                dst_path=articles_path,
                src_path=seed_path,
                force=(force or reset_articles),
                dry_run=dry_run,
            )
        )
    else:
        planned.append({"action": "ensure_articles_json", "path": str(articles_path), "reset": reset_articles})
        if not dry_run and (reset_articles or not articles_path.exists()):
            articles_path.write_text(json.dumps({"articles": []}, indent=2) + "\n", encoding="utf-8")

    # Point workspace content at canonical content.
    if link_mode == "copy":
        planned.append(_ensure_copy_dir(dst_dir=content_path, src_dir=content_target, force=force, dry_run=dry_run))
    else:
        planned.append(_ensure_symlink(link_path=content_path, target_path=content_target, force=force, dry_run=dry_run))

    cfg = {
        "schema": 1,
        "site_id": site_id,
        "workspace_dir": _try_relpath(repo_root, workspace_dir),
        "website_path": ".",
        "articles_json": _try_relpath(repo_root, articles_path),
        "content_dir": _try_relpath(repo_root, content_target),
        "link_mode": link_mode,
    }
    planned.append({"action": "write_config", "path": str(config_path)})
    if not dry_run:
        _write_json_file(config_path, cfg)

    _print_json(
        {
            "success": True,
            "repo_root": str(repo_root),
            "workspace_root": str(workspace_dir),
            "config_path": str(config_path),
            "site_id": site_id,
            "dry_run": dry_run,
            "force": force,
            "planned": planned,
            "recommended_commands": {
                "articles_summary": f"seo-content-cli --workspace-root {workspace_dir} articles-summary --website-path .",
                "validate_content": f"seo-content-cli --workspace-root {workspace_dir} validate-content --website-path .",
            },
        }
    )


def _seo_status(args: argparse.Namespace) -> None:
    repo_root = Path(args.repo_root).expanduser().resolve() if args.repo_root else Path.cwd().resolve()
    workspace_dir = (repo_root / str(args.workspace_dir)).resolve()
    config_path = workspace_dir / "seo_workspace.json"
    legacy_registry = workspace_dir / "WEBSITES_REGISTRY.json"
    content_path = workspace_dir / "content"
    articles_path = workspace_dir / "articles.json"

    cfg: dict[str, object] = {}
    cfg_error = ""
    if config_path.exists():
        try:
            cfg = _read_json_file(config_path)
        except Exception as exc:  # noqa: BLE001
            cfg_error = str(exc)

    def _link_target(p: Path) -> str:
        try:
            if p.is_symlink():
                return str(p.readlink())
        except Exception:
            return ""
        return ""

    _print_json(
        {
            "success": True,
            "repo_root": str(repo_root),
            "workspace_root": str(workspace_dir),
            "config_path": str(config_path),
            "config_present": config_path.exists(),
            "config_error": cfg_error,
            "config": cfg,
            "legacy_registry_present": legacy_registry.exists(),
            "articles_json": {
                "path": str(articles_path),
                "present": articles_path.exists(),
                "is_symlink": articles_path.is_symlink(),
                "symlink_target": _link_target(articles_path),
            },
            "content": {
                "path": str(content_path),
                "present": content_path.exists(),
                "is_symlink": content_path.is_symlink(),
                "symlink_target": _link_target(content_path),
            },
            "recommended_commands": {
                "articles_summary": f"seo-content-cli --workspace-root {workspace_dir} articles-summary --website-path .",
                "validate_content": f"seo-content-cli --workspace-root {workspace_dir} validate-content --website-path .",
            },
        }
    )


def _load_posthog_config(repo_root: Path) -> dict:
    """Load posthog_config.json from automation/ folder if it exists.
    
    Checks both:
    - {repo_root}/.github/automation/posthog_config.json (preferred)
    - {repo_root}/automation/posthog_config.json (legacy)
    """
    config_paths = [
        repo_root / ".github" / "automation" / "posthog_config.json",
        repo_root / "automation" / "posthog_config.json",
    ]
    for config_path in config_paths:
        if config_path.exists():
            try:
                return json.loads(config_path.read_text(encoding="utf-8"))
            except Exception:
                return {}
    return {}


def _posthog_report(args: argparse.Namespace) -> None:
    """
    Run multi-site PostHog pull + summary using centralized tool code.
    """
    payload_root = _payload_root_from_cli()
    if payload_root is None:
        raise SystemExit("Cannot auto-detect automation repo root for PostHog tooling.")

    script_path = (payload_root / "tools" / "posthog_help" / "posthog_report.py").resolve()
    if not script_path.exists():
        raise SystemExit(f"Missing script: {script_path}")

    repo_root = Path(args.repo_root).expanduser().resolve() if args.repo_root else Path.cwd().resolve()
    
    # Auto-detect posthog_config.json if no explicit project_id provided
    config = _load_posthog_config(repo_root)
    project_id = args.project_id if args.project_id is not None else config.get("project_id")
    api_key_env = args.api_key_env if args.api_key_env else config.get("api_key_env")
    base_url = args.base_url if args.base_url else config.get("base_url")
    
    cmd: list[str] = [
        "uv",
        "run",
        "--no-project",  # Prevent uv from finding pyproject.toml and installing deps
        str(script_path),
        "--repo-root",
        str(repo_root),
        "--refresh",  # Always refresh insights to get actual data (not cached nulls)
    ]
    if args.registry:
        cmd.extend(["--registry", str(args.registry)])
    if args.manifests_dir:
        cmd.extend(["--manifests-dir", str(args.manifests_dir)])
    if project_id is not None:
        cmd.extend(["--project-id", str(int(project_id))])
    if api_key_env:
        cmd.extend(["--api-key-env", str(api_key_env)])
    if base_url:
        cmd.extend(["--base-url", str(base_url)])
    
    # Dashboard names from args take precedence over config
    dashboard_names = list(args.dashboard_name) if args.dashboard_name else []
    if not dashboard_names and config.get("dashboard_names"):
        cfg_dashboards = config["dashboard_names"]
        if isinstance(cfg_dashboards, list):
            dashboard_names = [str(d) for d in cfg_dashboards if str(d).strip()]
        elif isinstance(cfg_dashboards, str) and cfg_dashboards.strip():
            dashboard_names = [cfg_dashboards.strip()]
    for dname in dashboard_names:
        cmd.extend(["--dashboard-name", str(dname)])
    for insight_id in args.insight_id or []:
        cmd.extend(["--insight-id", str(int(insight_id))])

    if args.out_dir:
        cmd.extend(["--out-dir", str(args.out_dir)])
    if bool(args.refresh):
        cmd.append("--refresh")
    if bool(args.list_dashboards):
        cmd.append("--list-dashboards")
    if int(args.timeout) > 0:
        cmd.extend(["--timeout", str(int(args.timeout))])
    if int(args.max_insights) > 0:
        cmd.extend(["--max-insights", str(int(args.max_insights))])
    if int(args.extra_insights) > 0:
        cmd.extend(["--extra-insights", str(int(args.extra_insights))])
    for site in args.site or []:
        cmd.extend(["--site", str(site)])
    for env_file in args.env_file or []:
        cmd.extend(["--env-file", str(env_file)])

    proc = subprocess.run(cmd, cwd=str(repo_root), check=False)
    raise SystemExit(proc.returncode)


def _posthog_list_projects(args: argparse.Namespace) -> None:
    payload_root = _payload_root_from_cli()
    if payload_root is None:
        raise SystemExit("Cannot auto-detect automation repo root for PostHog tooling.")

    script_path = (payload_root / "tools" / "posthog_help" / "posthog_report.py").resolve()
    if not script_path.exists():
        raise SystemExit(f"Missing script: {script_path}")

    repo_root = Path(args.repo_root).expanduser().resolve() if args.repo_root else Path.cwd().resolve()
    cmd: list[str] = [
        "uv",
        "run",
        "--python",
        sys.executable,
        str(script_path),
        "--repo-root",
        str(repo_root),
        "--api-key-env",
        str(args.api_key_env),
        "--list-projects",
    ]
    if args.base_url:
        cmd.extend(["--base-url", str(args.base_url)])
    if args.out_dir:
        cmd.extend(["--out-dir", str(args.out_dir)])
    for env_file in args.env_file or []:
        cmd.extend(["--env-file", str(env_file)])

    proc = subprocess.run(cmd, cwd=str(repo_root), check=False)
    raise SystemExit(proc.returncode)


def _posthog_list_dashboards(args: argparse.Namespace) -> None:
    payload_root = _payload_root_from_cli()
    if payload_root is None:
        raise SystemExit("Cannot auto-detect automation repo root for PostHog tooling.")

    script_path = (payload_root / "tools" / "posthog_help" / "posthog_report.py").resolve()
    if not script_path.exists():
        raise SystemExit(f"Missing script: {script_path}")

    repo_root = Path(args.repo_root).expanduser().resolve() if args.repo_root else Path.cwd().resolve()
    cmd: list[str] = [
        "uv",
        "run",
        "--python",
        sys.executable,
        str(script_path),
        "--repo-root",
        str(repo_root),
        "--api-key-env",
        str(args.api_key_env),
        "--project-id",
        str(int(args.project_id)),
        "--list-dashboards",
    ]
    if args.base_url:
        cmd.extend(["--base-url", str(args.base_url)])
    if args.out_dir:
        cmd.extend(["--out-dir", str(args.out_dir)])
    for env_file in args.env_file or []:
        cmd.extend(["--env-file", str(env_file)])

    proc = subprocess.run(cmd, cwd=str(repo_root), check=False)
    raise SystemExit(proc.returncode)


def _posthog_action_queue(args: argparse.Namespace) -> None:
    """
    Build deterministic PostHog action queue from per-site packets.
    """
    payload_root = _payload_root_from_cli()
    if payload_root is None:
        raise SystemExit("Cannot auto-detect automation repo root for PostHog tooling.")

    script_path = (payload_root / "tools" / "posthog_help" / "posthog_action_queue.py").resolve()
    if not script_path.exists():
        raise SystemExit(f"Missing script: {script_path}")

    repo_root = Path(args.repo_root).expanduser().resolve() if args.repo_root else Path.cwd().resolve()
    cmd: list[str] = [
        "uv",
        "run",
        "--python",
        sys.executable,
        str(script_path),
        "--repo-root",
        str(repo_root),
        "--max-actions",
        str(int(args.max_actions)),
        "--max-per-site",
        str(int(args.max_per_site)),
    ]
    if args.date:
        cmd.extend(["--date", str(args.date)])
    if args.out_dir:
        cmd.extend(["--out-dir", str(args.out_dir)])
    if bool(args.write_md):
        cmd.append("--write-md")

    proc = subprocess.run(cmd, cwd=str(repo_root), check=False)
    raise SystemExit(proc.returncode)


def _posthog_view(args: argparse.Namespace) -> None:
    """
    View extracted fields from PostHog insights JSON output.
    Eliminates need for ad-hoc jq/python parsing.
    """
    repo_root = Path(args.repo_root).expanduser().resolve() if args.repo_root else Path.cwd().resolve()
    out_dir = repo_root / ".github" / "automation" / "output" / "posthog"
    if args.out_dir:
        out_dir = Path(args.out_dir).expanduser()
        if not out_dir.is_absolute():
            out_dir = (repo_root / out_dir).resolve()

    # Find the latest insights file
    import glob
    pattern = str(out_dir / "*_insights.json")
    files = glob.glob(pattern)
    if not files:
        _print_json({"error": f"No *_insights.json files found in {out_dir}"})
        raise SystemExit(1)
    
    # Sort by mtime, most recent first
    files.sort(key=lambda p: Path(p).stat().st_mtime, reverse=True)
    latest_file = Path(files[0])

    try:
        data = json.loads(latest_file.read_text(encoding="utf-8"))
    except Exception as e:
        _print_json({"error": f"Failed to read {latest_file}: {e}"})
        raise SystemExit(1)

    field = args.field
    site_id = str(data.get("site_id") or data.get("site_name") or "unknown")
    
    if field == "situations":
        situations = data.get("situations", [])
        if args.format == "json":
            _print_json({"site_id": site_id, "situations": situations})
        else:
            # Lines format: one situation per line
            for s in situations:
                label = s.get("label", "unknown")
                evidence = s.get("evidence", "")
                confidence = s.get("confidence", "")
                print(f"[{confidence}] {label}: {evidence}")
    
    elif field == "action_candidates":
        actions = data.get("action_candidates", [])
        if args.format == "json":
            _print_json({"site_id": site_id, "action_candidates": actions})
        else:
            # Lines format
            for a in actions:
                priority = a.get("priority", "P?")
                owner = a.get("owner_surface", "unknown")
                next_step = a.get("next_step", "")
                print(f"[{priority}] {owner}: {next_step}")
    
    elif field == "insights":
        insights = data.get("insights", {})
        if args.format == "json":
            _print_json({"site_id": site_id, "insights": insights})
        else:
            # Lines format: key, name, latest value
            for key, val in insights.items():
                if isinstance(val, dict):
                    name = val.get("name", key)
                    latest = val.get("latest", "N/A")
                    pct = val.get("pct_change_vs_prev_point")
                    pct_str = f" ({pct:+.1f}%)" if pct is not None else ""
                    print(f"{key}: {name} = {latest}{pct_str}")
    
    elif field == "page_traffic":
        pages = data.get("page_traffic", [])
        if args.format == "json":
            _print_json({"site_id": site_id, "page_traffic": pages})
        else:
            for p in pages:
                page = p.get("page", "")
                latest = p.get("latest", "")
                print(f"{page}: {latest}")
    
    elif field == "breakdowns":
        # Extract breakdown values from insights with breakdown data
        breakdowns = []
        for key, item in data.get("insights", {}).items():
            if not isinstance(item, dict):
                continue
            raw = item.get("raw", {})
            result = raw.get("result", [])
            if not isinstance(result, list):
                continue
            insight_name = item.get("name", key)
            for series in result:
                if not isinstance(series, dict):
                    continue
                breakdown_val = series.get("breakdown_value")
                if breakdown_val:
                    # Handle array breakdown values (e.g., ["Chrome"])
                    if isinstance(breakdown_val, list):
                        breakdown_val = breakdown_val[0] if breakdown_val else ""
                    label = str(breakdown_val)
                    aggregated = series.get("aggregated_value")
                    if isinstance(aggregated, (int, float)):
                        breakdowns.append({
                            "insight": insight_name,
                            "value": label,
                            "count": aggregated
                        })
        
        if args.format == "json":
            _print_json({"site_id": site_id, "breakdowns": breakdowns})
        else:
            current_insight = ""
            for b in breakdowns:
                if b["insight"] != current_insight:
                    current_insight = b["insight"]
                    print(f"\n{current_insight}:")
                print(f"  {b['value']}: {b['count']}")
    
    else:
        _print_json({"error": f"Unknown field: {field}"})
        raise SystemExit(1)


def _seo_gsc_indexing_report(args: argparse.Namespace) -> None:
    """
    Run the GSC URL Inspection indexing report using the centralized tool code
    from the automation repo (no vendoring into target repos).
    """
    payload_root = _payload_root_from_cli()
    if payload_root is None:
        raise SystemExit("Cannot auto-detect automation repo root for GSC tooling.")

    script_path = (payload_root / "tools" / "seo_help" / "gsc_indexing_report.py").resolve()
    req_path = (payload_root / "tools" / "seo_help" / "requirements.txt").resolve()
    if not script_path.exists():
        raise SystemExit(f"Missing script: {script_path}")
    if not req_path.exists():
        raise SystemExit(f"Missing requirements: {req_path}")

    repo_root = Path(args.repo_root).expanduser().resolve() if args.repo_root else Path.cwd().resolve()
    workspace_dir = (repo_root / str(args.workspace_dir)).resolve()
    out_dir = Path(args.out_dir).expanduser() if getattr(args, "out_dir", "") else (repo_root / ".github" / "automation" / "output" / "gsc_indexing")
    out_dir = out_dir if out_dir.is_absolute() else (repo_root / out_dir).resolve()

    cmd: list[str] = [
        "uv",
        "run",
        "--with-requirements",
        str(req_path),
        "python",
        str(script_path),
        "--out-dir",
        str(out_dir),
        "--limit",
        str(int(args.limit)),
        "--workers",
        str(int(args.workers)),
        "--samples-per-bucket",
        str(int(args.samples_per_bucket)),
    ]

    if args.language:
        cmd.extend(["--language", str(args.language)])
    if args.manifest:
        cmd.extend(["--manifest", str(args.manifest)])
    if args.site:
        cmd.extend(["--site", str(args.site)])
    if args.sitemap_url:
        cmd.extend(["--sitemap-url", str(args.sitemap_url)])
    if args.urls_file:
        cmd.extend(["--urls-file", str(args.urls_file)])
    if args.service_account_path:
        cmd.extend(["--service-account-path", str(args.service_account_path)])
    if args.delegated_user:
        cmd.extend(["--delegated-user", str(args.delegated_user)])
    if args.oauth_client_secrets:
        cmd.extend(["--oauth-client-secrets", str(args.oauth_client_secrets)])
    if bool(args.list_sites):
        cmd.append("--list-sites")
    if bool(args.include_raw):
        cmd.append("--include-raw")

    proc = subprocess.run(cmd, cwd=str(repo_root), check=False)
    raise SystemExit(proc.returncode)


def _seo_gsc_page_context(args: argparse.Namespace) -> None:
    """
    Run single-page GSC context pull (performance + inspection + site context).
    """
    payload_root = _payload_root_from_cli()
    if payload_root is None:
        raise SystemExit("Cannot auto-detect automation repo root for GSC tooling.")

    script_path = (payload_root / "tools" / "seo_help" / "gsc_page_context.py").resolve()
    req_path = (payload_root / "tools" / "seo_help" / "requirements.txt").resolve()
    if not script_path.exists():
        raise SystemExit(f"Missing script: {script_path}")
    if not req_path.exists():
        raise SystemExit(f"Missing requirements: {req_path}")

    repo_root = Path(args.repo_root).expanduser().resolve() if args.repo_root else Path.cwd().resolve()
    workspace_dir = (repo_root / str(args.workspace_dir)).resolve()
    out_dir = Path(args.out_dir).expanduser() if getattr(args, "out_dir", "") else (repo_root / ".github" / "automation" / "output" / "gsc_page_context")
    out_dir = out_dir if out_dir.is_absolute() else (repo_root / out_dir).resolve()

    cmd: list[str] = [
        "uv",
        "run",
        "--with-requirements",
        str(req_path),
        "python",
        str(script_path),
        "--url",
        str(args.url),
        "--compare-days",
        str(int(args.compare_days)),
        "--long-compare-days",
        str(int(args.long_compare_days)),
        "--queries-limit",
        str(int(args.queries_limit)),
        "--queries-fetch-limit",
        str(int(args.queries_fetch_limit)),
        "--language",
        str(args.language),
        "--repo-root",
        str(repo_root),
        "--out-dir",
        str(out_dir),
    ]

    if args.manifest:
        cmd.extend(["--manifest", str(args.manifest)])
    if args.site:
        cmd.extend(["--site", str(args.site)])
    if args.service_account_path:
        cmd.extend(["--service-account-path", str(args.service_account_path)])
    if args.delegated_user:
        cmd.extend(["--delegated-user", str(args.delegated_user)])
    if args.oauth_client_secrets:
        cmd.extend(["--oauth-client-secrets", str(args.oauth_client_secrets)])
    if args.action_queue:
        cmd.extend(["--action-queue", str(args.action_queue)])

    proc = subprocess.run(cmd, cwd=str(repo_root), check=False)
    raise SystemExit(proc.returncode)


def _seo_gsc_site_scan(args: argparse.Namespace) -> None:
    """
    Run multi-page GSC site scan (candidate selection + per-page context).
    """
    payload_root = _payload_root_from_cli()
    if payload_root is None:
        raise SystemExit("Cannot auto-detect automation repo root for GSC tooling.")

    script_path = (payload_root / "tools" / "seo_help" / "gsc_site_scan.py").resolve()
    req_path = (payload_root / "tools" / "seo_help" / "requirements.txt").resolve()
    if not script_path.exists():
        raise SystemExit(f"Missing script: {script_path}")
    if not req_path.exists():
        raise SystemExit(f"Missing requirements: {req_path}")

    repo_root = Path(args.repo_root).expanduser().resolve() if args.repo_root else Path.cwd().resolve()
    workspace_dir = (repo_root / str(args.workspace_dir)).resolve()
    out_dir = Path(args.out_dir).expanduser() if getattr(args, "out_dir", "") else (repo_root / ".github" / "automation" / "output" / "gsc_site_scan")
    out_dir = out_dir if out_dir.is_absolute() else (repo_root / out_dir).resolve()

    cmd: list[str] = [
        "uv",
        "run",
        "--with-requirements",
        str(req_path),
        "python",
        str(script_path),
        "--repo-root",
        str(repo_root),
        "--out-dir",
        str(out_dir),
        "--compare-days",
        str(int(args.compare_days)),
        "--long-compare-days",
        str(int(args.long_compare_days)),
        "--top-pages",
        str(int(args.top_pages)),
        "--decliners",
        str(int(args.decliners)),
        "--max-pages",
        str(int(args.max_pages)),
        "--fetch-pages-limit",
        str(int(args.fetch_pages_limit)),
        "--non-pass-pool",
        str(int(args.non_pass_pool)),
        "--queries-limit",
        str(int(args.queries_limit)),
        "--queries-fetch-limit",
        str(int(args.queries_fetch_limit)),
        "--language",
        str(args.language),
    ]

    if args.manifest:
        cmd.extend(["--manifest", str(args.manifest)])
    if args.site:
        cmd.extend(["--site", str(args.site)])
    if args.service_account_path:
        cmd.extend(["--service-account-path", str(args.service_account_path)])
    if args.delegated_user:
        cmd.extend(["--delegated-user", str(args.delegated_user)])
    if args.oauth_client_secrets:
        cmd.extend(["--oauth-client-secrets", str(args.oauth_client_secrets)])
    if args.action_queue:
        cmd.extend(["--action-queue", str(args.action_queue)])

    proc = subprocess.run(cmd, cwd=str(repo_root), check=False)
    raise SystemExit(proc.returncode)


def _seo_gsc_watch(args: argparse.Namespace) -> None:
    """
    Run ongoing GSC watch feed (alerts + opportunities + drift).
    """
    payload_root = _payload_root_from_cli()
    if payload_root is None:
        raise SystemExit("Cannot auto-detect automation repo root for GSC tooling.")

    script_path = (payload_root / "tools" / "seo_help" / "gsc_watch.py").resolve()
    req_path = (payload_root / "tools" / "seo_help" / "requirements.txt").resolve()
    if not script_path.exists():
        raise SystemExit(f"Missing script: {script_path}")
    if not req_path.exists():
        raise SystemExit(f"Missing requirements: {req_path}")

    repo_root = Path(args.repo_root).expanduser().resolve() if args.repo_root else Path.cwd().resolve()
    workspace_dir = (repo_root / str(args.workspace_dir)).resolve()
    out_dir = Path(args.out_dir).expanduser() if getattr(args, "out_dir", "") else (repo_root / ".github" / "automation" / "output" / "gsc_watch")
    out_dir = out_dir if out_dir.is_absolute() else (repo_root / out_dir).resolve()

    cmd: list[str] = [
        "uv",
        "run",
        "--with-requirements",
        str(req_path),
        "python",
        str(script_path),
        "--repo-root",
        str(repo_root),
        "--out-dir",
        str(out_dir),
        "--compare-days",
        str(int(args.compare_days)),
        "--long-compare-days",
        str(int(args.long_compare_days)),
        "--fetch-pages-limit",
        str(int(args.fetch_pages_limit)),
        "--alerts-limit",
        str(int(args.alerts_limit)),
        "--opps-limit",
        str(int(args.opps_limit)),
        "--inspect-top-drops",
        str(int(args.inspect_top_drops)),
        "--drift-limit",
        str(int(args.drift_limit)),
        "--language",
        str(args.language),
    ]

    if args.manifest:
        cmd.extend(["--manifest", str(args.manifest)])
    if args.site:
        cmd.extend(["--site", str(args.site)])
    if args.service_account_path:
        cmd.extend(["--service-account-path", str(args.service_account_path)])
    if args.delegated_user:
        cmd.extend(["--delegated-user", str(args.delegated_user)])
    if args.oauth_client_secrets:
        cmd.extend(["--oauth-client-secrets", str(args.oauth_client_secrets)])
    if args.action_queue:
        cmd.extend(["--action-queue", str(args.action_queue)])

    proc = subprocess.run(cmd, cwd=str(repo_root), check=False)
    raise SystemExit(proc.returncode)


def _resolve_action_queue_path(args: argparse.Namespace) -> Path:
    repo_root = Path(args.repo_root).expanduser().resolve() if args.repo_root else Path.cwd().resolve()
    action_queue_arg = (getattr(args, "action_queue", "") or "").strip()
    if action_queue_arg:
        queue_path = Path(action_queue_arg).expanduser()
        if not queue_path.is_absolute():
            queue_path = (repo_root / queue_path).resolve()
        if not queue_path.exists():
            raise SystemExit(f"Action queue not found: {queue_path}")
        return queue_path

    workspace_dir = (repo_root / str(args.workspace_dir)).resolve()
    out_dir = repo_root / ".github" / "automation" / "output" / "gsc_indexing"
    if not out_dir.exists():
        raise SystemExit(f"Missing output directory: {out_dir}")

    candidates = sorted(
        out_dir.glob("*_action_queue.json"),
        key=lambda p: (p.stat().st_mtime, p.name),
        reverse=True,
    )
    if not candidates:
        raise SystemExit(
            "No *_action_queue.json files found. "
            "Run Step 6 first (automation-cli seo gsc-indexing-report) or pass --action-queue."
        )
    return candidates[0]


def _queue_item_field_value(item: dict, field: str) -> str:
    article = item.get("article") if isinstance(item.get("article"), dict) else {}
    if field == "url":
        return str(item.get("url") or "")
    if field == "path":
        return str(item.get("path") or "")
    if field == "reason_code":
        return str(item.get("reason_code") or "")
    if field == "basename":
        return str(article.get("basename") or "")
    if field == "file":
        return str(article.get("file") or "")
    if field == "title":
        return str(article.get("title") or "")
    if field == "url_slug":
        return str(article.get("url_slug") or "")
    if field == "id":
        return str(article.get("id") or "")
    if field == "url_to_file":
        file_path = str(article.get("file") or "")
        if not file_path:
            return ""
        return f"{str(item.get('url') or '')}\t{file_path}"
    return ""


def _is_not_indexed_coverage(item: dict) -> bool:
    coverage_state = str(item.get("coverageState") or "").strip().lower()
    return "not indexed" in coverage_state


def _seo_gsc_action_queue(args: argparse.Namespace) -> None:
    if bool(args.mapped_only) and bool(args.unmapped_only):
        raise SystemExit("Use only one of --mapped-only or --unmapped-only")

    queue_path = _resolve_action_queue_path(args)
    try:
        payload = _read_json_file(queue_path)
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"Failed to read action queue JSON: {exc}") from exc

    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise SystemExit(f"Invalid action queue format (missing list at items): {queue_path}")

    reason_codes = {v.strip().lower() for v in (args.reason_code or []) if v.strip()}
    coverage_contains = [v.strip().lower() for v in (args.coverage_contains or []) if v.strip()]
    verdict = (args.verdict or "").strip().lower()
    include_indexed_pass = bool(args.include_indexed_pass)

    filtered: list[dict] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        reason_code = str(item.get("reason_code") or "")
        if not include_indexed_pass and reason_code == "indexed_pass":
            continue
        if reason_codes and reason_code.lower() not in reason_codes:
            continue
        mapped = bool(item.get("mapped_to_article"))
        if bool(args.mapped_only) and not mapped:
            continue
        if bool(args.unmapped_only) and mapped:
            continue
        if verdict and str(item.get("verdict") or "").strip().lower() != verdict:
            continue
        if coverage_contains:
            coverage_state = str(item.get("coverageState") or "").lower()
            if not any(needle in coverage_state for needle in coverage_contains):
                continue
        filtered.append(item)

    limit = int(args.limit)
    if limit > 0:
        filtered = filtered[:limit]

    if args.format == "lines":
        values = [_queue_item_field_value(item, args.field) for item in filtered]
        values = [v for v in values if v]
        if bool(args.unique):
            seen: set[str] = set()
            deduped: list[str] = []
            for v in values:
                if v in seen:
                    continue
                seen.add(v)
                deduped.append(v)
            values = deduped
        sys.stdout.write("\n".join(values))
        if values:
            sys.stdout.write("\n")
        return

    _print_json(
        {
            "success": True,
            "action_queue_path": str(queue_path),
            "total_items": len(raw_items),
            "selected_items": len(filtered),
            "filters": {
                "reason_code": sorted(reason_codes),
                "coverage_contains": coverage_contains,
                "verdict": verdict,
                "mapped_only": bool(args.mapped_only),
                "unmapped_only": bool(args.unmapped_only),
                "include_indexed_pass": include_indexed_pass,
                "limit": limit,
            },
            "items": filtered,
        }
    )


def _seo_gsc_remediation_inputs(args: argparse.Namespace) -> None:
    """
    Deterministic Step 7 starter input selector.

    This intentionally mirrors the common ad-hoc query:
    - coverageState contains "not indexed"
    - emit first N URLs (or mapped file fields)
    """
    queue_path = _resolve_action_queue_path(args)
    try:
        payload = _read_json_file(queue_path)
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"Failed to read action queue JSON: {exc}") from exc

    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise SystemExit(f"Invalid action queue format (missing list at items): {queue_path}")

    selected: list[dict] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        if not _is_not_indexed_coverage(item):
            continue
        if bool(args.mapped_only) and not bool(item.get("mapped_to_article")):
            continue
        selected.append(item)

    limit = int(args.limit)
    if limit > 0:
        selected = selected[:limit]

    if args.format == "lines":
        values = [_queue_item_field_value(item, args.field) for item in selected]
        values = [v for v in values if v]
        if bool(args.unique):
            seen: set[str] = set()
            deduped: list[str] = []
            for v in values:
                if v in seen:
                    continue
                seen.add(v)
                deduped.append(v)
            values = deduped
        sys.stdout.write("\n".join(values))
        if values:
            sys.stdout.write("\n")
        return

    _print_json(
        {
            "success": True,
            "action_queue_path": str(queue_path),
            "total_items": len(raw_items),
            "selected_items": len(selected),
            "filters": {
                "coverage_contains": "not indexed",
                "mapped_only": bool(args.mapped_only),
                "limit": limit,
            },
            "items": selected,
        }
    )


def _seo_gsc_remediation_targets(args: argparse.Namespace) -> None:
    """
    Deterministic Step 7 fast-path target selector.

    Returns mapped content targets for URLs where coverageState indicates
    not-indexed status, so agents can move directly to content edits.
    """
    queue_path = _resolve_action_queue_path(args)
    try:
        payload = _read_json_file(queue_path)
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"Failed to read action queue JSON: {exc}") from exc

    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise SystemExit(f"Invalid action queue format (missing list at items): {queue_path}")

    targets: list[dict] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        if not _is_not_indexed_coverage(item):
            continue
        if not bool(item.get("mapped_to_article")):
            continue
        if str(item.get("reason_code") or "") == "indexed_pass":
            continue

        article = item.get("article") if isinstance(item.get("article"), dict) else {}
        file_path = str(article.get("file") or "")
        basename = str(article.get("basename") or "")
        if not file_path or not basename:
            continue

        targets.append(
            {
                "priority": int(item.get("priority") or 500),
                "reason_code": str(item.get("reason_code") or ""),
                "coverageState": str(item.get("coverageState") or ""),
                "url": str(item.get("url") or ""),
                "file": file_path,
                "basename": basename,
                "title": str(article.get("title") or ""),
            }
        )

    limit = int(args.limit)
    if limit > 0:
        targets = targets[:limit]

    if args.format == "lines":
        values: list[str]
        if args.field == "url_to_file":
            values = [f"{t['url']}\t{t['file']}" for t in targets]
        else:
            values = [str(t.get(args.field) or "") for t in targets]
        values = [v for v in values if v]
        if bool(args.unique):
            seen: set[str] = set()
            deduped: list[str] = []
            for v in values:
                if v in seen:
                    continue
                seen.add(v)
                deduped.append(v)
            values = deduped
        sys.stdout.write("\n".join(values))
        if values:
            sys.stdout.write("\n")
        return

    _print_json(
        {
            "success": True,
            "action_queue_path": str(queue_path),
            "total_items": len(raw_items),
            "selected_items": len(targets),
            "filters": {
                "coverage_contains": "not indexed",
                "mapped_to_article": True,
                "exclude_reason_code": "indexed_pass",
                "limit": limit,
            },
            "targets": targets,
        }
    )


def _skills_sync(args: argparse.Namespace) -> None:
    """
    Copy `.github/skills` (and optionally `.github/prompts`) into a target repo.

    This is intentionally a dumb copier: no deletes, no transforms, no templating.
    """
    this_file_dir = Path(__file__).resolve().parent
    default_repo_root = _find_ancestor_dir_with(this_file_dir, Path(".github") / "skills")

    from_root = Path(args.from_root).expanduser().resolve() if args.from_root else default_repo_root
    if from_root is None:
        raise SystemExit("Cannot auto-detect --from-root. Provide --from-root pointing at the automation repo root.")

    src_skills = (from_root / ".github" / "skills").resolve()
    if not src_skills.exists():
        raise SystemExit(f"Missing source skills dir: {src_skills}")

    src_prompts = (from_root / ".github" / "prompts").resolve()
    if args.include_prompts and not src_prompts.exists():
        raise SystemExit(f"Missing source prompts dir: {src_prompts}")

    to_root = Path(args.to).expanduser().resolve()
    # Allow passing either a repo root or the `.github/skills` dir itself.
    if to_root.name == "skills" and to_root.parent.name == ".github":
        target_repo = to_root.parents[1]
    else:
        target_repo = to_root

    dst_skills = (target_repo / ".github" / "skills").resolve()
    dst_prompts = (target_repo / ".github" / "prompts").resolve()

    includes = [s.strip() for s in (args.include or []) if s.strip()]

    plans: list[dict[str, object]] = []

    # Skills: either copy all skill dirs or a filtered subset.
    skill_dirs = [p for p in src_skills.iterdir() if p.is_dir()]
    if includes:
        skill_dirs = [p for p in skill_dirs if p.name in set(includes)]
        missing = sorted(set(includes) - {p.name for p in skill_dirs})
        if missing:
            raise SystemExit(f"Unknown skill(s): {', '.join(missing)}")

    skill_plan_ops: list[dict[str, str]] = []
    for d in sorted(skill_dirs, key=lambda p: p.name):
        skill_plan_ops.extend(_iter_copy_plan(d, dst_skills / d.name))

    plans.append({"kind": "skills", "src": str(src_skills), "dst": str(dst_skills), "ops": skill_plan_ops})

    prompt_plan_ops: list[dict[str, str]] = []
    if args.include_prompts:
        prompt_plan_ops = _iter_copy_plan(src_prompts, dst_prompts)
        plans.append({"kind": "prompts", "src": str(src_prompts), "dst": str(dst_prompts), "ops": prompt_plan_ops})

    # Apply
    results: list[dict[str, object]] = []
    for plan in plans:
        ops = list(plan["ops"])  # type: ignore[assignment]
        res = _apply_copy_plan(ops, dry_run=bool(args.dry_run), force=bool(args.force))
        results.append(
            {
                "kind": plan["kind"],
                "src": plan["src"],
                "dst": plan["dst"],
                "dry_run": bool(args.dry_run),
                "force": bool(args.force),
                "planned": len(ops),
                "copied": len(res["copied"]),
                "skipped_existing": len(res["skipped_existing"]),
                "failures": res["failures"],
            }
        )

    _print_json(
        {
            "success": all(r["failures"] == [] for r in results),
            "from_root": str(from_root),
            "to_repo": str(target_repo),
            "include_prompts": bool(args.include_prompts),
            "include": includes,
            "results": results,
        }
    )


def _read_git_head_sha(repo_root: Path) -> str:
    """Best-effort git HEAD SHA without running git."""
    head = repo_root / ".git" / "HEAD"
    if not head.exists():
        return ""
    raw = head.read_text(encoding="utf-8").strip()
    if raw.startswith("ref:"):
        ref = raw.split(":", 1)[1].strip()
        ref_path = repo_root / ".git" / ref
        if ref_path.exists():
            return ref_path.read_text(encoding="utf-8").strip()
        packed = repo_root / ".git" / "packed-refs"
        if packed.exists():
            for line in packed.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("^"):
                    continue
                sha, name = (line.split(" ", 1) + [""])[:2]
                if name.strip() == ref:
                    return sha.strip()
        return ""
    # Detached head contains the SHA directly.
    if len(raw) >= 7 and all(c in "0123456789abcdef" for c in raw.lower().strip()[:7]):
        return raw
    return ""


def _payload_root_from_cli() -> Path | None:
    """Locate the automation repo root that contains the `.github` payload."""
    here = Path(__file__).resolve().parent
    return _find_ancestor_dir_with(here, Path(".github") / "skills")


def _repo_init_or_update(args: argparse.Namespace, *, mode: str) -> None:
    """
    Install/update the "core" workflow payload into a target repo.

    This is intentionally minimal: it installs only the bootstrap skill + prompts
    that let you run updates in-place.
    """
    payload_root = Path(args.from_root).expanduser().resolve() if args.from_root else _payload_root_from_cli()
    if payload_root is None:
        raise SystemExit("Cannot auto-detect payload root. Provide --from-root pointing at the automation repo root.")

    target_repo = Path(args.to).expanduser().resolve() if args.to else Path.cwd().resolve()
    stamp_path_existing = target_repo / ".github" / "automation" / "automation_payload.json"
    prev_managed: list[str] = []
    if stamp_path_existing.exists():
        try:
            prev_stamp = json.loads(stamp_path_existing.read_text(encoding="utf-8"))
            if isinstance(prev_stamp, dict) and isinstance(prev_stamp.get("managed_files"), list):
                prev_managed = [str(x) for x in prev_stamp["managed_files"] if isinstance(x, str)]
        except Exception:
            prev_managed = []

    bundles = [b.strip().lower() for b in (getattr(args, "bundle", []) or []) if b.strip()]
    # If update is invoked without explicit bundles, preserve whatever was previously installed.
    if mode == "update" and not bundles:
        if stamp_path_existing.exists():
            try:
                stamp = json.loads(stamp_path_existing.read_text(encoding="utf-8"))
                prev = stamp.get("bundles") if isinstance(stamp, dict) else None
                if isinstance(prev, list) and all(isinstance(x, str) for x in prev):
                    bundles = [x.strip().lower() for x in prev if x.strip()]
            except Exception:
                # If stamp is unreadable, fall back to core-only update.
                bundles = bundles
    bundle_set = set(bundles)

    # Always install the minimal "core" payload (bootstrap).
    core_skill = payload_root / ".github" / "skills" / "distributed-workflows" / "SKILL.md"
    seo_local_skill = payload_root / ".github" / "skills" / "seo-local-setup" / "SKILL.md"
    core_prompts = [
        payload_root / ".github" / "prompts" / "automation0-install.prompt.md",
        payload_root / ".github" / "prompts" / "automation0-update.prompt.md",
        payload_root / ".github" / "prompts" / "automation0-status.prompt.md",
        payload_root / ".github" / "prompts" / "seo0-local-setup.prompt.md",
        payload_root / ".github" / "prompts" / "seo0-local-status.prompt.md",
    ]

    ops: list[dict[str, str]] = []
    ops.append(
        {
            "src": str(core_skill),
            "dst": str(target_repo / ".github" / "skills" / "distributed-workflows" / "SKILL.md"),
        }
    )
    ops.append(
        {
            "src": str(seo_local_skill),
            "dst": str(target_repo / ".github" / "skills" / "seo-local-setup" / "SKILL.md"),
        }
    )
    for src_path in core_prompts:
        ops.append(
            {
                "src": str(src_path),
                "dst": str(target_repo / ".github" / "prompts" / src_path.name),
            }
        )

    # Optional bundles.
    if "seo" in bundle_set:
        # Prompts: all seo*.prompt.md except the repo-local helpers already in core.
        src_prompts_dir = payload_root / ".github" / "prompts"
        for p in sorted(src_prompts_dir.glob("seo*.prompt.md"), key=lambda x: x.name):
            if p.name in {"seo0-local-setup.prompt.md", "seo0-local-status.prompt.md"}:
                continue
            ops.append({"src": str(p), "dst": str(target_repo / ".github" / "prompts" / p.name)})

        # Skills: all seo-* (including seo-local-setup already covered by core; safe to include as overwrite-managed file).
        src_skills_dir = payload_root / ".github" / "skills"
        for d in sorted(src_skills_dir.glob("seo-*"), key=lambda x: x.name):
            if not d.is_dir():
                continue
            ops.extend(_iter_copy_plan(d, target_repo / ".github" / "skills" / d.name))

        # Prompt templates (useful for authoring, and some skills refer to them).
        templates_root = src_prompts_dir / "templates" / "seo"
        if templates_root.exists():
            ops.extend(_iter_copy_plan(templates_root, target_repo / ".github" / "prompts" / "templates" / "seo"))

    if "posthog" in bundle_set:
        src_prompts_dir = payload_root / ".github" / "prompts"
        for p in sorted(src_prompts_dir.glob("posthog*.prompt.md"), key=lambda x: x.name):
            ops.append({"src": str(p), "dst": str(target_repo / ".github" / "prompts" / p.name)})

        src_skill_dir = payload_root / ".github" / "skills" / "posthog-product-insights"
        if src_skill_dir.exists() and src_skill_dir.is_dir():
            ops.extend(_iter_copy_plan(src_skill_dir, target_repo / ".github" / "skills" / "posthog-product-insights"))
        
        # Also include single-site skill
        src_single_site_skill_dir = payload_root / ".github" / "skills" / "posthog-single-site"
        if src_single_site_skill_dir.exists() and src_single_site_skill_dir.is_dir():
            ops.extend(_iter_copy_plan(src_single_site_skill_dir, target_repo / ".github" / "skills" / "posthog-single-site"))

    # Validate required payload sources exist (best effort; keeps errors actionable).
    missing: list[str] = []
    for op in ops:
        if not Path(op["src"]).exists():
            missing.append(op["src"])
    if missing:
        raise SystemExit("Missing payload file(s):\n" + "\n".join(f"- {m}" for m in sorted(set(missing))))

    # Init is conservative (no overwrite). Update overwrites managed files by default.
    overwrite = bool(args.force) if mode == "init" else (not bool(args.no_overwrite))
    res = _apply_copy_plan(ops, dry_run=bool(args.dry_run), force=overwrite)

    # Stamp (even on dry-run we can preview stamp fields without writing).
    stamp_dir = target_repo / ".github" / "automation"
    stamp_path = stamp_dir / "automation_payload.json"
    stamp = {
        "schema": 1,
        "payload_root": str(payload_root),
        "payload_git_head": _read_git_head_sha(payload_root),
        "installed_by": "automation-cli repo " + mode,
        "bundles": bundles,
        "managed_files": [op["dst"] for op in ops],
    }

    pruned: list[str] = []
    if bool(getattr(args, "prune", False)) and not bool(args.dry_run):
        current = set(stamp["managed_files"])
        for p_str in sorted(set(prev_managed) - current):
            try:
                p = Path(p_str).expanduser().resolve()
                # Safety: only delete within the target repo.
                if target_repo not in p.parents and p != target_repo:
                    continue
                if not (p.exists() or p.is_symlink()):
                    continue
                if p.is_dir() and not p.is_symlink():
                    continue
                p.unlink()
                pruned.append(str(p))
                parent = p.parent
                while parent != target_repo and parent.exists():
                    try:
                        parent.rmdir()
                    except OSError:
                        break
                    parent = parent.parent
            except Exception:
                continue

    stamp_write_error = ""
    if not bool(args.dry_run):
        try:
            stamp_dir.mkdir(parents=True, exist_ok=True)
            stamp_path.write_text(json.dumps(stamp, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            stamp_write_error = str(exc)

    _print_json(
        {
            "success": bool(res["success"]) and stamp_write_error == "",
            "mode": mode,
            "dry_run": bool(args.dry_run),
            "overwrite": overwrite,
            "payload_root": str(payload_root),
            "payload_git_head": stamp["payload_git_head"],
            "target_repo": str(target_repo),
            "bundles": bundles,
            "planned": len(ops),
            "copied": len(res["copied"]),
            "skipped_existing": len(res["skipped_existing"]),
            "failures": res["failures"],
            "pruned": pruned,
            "stamp_path": str(stamp_path),
            "stamp_write_error": stamp_write_error,
        }
    )


def _repo_init(args: argparse.Namespace) -> None:
    _repo_init_or_update(args, mode="init")


def _repo_update(args: argparse.Namespace) -> None:
    _repo_init_or_update(args, mode="update")


def _repo_status(args: argparse.Namespace) -> None:
    target_repo = Path(args.to).expanduser().resolve() if args.to else Path.cwd().resolve()
    stamp_path = target_repo / ".github" / "automation" / "automation_payload.json"
    stamp: dict[str, object] = {}
    if stamp_path.exists():
        try:
            stamp = json.loads(stamp_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            stamp = {"error": f"Failed to read stamp: {exc}"}

    payload_root = Path(args.from_root).expanduser().resolve() if args.from_root else _payload_root_from_cli()
    payload_head = _read_git_head_sha(payload_root) if payload_root else ""

    installed_head = str(stamp.get("payload_git_head") or "") if isinstance(stamp, dict) else ""
    out_of_sync = bool(installed_head and payload_head and installed_head != payload_head)

    _print_json(
        {
            "success": True,
            "target_repo": str(target_repo),
            "stamp_path": str(stamp_path),
            "stamp_present": stamp_path.exists(),
            "stamp": stamp,
            "payload_root": str(payload_root) if payload_root else "",
            "payload_git_head": payload_head,
            "out_of_sync": out_of_sync,
            "recommended": ("automation-cli repo update" if out_of_sync else ""),
        }
    )


def _campaign_start(args: argparse.Namespace) -> None:
    repo_root = Path(args.repo_root).expanduser().resolve() if args.repo_root else Path.cwd().resolve()
    result = create_campaign_run(
        repo_root=repo_root,
        campaign_name=str(args.campaign_name),
        cadence=str(args.cadence),
        website_id=str(args.website_id or ""),
        sources=[str(s) for s in (args.source or [])],
        dry_run=bool(args.dry_run),
    )
    _print_json(result)


def _campaign_status(args: argparse.Namespace) -> None:
    repo_root = Path(args.repo_root).expanduser().resolve() if args.repo_root else Path.cwd().resolve()
    try:
        result = campaign_status(
            repo_root=repo_root,
            run_id=(str(args.run_id).strip() if args.run_id else None),
        )
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(str(exc)) from exc
    _print_json(result)


def _campaign_collect(args: argparse.Namespace) -> None:
    repo_root = Path(args.repo_root).expanduser().resolve() if args.repo_root else Path.cwd().resolve()
    run_id = str(args.run_id).strip() if args.run_id else None
    try:
        result = collect_campaign_data(
            repo_root=repo_root,
            run_id=run_id or "",
            sources=[str(s) for s in (args.source or [])] if args.source else None,
            dry_run=bool(args.dry_run),
        )
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(str(exc)) from exc
    _print_json(result)


def _campaign_plan(args: argparse.Namespace) -> None:
    repo_root = Path(args.repo_root).expanduser().resolve() if args.repo_root else Path.cwd().resolve()
    try:
        result = plan_campaign(
            repo_root=repo_root,
            run_id=str(args.run_id).strip() if args.run_id else "",
            auto_disposition=None,  # Could be extended to load from file
            dry_run=bool(args.dry_run),
        )
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(str(exc)) from exc
    _print_json(result)


def _campaign_execute(args: argparse.Namespace) -> None:
    repo_root = Path(args.repo_root).expanduser().resolve() if args.repo_root else Path.cwd().resolve()
    try:
        result = execute_campaign_batch(
            repo_root=repo_root,
            run_id=str(args.run_id).strip() if args.run_id else "",
            wip_limit=int(args.wip_limit),
            dry_run=bool(args.dry_run),
        )
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(str(exc)) from exc
    _print_json(result)


def _campaign_transition(args: argparse.Namespace) -> None:
    repo_root = Path(args.repo_root).expanduser().resolve() if args.repo_root else Path.cwd().resolve()
    try:
        result = transition_item(
            repo_root=repo_root,
            run_id=str(args.run_id).strip() if args.run_id else "",
            item_id=str(args.item_id),
            new_status=str(args.status),
            notes=str(args.notes or ""),
            assigned_to=str(args.assigned_to or ""),
        )
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(str(exc)) from exc
    _print_json(result)


def _campaign_carry_over(args: argparse.Namespace) -> None:
    repo_root = Path(args.repo_root).expanduser().resolve() if args.repo_root else Path.cwd().resolve()
    try:
        result = carry_over_items(
            repo_root=repo_root,
            from_run_id=str(args.from_run_id),
            to_run_id=str(args.to_run_id).strip() if args.to_run_id else None,
            dry_run=bool(args.dry_run),
        )
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(str(exc)) from exc
    _print_json(result)


def _campaign_archive(args: argparse.Namespace) -> None:
    repo_root = Path(args.repo_root).expanduser().resolve() if args.repo_root else Path.cwd().resolve()
    try:
        result = archive_campaign(
            repo_root=repo_root,
            run_id=str(args.run_id),
            dry_run=bool(args.dry_run),
        )
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(str(exc)) from exc
    _print_json(result)


def _campaign_prune(args: argparse.Namespace) -> None:
    repo_root = Path(args.repo_root).expanduser().resolve() if args.repo_root else Path.cwd().resolve()
    try:
        result = prune_campaigns(
            repo_root=repo_root,
            keep_count=int(args.keep_count),
            dry_run=bool(args.dry_run),
        )
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(str(exc)) from exc
    _print_json(result)


def _reddit_pending(args: argparse.Namespace) -> None:
    from .reddit.database import ensure_reddit_table, get_pending_opportunities

    ensure_reddit_table()
    opportunities = get_pending_opportunities(project_name=args.project, severity=args.severity or "")
    if args.limit is not None:
        opportunities = opportunities[: args.limit]

    _print_json(
        {
            "project_name": args.project,
            "severity": args.severity or "",
            "count": len(opportunities),
            "opportunities": opportunities,
        }
    )


def _reddit_posted(args: argparse.Namespace) -> None:
    from .reddit.database import ensure_reddit_table, get_posted_opportunities

    ensure_reddit_table()
    opportunities = get_posted_opportunities(project_name=args.project, days=args.days)
    if args.limit is not None:
        opportunities = opportunities[: args.limit]

    _print_json(
        {
            "project_name": args.project,
            "days": args.days,
            "count": len(opportunities),
            "opportunities": opportunities,
        }
    )


def _reddit_mark_posted(args: argparse.Namespace) -> None:
    from .reddit.database import ensure_reddit_table, mark_opportunity_posted

    ensure_reddit_table()
    reply_text = _read_text_arg(args.reply_text, args.reply_text_file)
    result = mark_opportunity_posted(post_id=args.post_id, reply_text=reply_text, reply_url=args.reply_url or "")
    _print_json(result)


def _reddit_mark_skipped(args: argparse.Namespace) -> None:
    from .reddit.database import ensure_reddit_table, mark_opportunity_skipped

    ensure_reddit_table()
    result = mark_opportunity_skipped(post_id=args.post_id, reason=args.reason or "")
    _print_json(result)


def _reddit_submit_comment(args: argparse.Namespace) -> None:
    """Submit a comment to a Reddit post."""
    from .reddit.api import RedditAPI
    
    api = RedditAPI()
    result = api.submit_comment(post_id=args.post_id, text=args.text)
    _print_json(result)


def _reddit_auth_status(args: argparse.Namespace) -> None:
    """Check whether Reddit posting auth is ready."""
    from .reddit.api import RedditAPI

    api = RedditAPI()
    _print_json(api.auth_status())


def _reddit_stats(args: argparse.Namespace) -> None:
    from .reddit.database import ensure_reddit_table, get_reddit_statistics

    ensure_reddit_table()
    _print_json(get_reddit_statistics(project_name=args.project))


def _reddit_update_performance(args: argparse.Namespace) -> None:
    from .reddit.database import ensure_reddit_table, update_opportunity_performance

    ensure_reddit_table()
    _print_json(
        update_opportunity_performance(
            post_id=args.post_id,
            reply_upvotes=args.reply_upvotes,
            reply_replies=args.reply_replies,
        )
    )


def _reddit_search_submissions(args: argparse.Namespace) -> None:
    from .reddit.search import search_submissions

    try:
        posts = search_submissions(
            query=args.query,
            subreddit=args.subreddit or "",
            limit=args.limit,
            sort=args.sort,
            time=args.time,
        )
    except Exception as exc:  # noqa: BLE001
        _print_json({"success": False, "error": str(exc)})
        raise SystemExit(2) from exc

    _print_json(
        {
            "success": True,
            "query": args.query,
            "subreddit": args.subreddit or "",
            "limit": args.limit,
            "sort": args.sort,
            "time": args.time,
            "count": len(posts),
            "posts": posts,
        }
    )


def _reddit_insert_opportunity(args: argparse.Namespace) -> None:
    from .reddit.database import ensure_reddit_table, insert_reddit_opportunity

    ensure_reddit_table()

    payload = _read_json_arg(args.json, args.json_file)
    if not isinstance(payload, dict):
        raise SystemExit("insert-opportunity expects a JSON object")

    if not payload.get("project_name"):
        raise SystemExit("Missing required field: project_name")
    if not payload.get("post_id"):
        raise SystemExit("Missing required field: post_id")

    result = insert_reddit_opportunity(**payload)
    _print_json(result)


def _geo_maps_lookup(args: argparse.Namespace) -> None:
    from .geo.google_maps import GoogleMapsClient

    with GoogleMapsClient(
        headless=bool(args.headless),
        slow_mo_ms=int(args.slow_mo_ms),
        timeout_ms=int(args.timeout_ms),
        cdp_url=(args.cdp_url.strip() or None),
    ) as client:
        _print_json(client.lookup(args.query))


def _geo_maps_enrich_csv(args: argparse.Namespace) -> None:
    from .geo.google_maps import enrich_csv_with_google_maps

    _print_json(
        enrich_csv_with_google_maps(
            input_path=args.input,
            output_path=args.output,
            name_column=args.name_column,
            city_column=args.city_column,
            country_hint=args.country_hint,
            max_rows=(None if args.max_rows == 0 else int(args.max_rows)),
            sleep_seconds=float(args.sleep_seconds),
            headless=bool(args.headless),
            slow_mo_ms=int(args.slow_mo_ms),
            timeout_ms=int(args.timeout_ms),
            cdp_url=(args.cdp_url.strip() or None),
        )
    )


def _reddit_import_opportunities(args: argparse.Namespace) -> None:
    from .reddit.database import ensure_reddit_table, insert_reddit_opportunity

    ensure_reddit_table()

    payload = _read_json_arg(args.json, args.json_file)

    items: list[dict]
    if isinstance(payload, dict) and "opportunities" in payload and isinstance(payload["opportunities"], list):
        items = payload["opportunities"]
    elif isinstance(payload, list):
        items = payload
    else:
        raise SystemExit("import-opportunities expects a JSON list or {opportunities: [...]} object")

    results: list[object] = []
    failures: list[object] = []

    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            failures.append({"index": idx, "error": "Item is not an object"})
            continue
        if not item.get("project_name") or not item.get("post_id"):
            failures.append({"index": idx, "error": "Missing project_name or post_id"})
            continue
        try:
            results.append(insert_reddit_opportunity(**item))
        except Exception as exc:  # noqa: BLE001
            failures.append({"index": idx, "post_id": item.get("post_id"), "error": str(exc)})

    _print_json(
        {
            "success": len(failures) == 0,
            "inserted_or_updated": len(results),
            "failed": len(failures),
            "results": results,
            "failures": failures,
        }
    )


def _version_cmd(args: argparse.Namespace) -> None:
    """Check version and print update status."""
    if args.all:
        version_check.print_all_versions()
    else:
        version_check.print_version_check("automation-cli", "automation-mcp")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="automation-cli", description="Run automation workflows without MCP")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # Version command
    version_parser = subparsers.add_parser("version", help="Check CLI version and available updates")
    version_parser.add_argument("--all", action="store_true", help="Check all CLI packages for updates")
    version_parser.set_defaults(func=_version_cmd)

    repo = subparsers.add_parser("repo", help="Install/update workflow payload into a repo (skills/prompts)")
    repo_sub = repo.add_subparsers(dest="repo_command", required=True)

    repo_init = repo_sub.add_parser("init", help="Install core workflow payload into the current repo")
    repo_init.add_argument("--to", default="", help="Target repo root (default: current working directory)")
    repo_init.add_argument("--from-root", default=None, help="Payload source repo root (auto-detected if omitted)")
    repo_init.add_argument(
        "--bundle",
        action="append",
        default=[],
        help="Optional bundle(s) to install (repeatable). Currently supported: seo, posthog",
    )
    repo_init.add_argument("--dry-run", action="store_true", help="Preview changes; do not write files")
    repo_init.add_argument("--force", action="store_true", help="Overwrite existing managed files")
    repo_init.set_defaults(func=_repo_init)

    repo_update = repo_sub.add_parser("update", help="Update core workflow payload in the current repo")
    repo_update.add_argument("--to", default="", help="Target repo root (default: current working directory)")
    repo_update.add_argument("--from-root", default=None, help="Payload source repo root (auto-detected if omitted)")
    repo_update.add_argument(
        "--bundle",
        action="append",
        default=[],
        help="Optional bundle(s) to install (repeatable). Currently supported: seo, posthog",
    )
    repo_update.add_argument(
        "--prune",
        action="store_true",
        help="Delete previously-managed files that are no longer part of the current payload/bundles",
    )
    repo_update.add_argument("--dry-run", action="store_true", help="Preview changes; do not write files")
    repo_update.add_argument(
        "--no-overwrite",
        action="store_true",
        help="Do not overwrite existing files (useful to see what would be updated first)",
    )
    repo_update.add_argument(
        "--force",
        action="store_true",
        help="Force overwrite (equivalent to default update behavior unless --no-overwrite is set)",
    )
    repo_update.set_defaults(func=_repo_update)

    repo_status = repo_sub.add_parser("status", help="Show whether the repo payload is out of sync with the source")
    repo_status.add_argument("--to", default="", help="Target repo root (default: current working directory)")
    repo_status.add_argument("--from-root", default=None, help="Payload source repo root (auto-detected if omitted)")
    repo_status.set_defaults(func=_repo_status)

    campaign = subparsers.add_parser("campaign", help="Campaign run lifecycle (start/collect/plan/execute/status)")
    campaign_sub = campaign.add_subparsers(dest="campaign_command", required=True)

    campaign_start = campaign_sub.add_parser("start", help="Create a new weekly/biweekly campaign run")
    campaign_start.add_argument("--repo-root", default="", help="Repo root (default: cwd)")
    campaign_start.add_argument("--campaign-name", default="default", help="Campaign name (e.g. call-analyzer)")
    campaign_start.add_argument(
        "--cadence",
        default="biweekly",
        choices=["weekly", "biweekly"],
        help="Campaign cadence (default: biweekly)",
    )
    campaign_start.add_argument("--website-id", default="", help="Optional website identifier for this run")
    campaign_start.add_argument(
        "--source",
        action="append",
        default=[],
        choices=["gsc", "posthog", "keywords"],
        help="Data source to include (repeatable). Defaults to all.",
    )
    campaign_start.add_argument("--dry-run", action="store_true", help="Preview run creation without writing files")
    campaign_start.set_defaults(func=_campaign_start)

    campaign_collect = campaign_sub.add_parser("collect", help="Run deterministic collection for all configured sources")
    campaign_collect.add_argument("--repo-root", default="", help="Repo root (default: cwd)")
    campaign_collect.add_argument("--run-id", default="", help="Run id (default: use latest)")
    campaign_collect.add_argument(
        "--source",
        action="append",
        default=[],
        choices=["gsc", "posthog", "keywords"],
        help="Override data sources to collect (repeatable)",
    )
    campaign_collect.add_argument("--dry-run", action="store_true", help="Preview collection without running")
    campaign_collect.set_defaults(func=_campaign_collect)

    campaign_plan = campaign_sub.add_parser("plan", help="Merge collection findings into fix_plan.json with dispositions")
    campaign_plan.add_argument("--repo-root", default="", help="Repo root (default: cwd)")
    campaign_plan.add_argument("--run-id", default="", help="Run id (default: use latest)")
    campaign_plan.add_argument("--dry-run", action="store_true", help="Preview plan without writing")
    campaign_plan.set_defaults(func=_campaign_plan)

    campaign_execute = campaign_sub.add_parser("execute", help="Process next batch respecting WIP limit and priority")
    campaign_execute.add_argument("--repo-root", default="", help="Repo root (default: cwd)")
    campaign_execute.add_argument("--run-id", default="", help="Run id (default: use latest)")
    campaign_execute.add_argument("--wip-limit", type=int, default=5, help="Work-in-progress limit (default: 5)")
    campaign_execute.add_argument("--dry-run", action="store_true", help="Preview execution without starting items")
    campaign_execute.set_defaults(func=_campaign_execute)

    campaign_transition = campaign_sub.add_parser("transition", help="Transition an item to a new status")
    campaign_transition.add_argument("--repo-root", default="", help="Repo root (default: cwd)")
    campaign_transition.add_argument("--run-id", default="", help="Run id (default: use latest)")
    campaign_transition.add_argument("--item-id", required=True, help="Item ID to transition")
    campaign_transition.add_argument(
        "--status",
        required=True,
        choices=["todo", "in_progress", "qa", "done", "blocked"],
        help="New status",
    )
    campaign_transition.add_argument("--notes", default="", help="Optional notes for the transition")
    campaign_transition.add_argument("--assigned-to", default="", help="Optional assignee")
    campaign_transition.set_defaults(func=_campaign_transition)

    campaign_carry_over = campaign_sub.add_parser("carry-over", help="Carry over unfinished items to a new campaign run")
    campaign_carry_over.add_argument("--repo-root", default="", help="Repo root (default: cwd)")
    campaign_carry_over.add_argument("--from-run-id", required=True, help="Source campaign run id")
    campaign_carry_over.add_argument("--to-run-id", default="", help="Target campaign run id (default: create new)")
    campaign_carry_over.add_argument("--dry-run", action="store_true", help="Preview carry-over without creating")
    campaign_carry_over.set_defaults(func=_campaign_carry_over)

    campaign_archive = campaign_sub.add_parser("archive", help="Archive a completed campaign run")
    campaign_archive.add_argument("--repo-root", default="", help="Repo root (default: cwd)")
    campaign_archive.add_argument("--run-id", required=True, help="Campaign run id to archive")
    campaign_archive.add_argument("--dry-run", action="store_true", help="Preview archive without moving")
    campaign_archive.set_defaults(func=_campaign_archive)

    campaign_prune = campaign_sub.add_parser("prune", help="Prune old campaign runs, keeping only the most recent")
    campaign_prune.add_argument("--repo-root", default="", help="Repo root (default: cwd)")
    campaign_prune.add_argument("--keep-count", type=int, default=10, help="Number of recent runs to keep (default: 10)")
    campaign_prune.add_argument("--dry-run", action="store_true", help="Preview prune without deleting")
    campaign_prune.set_defaults(func=_campaign_prune)

    campaign_status_cmd = campaign_sub.add_parser("status", help="Show campaign run status and coverage gates")
    campaign_status_cmd.add_argument("--repo-root", default="", help="Repo root (default: cwd)")
    campaign_status_cmd.add_argument("--run-id", default="", help="Optional run id (default: latest run)")
    campaign_status_cmd.set_defaults(func=_campaign_status)

    seo = subparsers.add_parser("seo", help="Repo-local SEO workspace helpers (no registry file required)")
    seo_sub = seo.add_subparsers(dest="seo_command", required=True)

    seo_init = seo_sub.add_parser("init", help="Initialize/update repo-local SEO workspace under automation/")
    seo_init.add_argument("--site-id", default="", help="Optional site identifier (for display/logging only)")
    seo_init.add_argument("--website-id", default="", help="Deprecated alias for --site-id")
    seo_init.add_argument("--repo-root", default="", help="Repo root (default: cwd)")
    seo_init.add_argument("--workspace-dir", default="automation", help="Workspace dir under repo root (default: automation)")
    seo_init.add_argument("--source-repo", default="", help="Absolute path to the content repo root (default: repo-root)")
    seo_init.add_argument("--content-dir", default="", help="Canonical content dir (relative to source repo or absolute)")
    seo_init.add_argument("--source-content-dir", default="", help="Deprecated alias for --content-dir")
    seo_init.add_argument("--articles-json", default="", help="Optional seed file for workspace articles.json (copied)")
    seo_init.add_argument(
        "--link-mode",
        default="symlink",
        choices=["symlink", "copy"],
        help="How to materialize articles/content into the workspace (default: symlink)",
    )
    seo_init.add_argument("--dry-run", action="store_true", help="Preview changes; do not write files")
    seo_init.add_argument("--force", action="store_true", help="Overwrite/replace existing symlinks/files")
    seo_init.add_argument(
        "--reset-articles",
        action="store_true",
        help="Reset the workspace articles.json to an empty template (DANGEROUS).",
    )
    seo_init.set_defaults(func=_seo_init)

    seo_status = seo_sub.add_parser("status", help="Show repo-local SEO workspace status")
    seo_status.add_argument("--website-id", default="", help="Deprecated (ignored)")
    seo_status.add_argument("--repo-root", default="", help="Repo root (default: cwd)")
    seo_status.add_argument("--workspace-dir", default="automation", help="Workspace dir under repo root (default: automation)")
    seo_status.set_defaults(func=_seo_status)

    seo_gsc = seo_sub.add_parser("gsc-indexing-report", help="Run GSC URL Inspection indexing diagnostics (centralized tool)")
    seo_gsc.add_argument("--repo-root", default="", help="Repo root (default: cwd)")
    seo_gsc.add_argument("--workspace-dir", default="automation", help="Workspace dir under repo root (default: automation)")
    seo_gsc.add_argument("--out-dir", default="", help="Override output directory (default: .github/automation/output/gsc_indexing)")
    seo_gsc.add_argument("--manifest", default="", help="Optional manifest.json path (relative to repo root or absolute)")
    seo_gsc.add_argument("--site", default="", help="Search Console property, e.g. sc-domain:example.com")
    seo_gsc.add_argument("--sitemap-url", default="", help="Sitemap URL to inspect (recommended)")
    seo_gsc.add_argument("--urls-file", default="", help="Optional newline-delimited URLs file to inspect")
    seo_gsc.add_argument("--limit", type=int, default=500)
    seo_gsc.add_argument("--workers", type=int, default=2)
    seo_gsc.add_argument("--language", default="en-US")
    seo_gsc.add_argument("--service-account-path", default="")
    seo_gsc.add_argument("--delegated-user", default="")
    seo_gsc.add_argument("--oauth-client-secrets", default="")
    seo_gsc.add_argument("--list-sites", action="store_true")
    seo_gsc.add_argument("--include-raw", action="store_true")
    seo_gsc.add_argument("--samples-per-bucket", type=int, default=10)
    seo_gsc.set_defaults(func=_seo_gsc_indexing_report)

    seo_page_context = seo_sub.add_parser(
        "gsc-page-context",
        help="Pull deterministic context for one URL (trend + inspection + site context).",
    )
    seo_page_context.add_argument("--repo-root", default="", help="Repo root (default: cwd)")
    seo_page_context.add_argument("--workspace-dir", default="automation", help="Workspace dir under repo root (default: automation)")
    seo_page_context.add_argument("--out-dir", default="", help="Override output directory (default: .github/automation/output/gsc_page_context)")
    seo_page_context.add_argument("--manifest", default="", help="Optional manifest.json path (relative to repo root or absolute)")
    seo_page_context.add_argument("--site", default="", help="Search Console property, e.g. sc-domain:example.com")
    seo_page_context.add_argument("--url", required=True, help="Page URL to inspect")
    seo_page_context.add_argument("--compare-days", type=int, default=7, help="Short window size")
    seo_page_context.add_argument("--long-compare-days", type=int, default=28, help="Long window size")
    seo_page_context.add_argument("--queries-limit", type=int, default=15, help="Movers included in output")
    seo_page_context.add_argument(
        "--queries-fetch-limit",
        type=int,
        default=100,
        help="Rows fetched per query period before mover calculation",
    )
    seo_page_context.add_argument("--language", default="en-US")
    seo_page_context.add_argument("--service-account-path", default="")
    seo_page_context.add_argument("--delegated-user", default="")
    seo_page_context.add_argument("--oauth-client-secrets", default="")
    seo_page_context.add_argument(
        "--action-queue",
        default="",
        help="Optional *_action_queue.json path (defaults to latest Step 6 queue)",
    )
    seo_page_context.set_defaults(func=_seo_gsc_page_context)

    seo_site_scan = seo_sub.add_parser(
        "gsc-site-scan",
        help="Run mixed-candidate page scan (top pages + decliners + non-PASS overrides).",
    )
    seo_site_scan.add_argument("--repo-root", default="", help="Repo root (default: cwd)")
    seo_site_scan.add_argument("--workspace-dir", default="automation", help="Workspace dir under repo root (default: automation)")
    seo_site_scan.add_argument("--out-dir", default="", help="Override output directory (default: .github/automation/output/gsc_site_scan)")
    seo_site_scan.add_argument("--manifest", default="", help="Optional manifest.json path (relative to repo root or absolute)")
    seo_site_scan.add_argument("--site", default="", help="Search Console property, e.g. sc-domain:example.com")
    seo_site_scan.add_argument("--compare-days", type=int, default=7, help="Short window size")
    seo_site_scan.add_argument("--long-compare-days", type=int, default=28, help="Long window size")
    seo_site_scan.add_argument("--top-pages", type=int, default=5, help="Top pages by short-window impressions")
    seo_site_scan.add_argument("--decliners", type=int, default=5, help="Biggest short-window impression decliners")
    seo_site_scan.add_argument("--max-pages", type=int, default=20, help="Maximum pages in final selection")
    seo_site_scan.add_argument("--fetch-pages-limit", type=int, default=200, help="Search Analytics page row limit")
    seo_site_scan.add_argument("--non-pass-pool", type=int, default=20, help="Inspect top N pages for non-PASS override")
    seo_site_scan.add_argument("--queries-limit", type=int, default=10, help="Movers returned per page")
    seo_site_scan.add_argument("--queries-fetch-limit", type=int, default=100, help="Query row limit used for mover calculation")
    seo_site_scan.add_argument("--language", default="en-US")
    seo_site_scan.add_argument("--service-account-path", default="")
    seo_site_scan.add_argument("--delegated-user", default="")
    seo_site_scan.add_argument("--oauth-client-secrets", default="")
    seo_site_scan.add_argument("--action-queue", default="", help="Optional *_action_queue.json path")
    seo_site_scan.set_defaults(func=_seo_gsc_site_scan)

    seo_watch = seo_sub.add_parser(
        "gsc-watch",
        help="Build ongoing GSC watch feed (alerts, opportunities, drift).",
    )
    seo_watch.add_argument("--repo-root", default="", help="Repo root (default: cwd)")
    seo_watch.add_argument("--workspace-dir", default="automation", help="Workspace dir under repo root (default: automation)")
    seo_watch.add_argument("--out-dir", default="", help="Override output directory (default: .github/automation/output/gsc_watch)")
    seo_watch.add_argument("--manifest", default="", help="Optional manifest.json path (relative to repo root or absolute)")
    seo_watch.add_argument("--site", default="", help="Search Console property, e.g. sc-domain:example.com")
    seo_watch.add_argument("--compare-days", type=int, default=7, help="Short window size")
    seo_watch.add_argument("--long-compare-days", type=int, default=28, help="Long window size")
    seo_watch.add_argument("--fetch-pages-limit", type=int, default=250, help="Search Analytics page row limit")
    seo_watch.add_argument("--alerts-limit", type=int, default=30, help="Max page alerts in output")
    seo_watch.add_argument("--opps-limit", type=int, default=30, help="Max opportunities in output")
    seo_watch.add_argument("--inspect-top-drops", type=int, default=8, help="Run URL inspection on top dropping pages")
    seo_watch.add_argument("--drift-limit", type=int, default=12, help="Rows per dimension drift table")
    seo_watch.add_argument("--language", default="en-US")
    seo_watch.add_argument("--service-account-path", default="")
    seo_watch.add_argument("--delegated-user", default="")
    seo_watch.add_argument("--oauth-client-secrets", default="")
    seo_watch.add_argument(
        "--action-queue",
        default="",
        help="Optional *_action_queue.json path from Step 6",
    )
    seo_watch.set_defaults(func=_seo_gsc_watch)

    seo_gsc_queue = seo_sub.add_parser(
        "gsc-action-queue",
        help="Select remediation targets from Step 6 action queue (no jq).",
    )
    seo_gsc_queue.add_argument("--repo-root", default="", help="Repo root (default: cwd)")
    seo_gsc_queue.add_argument("--workspace-dir", default="automation", help="Workspace dir under repo root (default: automation)")
    seo_gsc_queue.add_argument(
        "--action-queue",
        default="",
        help="Path to *_action_queue.json (default: latest in .github/automation/output/gsc_indexing)",
    )
    seo_gsc_queue.add_argument(
        "--reason-code",
        action="append",
        default=[],
        help="Filter by reason_code (repeatable). Example: --reason-code fetch_error",
    )
    seo_gsc_queue.add_argument(
        "--coverage-contains",
        action="append",
        default=[],
        help="Keep rows where coverageState contains this text (case-insensitive; repeatable).",
    )
    seo_gsc_queue.add_argument("--verdict", default="", help="Filter verdict (case-insensitive exact match).")
    seo_gsc_queue.add_argument("--mapped-only", action="store_true", help="Only include mapped_to_article=true items.")
    seo_gsc_queue.add_argument("--unmapped-only", action="store_true", help="Only include mapped_to_article=false items.")
    seo_gsc_queue.add_argument("--include-indexed-pass", action="store_true", help="Include indexed_pass rows.")
    seo_gsc_queue.add_argument("--limit", type=int, default=100, help="Max rows to emit (0 means no limit).")
    seo_gsc_queue.add_argument(
        "--format",
        choices=["json", "lines"],
        default="json",
        help="Output format. Use lines for deterministic shell-friendly output.",
    )
    seo_gsc_queue.add_argument(
        "--field",
        choices=["url", "path", "reason_code", "basename", "file", "title", "url_slug", "id"],
        default="basename",
        help="Field to print when --format lines is used.",
    )
    seo_gsc_queue.add_argument("--unique", action="store_true", help="Deduplicate output values in --format lines mode.")
    seo_gsc_queue.set_defaults(func=_seo_gsc_action_queue)

    seo_gsc_inputs = seo_sub.add_parser(
        "gsc-remediation-inputs",
        help="Get Step 7 starter inputs (coverageState contains 'not indexed').",
    )
    seo_gsc_inputs.add_argument("--repo-root", default="", help="Repo root (default: cwd)")
    seo_gsc_inputs.add_argument("--workspace-dir", default="automation", help="Workspace dir under repo root (default: automation)")
    seo_gsc_inputs.add_argument(
        "--action-queue",
        default="",
        help="Path to *_action_queue.json (default: latest in .github/automation/output/gsc_indexing)",
    )
    seo_gsc_inputs.add_argument("--mapped-only", action="store_true", help="Only include mapped_to_article=true items.")
    seo_gsc_inputs.add_argument("--limit", type=int, default=20, help="Max rows to emit (0 means no limit).")
    seo_gsc_inputs.add_argument(
        "--format",
        choices=["json", "lines"],
        default="lines",
        help="Output format. Default lines for direct use in prompts.",
    )
    seo_gsc_inputs.add_argument(
        "--field",
        choices=["url", "path", "reason_code", "basename", "file", "title", "url_slug", "id", "url_to_file"],
        default="url",
        help="Field to print when --format lines is used.",
    )
    seo_gsc_inputs.add_argument("--unique", action="store_true", help="Deduplicate output values in --format lines mode.")
    seo_gsc_inputs.set_defaults(func=_seo_gsc_remediation_inputs)

    seo_gsc_targets = seo_sub.add_parser(
        "gsc-remediation-targets",
        help="Get Step 7 edit-ready mapped targets (fast path).",
    )
    seo_gsc_targets.add_argument("--repo-root", default="", help="Repo root (default: cwd)")
    seo_gsc_targets.add_argument("--workspace-dir", default="automation", help="Workspace dir under repo root (default: automation)")
    seo_gsc_targets.add_argument(
        "--action-queue",
        default="",
        help="Path to *_action_queue.json (default: latest in .github/automation/output/gsc_indexing)",
    )
    seo_gsc_targets.add_argument("--limit", type=int, default=12, help="Max rows to emit (0 means no limit).")
    seo_gsc_targets.add_argument(
        "--format",
        choices=["json", "lines"],
        default="lines",
        help="Output format. Default lines for direct use in prompts.",
    )
    seo_gsc_targets.add_argument(
        "--field",
        choices=["url", "file", "basename", "reason_code", "coverageState", "title", "url_to_file"],
        default="basename",
        help="Field to print when --format lines is used.",
    )
    seo_gsc_targets.add_argument("--unique", action="store_true", help="Deduplicate output values in --format lines mode.")
    seo_gsc_targets.set_defaults(func=_seo_gsc_remediation_targets)

    posthog = subparsers.add_parser("posthog", help="PostHog analytics pull + action queue helpers")
    posthog_sub = posthog.add_subparsers(dest="posthog_command", required=True)

    posthog_report = posthog_sub.add_parser("report", help="Run PostHog multi-site pull and summary")
    posthog_report.add_argument("--repo-root", default="", help="Repo root (default: cwd)")
    posthog_report.add_argument("--registry", default="", help="Optional: Path to registry (legacy; if not provided, scans manifests-dir)")
    posthog_report.add_argument("--manifests-dir", default="", help="Directory to scan for manifest.json files (default: general/)")
    posthog_report.add_argument("--project-id", type=int, default=None, help="One-off mode: PostHog project ID")
    posthog_report.add_argument("--api-key-env", default="", help="One-off mode: env var name holding PostHog API key")
    posthog_report.add_argument("--base-url", default="", help="One-off mode: PostHog base URL (default: https://app.posthog.com)")
    posthog_report.add_argument("--dashboard-name", action="append", default=[], help="One-off mode: dashboard name substring (repeatable)")
    posthog_report.add_argument("--insight-id", action="append", default=[], type=int, help="One-off mode: explicit insight ID (repeatable)")
    posthog_report.add_argument("--site", action="append", default=[], help="Limit to site id (repeatable)")
    posthog_report.add_argument("--out-dir", default="", help="Override output directory (default: <repo-root>/.github/automation/output/posthog)")
    posthog_report.add_argument("--refresh", action="store_true", help="Pass refresh=true to insight endpoints")
    posthog_report.add_argument("--list-dashboards", action="store_true", help="List dashboards per site and exit")
    posthog_report.add_argument("--timeout", type=int, default=30, help="HTTP timeout seconds")
    posthog_report.add_argument("--max-insights", type=int, default=30, help="Max insights per site when resolving from dashboards")
    posthog_report.add_argument("--extra-insights", type=int, default=0, help="Also fetch N extra recent insights per site")
    posthog_report.add_argument("--env-file", action="append", default=[], help="Extra env file(s) to load (repeatable)")
    posthog_report.set_defaults(func=_posthog_report)

    posthog_projects = posthog_sub.add_parser("list-projects", help="List PostHog projects for an API key")
    posthog_projects.add_argument("--repo-root", default="", help="Repo root (default: cwd)")
    posthog_projects.add_argument("--api-key-env", required=True, help="Environment variable name holding the PostHog API key")
    posthog_projects.add_argument("--base-url", default="", help="PostHog base URL (default: https://app.posthog.com)")
    posthog_projects.add_argument("--out-dir", default="", help="Override output directory (default: <repo-root>/.github/automation/output/posthog)")
    posthog_projects.add_argument("--env-file", action="append", default=[], help="Extra env file(s) to load (repeatable)")
    posthog_projects.set_defaults(func=_posthog_list_projects)

    posthog_dashboards = posthog_sub.add_parser("list-dashboards", help="List dashboards for a PostHog project")
    posthog_dashboards.add_argument("--repo-root", default="", help="Repo root (default: cwd)")
    posthog_dashboards.add_argument("--project-id", required=True, type=int, help="PostHog project ID")
    posthog_dashboards.add_argument("--api-key-env", required=True, help="Environment variable name holding the PostHog API key")
    posthog_dashboards.add_argument("--base-url", default="", help="PostHog base URL (default: https://app.posthog.com)")
    posthog_dashboards.add_argument("--out-dir", default="", help="Override output directory (default: <repo-root>/.github/automation/output/posthog)")
    posthog_dashboards.add_argument("--env-file", action="append", default=[], help="Extra env file(s) to load (repeatable)")
    posthog_dashboards.set_defaults(func=_posthog_list_dashboards)

    posthog_queue = posthog_sub.add_parser("action-queue", help="Build cross-site PostHog action queue")
    posthog_queue.add_argument("--repo-root", default="", help="Repo root (default: cwd)")
    posthog_queue.add_argument("--out-dir", default="", help="Override output directory (default: <repo-root>/.github/automation/output/posthog)")
    posthog_queue.add_argument("--date", default="", help="Run date (YYYY-MM-DD). Default: today")
    posthog_queue.add_argument("--max-actions", type=int, default=15, help="Max cross-site actions")
    posthog_queue.add_argument("--max-per-site", type=int, default=5, help="Max actions per site before global ranking")
    posthog_queue.add_argument("--write-md", action="store_true", help="Also write markdown action queue")
    posthog_queue.set_defaults(func=_posthog_action_queue)

    posthog_view = posthog_sub.add_parser("view", help="View extracted fields from latest PostHog insights (no custom code needed)")
    posthog_view.add_argument("--repo-root", default="", help="Repo root (default: cwd)")
    posthog_view.add_argument("--out-dir", default="", help="Override output directory (default: <repo-root>/.github/automation/output/posthog)")
    posthog_view.add_argument(
        "--field",
        choices=["situations", "action_candidates", "insights", "page_traffic", "breakdowns"],
        required=True,
        help="Field to extract and display from the latest insights JSON",
    )
    posthog_view.add_argument(
        "--format",
        choices=["json", "lines"],
        default="lines",
        help="Output format: json for structured data, lines for human-readable",
    )
    posthog_view.set_defaults(func=_posthog_view)

    skills = subparsers.add_parser("skills", help="Sync workflow skills/prompts into another repo")
    skills_sub = skills.add_subparsers(dest="skills_command", required=True)

    sync = skills_sub.add_parser("sync", help="Copy .github/skills (and optionally .github/prompts) to a target repo")
    sync.add_argument(
        "--to",
        required=True,
        help="Target repo root (or path to its .github/skills directory)",
    )
    sync.add_argument(
        "--from-root",
        default=None,
        help=(
            "Source automation repo root. If omitted, automation-cli attempts to auto-detect when run from an editable "
            "install of this repo."
        ),
    )
    sync.add_argument(
        "--include",
        action="append",
        default=[],
        help="Skill directory name to include (repeatable). If omitted, sync all skills.",
    )
    sync.add_argument(
        "--include-prompts",
        action="store_true",
        help="Also copy .github/prompts into the target repo (off by default).",
    )
    sync.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would change; do not write files.",
    )
    sync.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files in the target repo.",
    )
    sync.set_defaults(func=_skills_sync)

    reddit = subparsers.add_parser("reddit", help="Reddit operations (search + DB)")
    reddit_sub = reddit.add_subparsers(dest="reddit_command", required=True)

    search = reddit_sub.add_parser("search-submissions", help="Search Reddit submissions")
    search.add_argument("--query", required=True, help="Search query")
    search.add_argument("--subreddit", default="", help="Subreddit name (optional; empty searches all)")
    search.add_argument("--limit", type=int, default=10, help="Number of results to return")
    search.add_argument(
        "--sort",
        default="relevance",
        choices=["relevance", "hot", "top", "new", "comments"],
        help="Sort order",
    )
    search.add_argument(
        "--time",
        default="all",
        choices=["all", "hour", "day", "week", "month", "year"],
        help="Time filter",
    )
    search.set_defaults(func=_reddit_search_submissions)

    pending = reddit_sub.add_parser("pending", help="List pending opportunities")
    pending.add_argument("--project", required=True, help="Project slug (e.g. expense, coffee)")
    pending.add_argument("--severity", default="", help="Optional severity filter (CRITICAL/HIGH/MEDIUM/LOW)")
    pending.add_argument("--limit", type=int, default=None, help="Optional max number of results")
    pending.set_defaults(func=_reddit_pending)

    posted = reddit_sub.add_parser("posted", help="List posted opportunities")
    posted.add_argument("--project", required=True, help="Project slug (e.g. expense, coffee)")
    posted.add_argument("--days", type=int, default=30, help="Lookback window in days")
    posted.add_argument("--limit", type=int, default=None, help="Optional max number of results")
    posted.set_defaults(func=_reddit_posted)

    mark_posted = reddit_sub.add_parser("mark-posted", help="Mark a post as replied/posted")
    mark_posted.add_argument("--post-id", required=True, help="Reddit post ID")
    mark_posted.add_argument("--reply-url", default="", help="URL to your Reddit comment")
    mark_posted.add_argument("--reply-text", default=None, help="Reply text (3–5 sentences).")
    mark_posted.add_argument(
        "--reply-text-file",
        default=None,
        help="Path to file containing reply text (use '-' to read from stdin)",
    )
    mark_posted.set_defaults(func=_reddit_mark_posted)

    mark_skipped = reddit_sub.add_parser("mark-skipped", help="Mark a post as skipped")
    mark_skipped.add_argument("--post-id", required=True, help="Reddit post ID")
    mark_skipped.add_argument("--reason", default="", help="Optional skip reason")
    mark_skipped.set_defaults(func=_reddit_mark_skipped)

    submit = reddit_sub.add_parser("submit-comment", help="Submit a comment to a Reddit post")
    submit.add_argument("--post-id", required=True, help="Reddit post ID (e.g., '1abc123')")
    submit.add_argument("--text", required=True, help="Comment text")
    submit.set_defaults(func=_reddit_submit_comment)

    auth_status = reddit_sub.add_parser("auth-status", help="Check Reddit posting authentication")
    auth_status.set_defaults(func=_reddit_auth_status)

    stats = reddit_sub.add_parser("stats", help="Show project stats")
    stats.add_argument("--project", required=True, help="Project slug (e.g. expense, coffee)")
    stats.set_defaults(func=_reddit_stats)

    perf = reddit_sub.add_parser("update-performance", help="Update reply performance metrics")
    perf.add_argument("--post-id", required=True, help="Reddit post ID")
    perf.add_argument("--reply-upvotes", type=int, required=True, help="Current upvotes on your reply")
    perf.add_argument("--reply-replies", type=int, required=True, help="Number of comment replies to your reply")
    perf.set_defaults(func=_reddit_update_performance)

    insert = reddit_sub.add_parser("insert-opportunity", help="Insert/update a single opportunity in the DB")
    insert.add_argument("--json", default=None, help="Opportunity JSON object as a string")
    insert.add_argument("--json-file", default=None, help="Path to JSON file (use '-' for stdin)")
    insert.set_defaults(func=_reddit_insert_opportunity)

    imp = reddit_sub.add_parser("import-opportunities", help="Insert/update many opportunities")
    imp.add_argument("--json", default=None, help="JSON list or {opportunities:[...]} as a string")
    imp.add_argument("--json-file", default=None, help="Path to JSON file (use '-' for stdin)")
    imp.set_defaults(func=_reddit_import_opportunities)

    geo = subparsers.add_parser("geo", help="Geo/place enrichment")
    geo_sub = geo.add_subparsers(dest="geo_command", required=True)

    lookup = geo_sub.add_parser("maps-lookup", help="Look up a place on Google Maps (Playwright)")
    lookup.add_argument("--query", required=True, help="Query text (e.g. 'Atomic Coffee, Auckland, New Zealand')")
    lookup.add_argument("--headless", action="store_true", help="Run browser headless")
    lookup.add_argument("--slow-mo-ms", type=int, default=0, help="Slow down actions (ms)")
    lookup.add_argument("--timeout-ms", type=int, default=30000, help="Timeout for navigation/selectors")
    lookup.add_argument(
        "--cdp-url",
        default="",
        help="Optional CDP URL to attach to existing Chrome (e.g. http://127.0.0.1:9222)",
    )
    lookup.set_defaults(func=_geo_maps_lookup)

    enrich = geo_sub.add_parser("maps-enrich-csv", help="Enrich cafes CSV with Google Maps address + URL")
    enrich.add_argument("--input", required=True, help="Input CSV path")
    enrich.add_argument("--output", required=True, help="Output CSV path")
    enrich.add_argument("--name-column", default="cafe_name", help="Column containing the cafe name")
    enrich.add_argument("--city-column", default="city_guess", help="Column containing city hint")
    enrich.add_argument("--country-hint", default="New Zealand", help="Country hint appended to queries")
    enrich.add_argument("--max-rows", type=int, default=0, help="0 = all rows; otherwise limit")
    enrich.add_argument("--sleep-seconds", type=float, default=1.0, help="Delay between lookups")
    enrich.add_argument("--headless", action="store_true", help="Run browser headless")
    enrich.add_argument("--slow-mo-ms", type=int, default=0, help="Slow down actions (ms)")
    enrich.add_argument("--timeout-ms", type=int, default=30000, help="Timeout for navigation/selectors")
    enrich.add_argument(
        "--cdp-url",
        default="",
        help="Optional CDP URL to attach to existing Chrome (e.g. http://127.0.0.1:9222)",
    )
    enrich.set_defaults(func=_geo_maps_enrich_csv)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except KeyboardInterrupt:
        sys.stderr.write("Interrupted by user.\n")
        raise SystemExit(130)


if __name__ == "__main__":
    main()
