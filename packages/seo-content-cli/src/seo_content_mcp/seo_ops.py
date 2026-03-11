"""SEO Ops helpers for automation workspace.

This module mirrors the SEO ops logic exposed by the Flask UI in mcp/reddit-db-mcp,
but without Flask/runtime dependencies so it can be safely used from MCP tools.

Source of truth assumptions:
- Real website repo content is canonical (read-only here)
- Automation workspace is the writable staging layer (articles.json + automation content files)

All paths are resolved relative to the automation workspace root.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path


def _generate_url_slug(filename: str) -> str:
    """Generate url_slug from filename.
    
    Convention:
    - Filename format: {id:03d}_{slug}.mdx (e.g., "104_spy_vs_spx.mdx")
    - URL slug format: {slug} (e.g., "spy_vs_spx")
    
    Strips numeric ID prefix. Keeps underscores (standard convention).
    """
    # Get just the basename
    basename = Path(filename).name
    # Remove extension
    basename = basename.replace(".mdx", "").replace(".md", "")
    # Strip numeric prefix (e.g., "104_") - keeps underscores
    slug = re.sub(r'^\d+_', '', basename)
    return slug
from typing import Any


def parse_iso_date(value: Any):
    if not value or not isinstance(value, str):
        return None
    value = value.strip()
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def load_json_file(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def list_markdown_files(root: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for p in root.glob("**/*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in {".md", ".mdx"}:
            continue
        files[p.name] = p
    return files


def build_slug_to_repo_basename(repo_files: dict[str, Path]) -> dict[str, str]:
    """Map normalized slug -> repo basename.

    Slug is derived from the repo filename (strips numeric prefix, normalizes underscores/hyphens).
    """
    out: dict[str, str] = {}
    for basename, path in repo_files.items():
        slug = derive_slug_from_filename(basename)
        if slug and slug not in out:
            out[slug] = basename
    return out


def article_slug(article: dict[str, Any]) -> str:
    slug = normalize_slug(str(article.get("url_slug") or ""))
    if slug:
        return slug
    file_ref = str(article.get("file") or "")
    if file_ref:
        return derive_slug_from_filename(file_ref)
    return ""


def numeric_prefix_id(filename: str) -> int | None:
    m = re.match(r"^(\d+)[_-]", (filename or "").strip())
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def parse_frontmatter(path: Path) -> dict[str, str]:
    """Best-effort YAML frontmatter parser.

    Supports simple `key: value` lines between the first two `---` markers.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return {}

    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}

    fm_block = parts[1]
    out: dict[str, str] = {}
    for raw_line in fm_block.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            out[key] = value
    return out


def normalize_slug(value: str) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"\s+", "-", value)
    value = value.replace("_", "-")
    value = re.sub(r"[^a-z0-9\-]+", "", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value


def derive_slug_from_filename(filename: str) -> str:
    base = Path(filename).stem
    base = re.sub(r"^\d+[_-]+", "", base)
    return normalize_slug(base)


def check_article_slug_alignment(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Check if url_slug matches the filename (accounting for underscore/hyphen differences).
    
    This detects mismatches where url_slug doesn't match the expected format derived
    from the filename (minus numeric prefix), which causes GSC article mapping issues.
    
    Returns a list of mismatch records with keys:
    - id: article id
    - url_slug: the url_slug from articles.json
    - filename: the actual filename from the file field
    - expected_slug: what url_slug should be to match the filename
    """
    mismatches = []
    
    for article in articles:
        article_id = article.get("id")
        url_slug = str(article.get("url_slug") or "").strip()
        file_path = str(article.get("file") or "").strip()
        
        if not url_slug or not file_path:
            continue
        
        # Get expected slug from filename
        filename = Path(file_path).name
        expected_slug = _generate_url_slug(filename)
        
        if url_slug != expected_slug:
            mismatches.append({
                "id": article_id,
                "url_slug": url_slug,
                "filename": filename,
                "expected_slug": expected_slug,
            })
    
    return mismatches


def update_frontmatter_date(content_path: Path, new_date_iso: str) -> dict[str, Any]:
    """Update (or insert) frontmatter `date:` in a markdown/mdx file."""
    try:
        text = content_path.read_text(encoding="utf-8")
    except Exception as e:
        return {"ok": False, "error": f"Failed to read {content_path}: {e}"}

    if not text.startswith("---"):
        return {"ok": False, "error": "Missing frontmatter (expected file to start with ---)"}

    parts = text.split("---", 2)
    if len(parts) < 3:
        return {"ok": False, "error": "Malformed frontmatter (missing closing ---)"}

    fm = parts[1]
    body = parts[2]

    fm_lines = fm.splitlines()
    date_line_re = re.compile(r"^\s*(date|published_date|published)\s*:\s*.*$", re.IGNORECASE)
    replaced = False
    new_line = f'date: "{new_date_iso}"'

    for i, line in enumerate(fm_lines):
        if date_line_re.match(line):
            fm_lines[i] = new_line
            replaced = True
            break

    if not replaced:
        insert_at = 0
        for i, line in enumerate(fm_lines):
            if line.strip().lower().startswith("title:"):
                insert_at = i + 1
                break
        fm_lines.insert(insert_at, new_line)

    new_text = "---\n" + "\n".join(fm_lines).rstrip() + "\n---" + body
    try:
        content_path.write_text(new_text, encoding="utf-8")
    except Exception as e:
        return {"ok": False, "error": f"Failed to write {content_path}: {e}"}

    return {"ok": True, "replaced": replaced}


def _md_escape(text: Any) -> str:
    if text is None:
        return ""
    s = str(text)
    return s.replace("\r\n", "\n").replace("\r", "\n")


def _md_code(s: Any) -> str:
    escaped = _md_escape(s).replace("`", "\\`")
    return f"`{escaped}`"


@dataclass(frozen=True)
class SEOOpsPaths:
    workspace_root: Path
    registry_path: Path


class SEOOps:
    def __init__(self, workspace_root: str):
        root = Path(workspace_root).resolve()
        self._paths = SEOOpsPaths(
            workspace_root=root,
            registry_path=(root / "WEBSITES_REGISTRY.json").resolve(),
        )

    @property
    def workspace_root(self) -> Path:
        return self._paths.workspace_root

    def load_websites_registry(self) -> list[dict[str, Any]]:
        if not self._paths.registry_path.exists():
            return []
        data = load_json_file(self._paths.registry_path)
        return list(data.get("websites", []) or [])

    def get_site_by_id(self, website_id: str) -> dict[str, Any] | None:
        for w in self.load_websites_registry():
            if w.get("id") == website_id:
                return w
        return None

    def get_repo_content_dir(self, site: dict[str, Any]) -> Path | None:
        repo_root = site.get("source_repo_local_path")
        repo_content_dir = site.get("source_content_dir")
        if not repo_root or not repo_content_dir:
            return None
        repo_content_path = Path(str(repo_content_dir))
        if repo_content_path.is_absolute():
            return repo_content_path.resolve()
        return (Path(str(repo_root)) / repo_content_path).resolve()

    def get_automation_site_root(self, site: dict[str, Any]) -> Path | None:
        site_path = site.get("path") or ""
        if not site_path:
            return None
        return (self.workspace_root / site_path).resolve()

    def get_automation_content_dir(self, site: dict[str, Any]) -> Path | None:
        root = self.get_automation_site_root(site)
        if not root:
            return None
        p = (root / "content").resolve()
        return p if p.exists() else None

    def get_articles_path(self, site: dict[str, Any]) -> Path | None:
        rel = site.get("articles")
        if not rel:
            return None
        return (self.workspace_root / str(rel)).resolve()

    def load_site_articles(self, site: dict[str, Any]) -> list[dict[str, Any]]:
        articles_path = self.get_articles_path(site)
        if not articles_path or not articles_path.exists():
            return []
        data = load_json_file(articles_path)
        return list(data.get("articles", []) or [])

    def build_repo_date_map(self, site: dict[str, Any]) -> dict[str, str]:
        """Map repo basenames -> canonical published date (YYYY-MM-DD) from frontmatter."""
        repo_content = self.get_repo_content_dir(site)
        if not repo_content or not repo_content.exists():
            return {}

        out: dict[str, str] = {}
        for name, path in list_markdown_files(repo_content).items():
            fm = parse_frontmatter(path)
            raw = fm.get("date") or fm.get("published") or fm.get("published_date")
            if not raw:
                continue
            d = parse_iso_date(str(raw)[:10])
            if d:
                out[name] = d.isoformat()
        return out

    def compute_site_metrics(self, site: dict[str, Any]) -> dict[str, Any]:
        today = datetime.now().date()
        site_root = self.get_automation_site_root(site)

        repo_dates = self.build_repo_date_map(site)

        articles = self.load_site_articles(site)
        total = len(articles)

        published = [a for a in articles if (a.get("status") or "").lower() == "published"]
        ready = [a for a in articles if (a.get("status") or "").lower() == "ready_to_publish"]
        drafts = [
            a
            for a in articles
            if (a.get("status") or "").lower() in {"draft", "staged", "ready_to_publish"}
        ]

        latest_published_date = None
        for a in published:
            basename = Path(str(a.get("file") or "")).name
            effective_raw = repo_dates.get(basename) or a.get("published_date")
            d = parse_iso_date(effective_raw)
            if d and (latest_published_date is None or d > latest_published_date):
                latest_published_date = d

        future_dates = 0
        missing_dates = 0
        bad_dates = 0
        missing_slugs = 0
        slug_counts: dict[str, int] = {}

        for a in articles:
            basename = Path(str(a.get("file") or "")).name
            raw_date = repo_dates.get(basename) or a.get("published_date")
            if raw_date is None or str(raw_date).strip() == "":
                missing_dates += 1
            else:
                d = parse_iso_date(raw_date)
                if not d:
                    bad_dates += 1
                elif d > today:
                    future_dates += 1

            slug = (a.get("url_slug") or "").strip()
            if not slug:
                missing_slugs += 1
            else:
                slug_counts[slug] = slug_counts.get(slug, 0) + 1

        duplicate_slugs = sum(1 for _, c in slug_counts.items() if c > 1)

        missing_files = 0
        if site_root:
            for a in articles:
                rel = a.get("file")
                if not rel:
                    continue
                rel = str(rel).lstrip("./")
                candidate = (site_root / rel).resolve()
                if not candidate.exists():
                    missing_files += 1

        content_file_count = None
        if site_root and (site_root / "content").exists():
            try:
                content_dir = site_root / "content"
                content_file_count = sum(
                    1
                    for p in content_dir.iterdir()
                    if p.is_file() and p.suffix.lower() in {".md", ".mdx"}
                )
            except Exception:
                content_file_count = None

        return {
            "id": site.get("id"),
            "name": site.get("name"),
            "status": site.get("status"),
            "path": site.get("path"),
            "articles_path": site.get("articles"),
            "total": total,
            "published": len(published),
            "ready_to_publish": len(ready),
            "drafts": len(drafts),
            "latest_published_date": latest_published_date.isoformat() if latest_published_date else None,
            "future_dates": future_dates,
            "missing_dates": missing_dates,
            "bad_dates": bad_dates,
            "missing_slugs": missing_slugs,
            "duplicate_slugs": duplicate_slugs,
            "missing_files": missing_files,
            "content_file_count": content_file_count,
            "has_source_repo_config": bool(site.get("source_repo_local_path")),
            "source_repo_local_path": site.get("source_repo_local_path"),
            "source_content_dir": site.get("source_content_dir"),
            "sitemap_url": site.get("sitemap_url"),
        }

    def overview(self) -> dict[str, Any]:
        websites = self.load_websites_registry()
        sites = [self.compute_site_metrics(w) for w in websites]

        overall = {
            "site_count": len(sites),
            "total_articles": sum(s["total"] for s in sites),
            "total_published": sum(s["published"] for s in sites),
            "total_ready_to_publish": sum(int(s.get("ready_to_publish") or 0) for s in sites),
            "total_drafts": sum(s["drafts"] for s in sites),
            "total_future_dates": sum(s["future_dates"] for s in sites),
            "total_missing_dates": sum(s["missing_dates"] for s in sites),
            "total_missing_files": sum(s["missing_files"] for s in sites),
        }

        return {
            "ok": True,
            "registry": str(self._paths.registry_path),
            "generated": datetime.now().date().isoformat(),
            "overall": overall,
            "sites": sites,
        }

    def compute_repo_drift(self, site: dict[str, Any]) -> dict[str, Any]:
        """Compare automation content files vs real repo content files by basename."""
        repo_content = self.get_repo_content_dir(site)
        if not repo_content or not repo_content.exists():
            return {"ok": False, "error": f"Repo content dir not found: {repo_content}"}

        automation_content = self.get_automation_content_dir(site)
        if not automation_content or not automation_content.exists():
            return {"ok": False, "error": f"Automation content dir not found: {automation_content}"}

        repo_files = list_markdown_files(repo_content)
        auto_files = list_markdown_files(automation_content)

        missing_in_repo = sorted([name for name in auto_files.keys() if name not in repo_files])
        missing_in_automation = sorted([name for name in repo_files.keys() if name not in auto_files])

        mismatches = []
        for name in sorted(set(repo_files.keys()) & set(auto_files.keys())):
            repo_path = repo_files[name]
            auto_path = auto_files[name]
            try:
                repo_hash = sha256_file(repo_path)
                auto_hash = sha256_file(auto_path)
            except Exception as e:
                mismatches.append({
                    "file": name,
                    "repo_path": str(repo_path),
                    "automation_path": str(auto_path),
                    "error": str(e),
                })
                continue

            if repo_hash != auto_hash:
                mismatches.append({
                    "file": name,
                    "repo_path": str(repo_path),
                    "automation_path": str(auto_path),
                    "repo_sha256": repo_hash,
                    "automation_sha256": auto_hash,
                })

        return {
            "ok": True,
            "site_id": site.get("id"),
            "repo_content_dir": str(repo_content),
            "automation_content_dir": str(automation_content),
            "repo_files": len(repo_files),
            "automation_files": len(auto_files),
            "missing_in_repo": missing_in_repo,
            "missing_in_automation": missing_in_automation,
            "mismatches": mismatches,
        }

    def preview_import_from_repo(self, site: dict[str, Any]) -> dict[str, Any]:
        repo_content = self.get_repo_content_dir(site)
        if not repo_content or not repo_content.exists():
            return {"ok": False, "error": f"Repo content dir not found: {repo_content}"}

        articles_path = self.get_articles_path(site)
        if not articles_path or not articles_path.exists():
            return {"ok": False, "error": f"articles.json not found: {articles_path}"}

        articles_doc = load_json_file(articles_path)
        articles = list(articles_doc.get("articles", []) or [])

        by_basename: dict[str, dict[str, Any]] = {}
        by_slug: dict[str, dict[str, Any]] = {}
        max_id = 0
        for a in articles:
            try:
                max_id = max(max_id, int(a.get("id") or 0))
            except Exception:
                pass
            f = a.get("file")
            if f:
                by_basename[Path(str(f)).name] = a
            slug = (a.get("url_slug") or "").strip()
            if slug:
                by_slug[slug] = a

        repo_files = list_markdown_files(repo_content)
        changes = {"new": [], "updated": [], "skipped": []}

        for name, path in repo_files.items():
            fm = parse_frontmatter(path)
            fm_title = fm.get("title")
            fm_slug = fm.get("slug") or fm.get("url_slug")
            fm_date = fm.get("date") or fm.get("published") or fm.get("published_date")

            date_val = None
            if fm_date:
                date_val = parse_iso_date(str(fm_date)[:10])
            slug_val = normalize_slug(fm_slug) if fm_slug else derive_slug_from_filename(name)

            target = by_basename.get(name) or (by_slug.get(slug_val) if slug_val else None)

            if not target:
                next_id = max_id + 1
                max_id = next_id
                changes["new"].append({
                    "id": next_id,
                    "file": f"./content/{name}",
                    "title": fm_title or name,
                    "url_slug": slug_val,
                    "published_date": date_val.isoformat() if date_val else None,
                    "status": "published",
                    "source_file": str(path),
                })
                continue

            updates: dict[str, Any] = {}
            if fm_title and (target.get("title") != fm_title):
                updates["title"] = {"from": target.get("title"), "to": fm_title}

            if slug_val and (target.get("url_slug") or "").strip() != slug_val:
                if not (target.get("url_slug") or "").strip():
                    updates["url_slug"] = {"from": target.get("url_slug"), "to": slug_val}

            if date_val:
                current = parse_iso_date(target.get("published_date"))
                if current != date_val:
                    updates["published_date"] = {"from": target.get("published_date"), "to": date_val.isoformat()}

            if (target.get("status") or "").lower() != "published":
                updates["status"] = {"from": target.get("status"), "to": "published"}

            if updates:
                changes["updated"].append({
                    "id": target.get("id"),
                    "file": target.get("file"),
                    "source_file": str(path),
                    "updates": updates,
                })
            else:
                changes["skipped"].append({
                    "id": target.get("id"),
                    "file": target.get("file"),
                    "source_file": str(path),
                })

        return {
            "ok": True,
            "site_id": site.get("id"),
            "articles_json": str(articles_path),
            "repo_content_dir": str(repo_content),
            "repo_files": len(repo_files),
            "changes": changes,
        }

    def apply_import_from_repo(self, site: dict[str, Any]) -> dict[str, Any]:
        preview = self.preview_import_from_repo(site)
        if not preview.get("ok"):
            return preview

        articles_path = Path(preview["articles_json"]).resolve()
        doc = load_json_file(articles_path)
        articles = list(doc.get("articles", []) or [])

        by_id: dict[int, dict[str, Any]] = {}
        for a in articles:
            try:
                by_id[int(a.get("id"))] = a
            except Exception:
                continue

        for upd in preview["changes"]["updated"]:
            try:
                aid = int(upd["id"])
            except Exception:
                continue
            target = by_id.get(aid)
            if not target:
                continue
            updates = upd.get("updates", {})
            for field, change in updates.items():
                target[field] = change.get("to")

        for n in preview["changes"]["new"]:
            new_entry = {
                "id": n.get("id"),
                "title": n.get("title"),
                "url_slug": n.get("url_slug"),
                "file": n.get("file"),
                "target_keyword": "",
                "keyword_difficulty": "",
                "target_volume": 0,
                "published_date": n.get("published_date") or "",
                "word_count": 0,
                "status": n.get("status") or "published",
                "content_gaps_addressed": [],
                "estimated_traffic_monthly": "",
            }
            articles.append(new_entry)

        def _id_key(a: dict[str, Any]):
            try:
                return int(a.get("id") or 0)
            except Exception:
                return 0

        articles.sort(key=_id_key)
        doc["articles"] = articles
        articles_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        preview["applied"] = True
        return preview

    # ------------------------------------------------------------------
    # Pull content files from production repo → automation
    # ------------------------------------------------------------------

    def pull_content_from_repo(
        self,
        site: dict[str, Any],
        *,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        """Copy content files from the production repo into automation.

        This brings the automation workspace up-to-date with whatever has
        changed in the production repo (widget tweaks, image swaps, manual
        edits, etc.) **before** we schedule or deploy new articles.

        Safety rules:
        - Files for ``ready_to_publish`` or ``draft`` articles in
          articles.json are **never** overwritten — those are staged work
          inside the automation repo.
        - All other mismatches (published / unknown status) are pulled
          from production.
        - Files that exist in production but not in automation are always
          pulled (they are likely articles created outside the automation
          pipeline).

        After copying files, ``apply_import_from_repo`` is called to sync
        articles.json metadata (titles, dates, slugs) from the freshly
        pulled frontmatter.

        Args:
            site: Website dict from the registry.
            dry_run: If True (default), only report what would change.

        Returns:
            A JSON-serialisable dict with pull details.
        """
        import shutil

        repo_content = self.get_repo_content_dir(site)
        if not repo_content or not repo_content.exists():
            return {"ok": False, "error": f"Production content dir not found: {repo_content}"}

        automation_content = self.get_automation_content_dir(site)
        if not automation_content:
            # content/ dir may not exist yet — create it if we're not dry-running
            site_root = self.get_automation_site_root(site)
            if not site_root:
                return {"ok": False, "error": "Cannot resolve automation site root"}
            automation_content = site_root / "content"
            if not dry_run:
                automation_content.mkdir(parents=True, exist_ok=True)
            elif not automation_content.exists():
                # For dry-run, treat everything as missing-in-automation
                pass

        # Repo-local mode: automation content may resolve to the same directory as repo content
        # (e.g., the automation workspace content/ is a symlink into the repo's real content dir).
        # In that case, pulling would attempt to copy files onto themselves and can error; treat as no-op.
        try:
            if repo_content.resolve() == automation_content.resolve():
                return {
                    "ok": True,
                    "dry_run": dry_run,
                    "site_id": site.get("id"),
                    "production_dir": str(repo_content),
                    "automation_dir": str(automation_content),
                    "production_files": 0,
                    "automation_files": 0,
                    "files_to_pull": 0,
                    "files_skipped": 0,
                    "protected_basenames": [],
                    "pull_details": [],
                    "skip_details": [],
                    "reason": "noop_same_dir",
                }
        except Exception:
            # Best-effort only.
            pass

        # Build a set of basenames we must NOT overwrite (staging work)
        protected_basenames: set[str] = set()
        for a in self.load_site_articles(site):
            st = (a.get("status") or "").strip().lower()
            if st in {"ready_to_publish", "draft", "staged"}:
                bn = Path(str(a.get("file") or "")).name
                if bn:
                    protected_basenames.add(bn)

        # Compute drift
        drift = self.compute_repo_drift(site)
        if not drift.get("ok"):
            return {"ok": False, "error": drift.get("error", "Drift check failed")}

        to_copy: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []

        # 1) Files in production but not in automation → always pull
        for name in drift.get("missing_in_automation", []):
            if name in protected_basenames:
                skipped.append({"file": name, "reason": "protected_status"})
            else:
                to_copy.append({
                    "file": name,
                    "reason": "missing_in_automation",
                    "source": str(repo_content / name),
                })

        # 2) Mismatched files → pull unless protected
        for m in drift.get("mismatches", []):
            name = m.get("file")
            if not name:
                continue
            if name in protected_basenames:
                skipped.append({"file": name, "reason": "protected_status"})
            else:
                to_copy.append({
                    "file": name,
                    "reason": "content_mismatch",
                    "source": str(repo_content / name),
                })

        result: dict[str, Any] = {
            "ok": True,
            "dry_run": dry_run,
            "site_id": site.get("id"),
            "production_dir": str(repo_content),
            "automation_dir": str(automation_content),
            "production_files": drift.get("repo_files", 0),
            "automation_files": drift.get("automation_files", 0),
            "files_to_pull": len(to_copy),
            "files_skipped": len(skipped),
            "protected_basenames": sorted(protected_basenames),
            "pull_details": to_copy,
            "skip_details": skipped,
        }

        if dry_run:
            return result

        # Actually copy files
        copied: list[str] = []
        failed: list[dict[str, str]] = []
        for item in to_copy:
            src = Path(item["source"])
            dst = automation_content / item["file"]
            try:
                shutil.copy2(src, dst)
                copied.append(item["file"])
            except Exception as e:
                failed.append({"file": item["file"], "error": str(e)})

        result["copied"] = copied
        result["failed"] = failed
        result["files_pulled"] = len(copied)

        # Sync articles.json metadata from the freshly-pulled frontmatter
        import_result = self.apply_import_from_repo(site)
        import_changes = import_result.get("changes", {})
        result["import_sync"] = {
            "new_articles": len(import_changes.get("new", [])),
            "updated_articles": len(import_changes.get("updated", [])),
        }

        # Second pass: import_apply may have changed some article statuses
        # from ready_to_publish → published (because they already exist in
        # production from a prior deploy).  Those files are now unprotected
        # and may still differ.  Do one more drift+copy pass so the command
        # is fully idempotent in a single invocation.
        second_protected: set[str] = set()
        for a in self.load_site_articles(site):
            st = (a.get("status") or "").strip().lower()
            if st in {"ready_to_publish", "draft", "staged"}:
                bn = Path(str(a.get("file") or "")).name
                if bn:
                    second_protected.add(bn)

        drift2 = self.compute_repo_drift(site)
        extra_copied: list[str] = []
        if drift2.get("ok"):
            for name in drift2.get("missing_in_automation", []):
                if name not in second_protected and name not in copied:
                    src = repo_content / name
                    dst = automation_content / name
                    try:
                        shutil.copy2(src, dst)
                        extra_copied.append(name)
                    except Exception as e:
                        failed.append({"file": name, "error": str(e)})
            for m in drift2.get("mismatches", []):
                name = m.get("file")
                if not name:
                    continue
                if name not in second_protected and name not in copied:
                    src = repo_content / name
                    dst = automation_content / name
                    try:
                        shutil.copy2(src, dst)
                        extra_copied.append(name)
                    except Exception as e:
                        failed.append({"file": name, "error": str(e)})

        if extra_copied:
            copied.extend(extra_copied)
            result["copied"] = copied
            result["files_pulled"] = len(copied)
            result["second_pass_pulled"] = len(extra_copied)

        return result

    # ------------------------------------------------------------------
    # Deploy selected content files from automation → production repo
    # ------------------------------------------------------------------

    def deploy_files_to_repo(
        self,
        site: dict[str, Any],
        *,
        files: list[str],
        dry_run: bool = True,
        allow_overwrite: bool = False,
    ) -> dict[str, Any]:
        """
        Copy a scoped list of basenames from automation content/ to production content dir.

        This is intentionally explicit for workflows like indexing remediation where
        you may be updating already-published content.
        """
        import shutil

        repo_content = self.get_repo_content_dir(site)
        if not repo_content or not repo_content.exists():
            return {"ok": False, "error": f"Production content dir not found: {repo_content}"}

        automation_content = self.get_automation_content_dir(site)
        if not automation_content or not automation_content.exists():
            return {"ok": False, "error": f"Automation content dir not found: {automation_content}"}

        # Repo-local mode: if automation content resolves to repo content, deploy is a no-op.
        try:
            if repo_content.resolve() == automation_content.resolve():
                normalized = [Path(str(f)).name for f in (files or []) if Path(str(f)).name]
                return {
                    "ok": True,
                    "site_id": site.get("id"),
                    "dry_run": dry_run,
                    "allow_overwrite": allow_overwrite,
                    "production_dir": str(repo_content),
                    "automation_dir": str(automation_content),
                    "files_requested": list(files),
                    "files_normalized": normalized,
                    "files_copied": 0,
                    "files_skipped": len(normalized),
                    "files_failed": 0,
                    "copied": [],
                    "skipped": [{"file": bn, "reason": "noop_same_dir"} for bn in normalized],
                    "failed": [],
                    "results": [{"file": bn, "status": "noop_same_dir"} for bn in normalized],
                    "reason": "noop_same_dir",
                }
        except Exception:
            pass

        normalized: list[str] = []
        for f in files:
            bn = Path(str(f)).name
            if not bn:
                continue
            # Enforce basename-only (defense-in-depth).
            normalized.append(bn)

        results: list[dict[str, Any]] = []
        copied: list[str] = []
        skipped: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []

        for bn in normalized:
            src = automation_content / bn
            dst = repo_content / bn
            if not src.exists():
                failed.append({"file": bn, "error": "source_not_found", "source": str(src)})
                results.append({"file": bn, "status": "failed", "error": "source_not_found"})
                continue

            if dst.exists() and not allow_overwrite:
                skipped.append({"file": bn, "reason": "target_exists_overwrite_not_allowed", "target": str(dst)})
                results.append({"file": bn, "status": "skipped", "reason": "target_exists_overwrite_not_allowed"})
                continue

            if dry_run:
                results.append({"file": bn, "status": "would_copy", "source": str(src), "target": str(dst)})
                continue

            try:
                shutil.copy2(src, dst)
                copied.append(bn)
                results.append({"file": bn, "status": "copied", "source": str(src), "target": str(dst)})
            except Exception as e:
                failed.append({"file": bn, "error": str(e), "source": str(src), "target": str(dst)})
                results.append({"file": bn, "status": "failed", "error": str(e)})

        return {
            "ok": True,
            "site_id": site.get("id"),
            "dry_run": dry_run,
            "allow_overwrite": allow_overwrite,
            "production_dir": str(repo_content),
            "automation_dir": str(automation_content),
            "files_requested": list(files),
            "files_normalized": normalized,
            "files_copied": len(copied),
            "files_skipped": len(skipped),
            "files_failed": len(failed),
            "copied": copied,
            "skipped": skipped,
            "failed": failed,
            "results": results,
        }

    def analyze_site_dates(self, site: dict[str, Any]) -> dict[str, Any]:
        today = datetime.now().date()
        articles = self.load_site_articles(site)
        repo_dates = self.build_repo_date_map(site)
        issues = {"future": [], "missing": [], "bad": [], "overlaps": []}

        by_date: dict[str, list[int]] = {}
        for a in articles:
            basename = Path(str(a.get("file") or "")).name
            raw = repo_dates.get(basename) or a.get("published_date")
            if raw is None or str(raw).strip() == "":
                issues["missing"].append(a.get("id"))
                continue
            d = parse_iso_date(raw)
            if d is None:
                issues["bad"].append(a.get("id"))
                continue
            if d > today:
                issues["future"].append(a.get("id"))
            by_date.setdefault(d.isoformat(), []).append(a.get("id"))

        for d, ids in by_date.items():
            if len(ids) > 1:
                issues["overlaps"].append({"date": d, "ids": ids})

        return {
            "ok": True,
            "site_id": site.get("id"),
            "today": today.isoformat(),
            "total": len(articles),
            "issues": issues,
        }

    def validate_site_index(
        self,
        site: dict[str, Any],
        ids: list[int] | None = None,
        max_repo_candidates: int = 5,
    ) -> dict[str, Any]:
        """Validate articles.json entries against repo + automation content.

        This is index-aware validation (unlike drift), so it can detect entries
        that point to missing content in BOTH places.
        """

        articles = self.load_site_articles(site)
        if ids:
            want = {int(x) for x in ids}

            def _keep(a: dict[str, Any]) -> bool:
                try:
                    return int(a.get("id")) in want
                except Exception:
                    return False

            articles = [a for a in articles if _keep(a)]

        repo_content = self.get_repo_content_dir(site)
        repo_files: dict[str, Path] = {}
        if repo_content and repo_content.exists():
            repo_files = list_markdown_files(repo_content)
        repo_slug_map = build_slug_to_repo_basename(repo_files) if repo_files else {}

        auto_root = self.get_automation_site_root(site)
        auto_files: dict[str, Path] = {}
        auto_content = self.get_automation_content_dir(site)
        if auto_content and auto_content.exists():
            auto_files = list_markdown_files(auto_content)

        repo_dates = self.build_repo_date_map(site)

        results: list[dict[str, Any]] = []
        missing_everywhere = 0
        repo_present = 0
        auto_present = 0

        for a in articles:
            rel_file = str(a.get("file") or "")
            basename = Path(rel_file).name if rel_file else ""

            a_slug = article_slug(a)
            repo_basename = None
            if basename and basename in repo_files:
                repo_basename = basename
            elif a_slug and a_slug in repo_slug_map:
                repo_basename = repo_slug_map.get(a_slug)

            repo_path = repo_files.get(repo_basename) if repo_basename else None
            in_repo = bool(repo_path)
            if in_repo:
                repo_present += 1

            auto_path: Path | None = None
            in_auto = False
            if auto_root and rel_file:
                candidate = (auto_root / rel_file).resolve()
                auto_path = candidate
                in_auto = candidate.exists()
            elif basename and basename in auto_files:
                auto_path = auto_files.get(basename)
                in_auto = bool(auto_path and auto_path.exists())

            if in_auto:
                auto_present += 1

            repo_date = repo_dates.get(repo_basename) if repo_basename else None
            index_date = a.get("published_date")
            auto_fm_date = None
            if in_auto and auto_path:
                fm = parse_frontmatter(auto_path)
                auto_fm_date = fm.get("date") or fm.get("published") or fm.get("published_date")
                if auto_fm_date:
                    d = parse_iso_date(str(auto_fm_date)[:10])
                    auto_fm_date = d.isoformat() if d else str(auto_fm_date)

            effective_date = repo_date or auto_fm_date or (str(index_date).strip() if index_date else "") or None

            status = (a.get("status") or "").strip()
            suggested_status = "published" if in_repo else status

            repo_candidates: list[str] = []
            if not in_repo and repo_files and max_repo_candidates > 0:
                if a_slug:
                    for fname in repo_files.keys():
                        if a_slug in normalize_slug(fname):
                            repo_candidates.append(fname)
                    repo_candidates = repo_candidates[: max_repo_candidates]

            if not in_repo and not in_auto:
                missing_everywhere += 1

            results.append(
                {
                    "id": a.get("id"),
                    "title": a.get("title"),
                    "target_keyword": a.get("target_keyword"),
                    "url_slug": a.get("url_slug"),
                    "file": a.get("file"),
                    "basename": basename,
                    "status": status,
                    "suggested_status": suggested_status,
                    "index_published_date": (str(index_date).strip() if index_date else "") or None,
                    "repo_published_date": repo_date,
                    "automation_frontmatter_date": auto_fm_date,
                    "effective_published_date": effective_date,
                    "in_repo": in_repo,
                    "repo_path": str(repo_path) if repo_path else None,
                    "in_automation": in_auto,
                    "automation_path": str(auto_path) if auto_path else None,
                    "repo_filename_candidates": repo_candidates,
                }
            )

        return {
            "ok": True,
            "site_id": site.get("id"),
            "checked": len(results),
            "summary": {
                "repo_configured": bool(repo_content),
                "repo_present": repo_present,
                "automation_present": auto_present,
                "missing_everywhere": missing_everywhere,
            },
            "entries": results,
        }

    def compute_mutable_articles(
        self,
        site: dict[str, Any],
        *,
        status_filter: set[str] | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        today = datetime.now().date()
        articles = self.load_site_articles(site)

        repo_content = self.get_repo_content_dir(site)
        repo_files: dict[str, Path] = {}
        if repo_content and repo_content.exists():
            repo_files = list_markdown_files(repo_content)

        repo_basenames: set[str] = set(repo_files.keys())
        repo_slug_map = build_slug_to_repo_basename(repo_files) if repo_files else {}

        max_repo_id = 0
        for bn in repo_basenames:
            pid = numeric_prefix_id(bn)
            if pid and pid > max_repo_id:
                max_repo_id = pid

        mutable: list[dict[str, Any]] = []
        immutable: list[dict[str, Any]] = []

        normalized_filter = {s.strip().lower() for s in (status_filter or set()) if str(s).strip()}

        for a in articles:
            status = (a.get("status") or "").lower().strip()
            basename = Path(str(a.get("file") or "")).name
            a_slug = article_slug(a)
            in_repo = (basename in repo_basenames) if basename else False
            if (not in_repo) and a_slug and (a_slug in repo_slug_map):
                in_repo = True

            # When an explicit status filter is set, use it as primary
            # classifier.  The article's status takes precedence over repo
            # presence so that e.g. ready_to_publish articles can still be
            # rescheduled even after an earlier deploy copied them to the repo.
            if normalized_filter:
                if status in normalized_filter:
                    mutable.append(a)
                else:
                    immutable.append(a)
                continue

            # Without an explicit filter, in-repo articles are immutable.
            if in_repo:
                immutable.append(a)
                continue

            raw = (a.get("published_date") or "")
            raw = str(raw).strip() if raw is not None else ""
            d = parse_iso_date(raw) if raw else None
            is_missing_date = not raw
            is_future = d is not None and d > today

            aid = 0
            try:
                aid = int(a.get("id") or 0)
            except Exception:
                aid = 0
            newer_than_repo = bool(max_repo_id and aid and aid > max_repo_id)

            # Only treat as mutable if it clearly needs scheduling:
            # - drafts/staged
            # - missing/future date
            # - OR the article is clearly newer than the repo's max numeric ID
            #   (covers newly-generated content that may be marked "published" in automation
            #   but is not yet present in the repo).
            if status in {"draft", "staged", "ready_to_publish"} or is_missing_date or is_future or newer_than_repo:
                mutable.append(a)
            else:
                immutable.append(a)

        ctx = {
            "repo_configured": bool(repo_content),
            "repo_file_count": len(repo_basenames),
            "repo_max_numeric_id": max_repo_id if max_repo_id else None,
            "immutable_count": len(immutable),
            "mutable_count": len(mutable),
        }
        return mutable, ctx

    def preview_date_schedule(
        self,
        site: dict[str, Any],
        spacing_days: int = 2,
        statuses: list[str] | None = None,
    ) -> dict[str, Any]:
        today = datetime.now().date()
        spacing_days = max(1, int(spacing_days))

        status_filter = {str(s).strip().lower() for s in (statuses or []) if str(s).strip()}
        mutable, ctx = self.compute_mutable_articles(site, status_filter=status_filter or None)
        if not mutable:
            return {"ok": True, "site_id": site.get("id"), "spacing_days": spacing_days, "schedule": [], "context": ctx}

        repo_content = self.get_repo_content_dir(site)
        repo_files: dict[str, Path] = {}
        if repo_content and repo_content.exists():
            repo_files = list_markdown_files(repo_content)

        repo_basenames: set[str] = set(repo_files.keys())
        repo_slug_map = build_slug_to_repo_basename(repo_files) if repo_files else {}

        repo_dates = self.build_repo_date_map(site)

        immutable_dates = []
        for a in self.load_site_articles(site):
            basename = Path(str(a.get("file") or "")).name
            a_slug = article_slug(a)
            repo_basename = None
            if basename and basename in repo_basenames:
                repo_basename = basename
            elif a_slug and a_slug in repo_slug_map:
                repo_basename = repo_slug_map.get(a_slug)

            if repo_basename:
                effective_raw = repo_dates.get(repo_basename) or a.get("published_date")
                d = parse_iso_date(effective_raw)
                if d and d <= today:
                    immutable_dates.append(d)

        anchor = max(immutable_dates) if immutable_dates else None
        if not anchor:
            mutable_dates = [parse_iso_date(a.get("published_date")) for a in mutable]
            mutable_dates = [d for d in mutable_dates if d and d <= today]
            anchor = max(mutable_dates) if mutable_dates else today

        # Collect ALL occupied dates (immutable articles) so we can skip them.
        occupied: set[str] = set()
        for d in immutable_dates:
            occupied.add(d.isoformat())
        # Also include dates from non-mutable articles loaded from articles.json
        # that might not be in repo yet (e.g. different statuses).
        mutable_ids = {int(a.get("id") or 0) for a in mutable}
        for a in self.load_site_articles(site):
            try:
                aid = int(a.get("id") or 0)
            except Exception:
                aid = 0
            if aid in mutable_ids:
                continue
            ds = str(a.get("published_date") or "").strip()
            if ds:
                occupied.add(ds)

        n = len(mutable)

        def _generate_dates_skipping_occupied(
            start: date, direction: int, count: int, spacing: int
        ) -> list[str]:
            """Generate `count` dates spaced `spacing` days apart, skipping occupied ones.
            direction: +1 for forward, -1 for backward from `start`.
            """
            result: list[str] = []
            cursor = start
            while len(result) < count:
                iso = cursor.isoformat()
                if iso not in occupied:
                    result.append(iso)
                cursor += timedelta(days=direction * 1)
                # Safety: don't go more than count * spacing * 3 days
                if abs((cursor - start).days) > count * spacing * 3:
                    break
            return result

        schedule_dates: list[str] = []
        mode = "forward"
        available_days = (today - anchor).days
        forward_needed = spacing_days * n

        if available_days >= forward_needed:
            start = anchor + timedelta(days=spacing_days)
            schedule_dates = _generate_dates_skipping_occupied(start, +1, n, spacing_days)
            # Re-apply spacing: we skipped occupied dates but need to respect min spacing.
            # Rebuild with proper spacing, skipping occupied.
            schedule_dates = []
            cursor = anchor + timedelta(days=spacing_days)
            while len(schedule_dates) < n:
                iso = cursor.isoformat()
                if iso not in occupied:
                    schedule_dates.append(iso)
                    cursor += timedelta(days=spacing_days)
                else:
                    cursor += timedelta(days=1)
                if (cursor - anchor).days > n * spacing_days * 3:
                    break
        else:
            mode = "backward"
            # Start from today and work backward, maintaining spacing, skipping occupied.
            schedule_dates = []
            cursor = today
            while len(schedule_dates) < n:
                iso = cursor.isoformat()
                if iso not in occupied:
                    schedule_dates.append(iso)
                    cursor -= timedelta(days=spacing_days)
                else:
                    cursor -= timedelta(days=1)
                if (today - cursor).days > n * spacing_days * 3:
                    break
            schedule_dates.reverse()  # oldest first

        def sort_key(a: dict[str, Any]):
            d = parse_iso_date(a.get("published_date"))
            return (d or datetime.min.date(), int(a.get("id") or 0))

        mutable_sorted = sorted(mutable, key=sort_key)

        schedule = []
        for a, new_date in zip(mutable_sorted, schedule_dates):
            old = str(a.get("published_date") or "").strip()
            if old == new_date:
                continue
            schedule.append({
                "id": a.get("id"),
                "file": a.get("file"),
                "title": a.get("title"),
                "from": a.get("published_date"),
                "to": new_date,
                "status": a.get("status"),
            })

        return {
            "ok": True,
            "site_id": site.get("id"),
            "today": today.isoformat(),
            "anchor": anchor.isoformat() if anchor else None,
            "mode": mode,
            "spacing_days": spacing_days,
            "context": ctx,
            "schedule": schedule,
        }

    def apply_date_schedule(
        self,
        site: dict[str, Any],
        spacing_days: int = 2,
        statuses: list[str] | None = None,
    ) -> dict[str, Any]:
        preview = self.preview_date_schedule(site, spacing_days=spacing_days, statuses=statuses)
        if not preview.get("ok"):
            return preview

        schedule = list(preview.get("schedule", []) or [])

        status_filter = {str(s).strip().lower() for s in (statuses or []) if str(s).strip()}

        # Hard safety gate: only enforce when no explicit status filter is provided.
        # With status filters (e.g., ready_to_publish), scheduling is already scoped
        # to new/staged content and should be allowed even if IDs are <= repo_max.
        if schedule and not status_filter:
            ctx = preview.get("context", {}) or {}
            repo_max = ctx.get("repo_max_numeric_id")
            if repo_max is not None:
                unsafe: list[dict[str, Any]] = []
                for item in schedule:
                    try:
                        aid = int(item.get("id") or 0)
                    except Exception:
                        aid = 0
                    if aid and aid <= int(repo_max):
                        unsafe.append(item)

                if unsafe:
                    return {
                        "ok": False,
                        "error": "Refusing to apply schedule: would modify historical articles (id <= repo_max_numeric_id).",
                        "site_id": site.get("id"),
                        "repo_max_numeric_id": repo_max,
                        "unsafe_count": len(unsafe),
                        "unsafe_sample": unsafe[:10],
                        "preview": preview,
                    }

        articles_path = self.get_articles_path(site)
        if not articles_path:
            return {"ok": False, "error": "Missing site.articles"}

        doc = load_json_file(articles_path)
        articles = list(doc.get("articles", []) or [])
        by_id: dict[int, dict[str, Any]] = {}
        for a in articles:
            try:
                by_id[int(a.get("id"))] = a
            except Exception:
                continue

        content_dir = self.get_automation_content_dir(site)
        file_results = []

        # Phase A: Apply any schedule date changes to articles.json + frontmatter.
        for item in schedule:
            try:
                aid = int(item["id"])
            except Exception:
                continue
            target = by_id.get(aid)
            if not target:
                continue

            new_date = item["to"]
            target["published_date"] = new_date

            if content_dir and target.get("file"):
                rel = str(target["file"]).lstrip("./")
                p = (content_dir.parent / rel).resolve()
                if p.exists():
                    res = update_frontmatter_date(p, new_date)
                    file_results.append({"id": aid, "file": str(p), **res})
                else:
                    file_results.append({"id": aid, "file": str(p), "ok": False, "error": "File not found"})

        # Phase B: Sync frontmatter dates for ALL mutable articles (even if
        # articles.json didn't change).  This catches cases where a previous
        # schedule-apply updated articles.json but the MDX frontmatter still
        # has the old date.
        already_synced = {r["id"] for r in file_results if r.get("ok")}
        mutable, _ctx = self.compute_mutable_articles(site, status_filter=status_filter or None)
        frontmatter_sync_results = []
        if content_dir:
            for a in mutable:
                try:
                    aid = int(a.get("id") or 0)
                except Exception:
                    continue
                if aid in already_synced:
                    continue
                expected_date = str(a.get("published_date") or "").strip()
                if not expected_date:
                    continue
                file_ref = str(a.get("file") or "")
                if not file_ref:
                    continue
                rel = file_ref.lstrip("./")
                p = (content_dir.parent / rel).resolve()
                if not p.exists():
                    continue
                # Check current frontmatter date
                try:
                    text = p.read_text(encoding="utf-8")
                except Exception:
                    continue
                import re as _re
                fm_date_match = _re.search(r'^date:\s*"([^"]+)"', text, _re.MULTILINE)
                current_date = fm_date_match.group(1) if fm_date_match else None
                if current_date == expected_date:
                    continue
                # Frontmatter out of sync — fix it
                res = update_frontmatter_date(p, expected_date)
                frontmatter_sync_results.append({
                    "id": aid, "file": str(p),
                    "from": current_date, "to": expected_date, **res,
                })

        if schedule or frontmatter_sync_results:
            doc["articles"] = articles
            articles_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        preview["applied"] = True
        preview["file_updates"] = file_results
        preview["frontmatter_synced"] = frontmatter_sync_results
        return preview

    def build_overview_markdown_report(self, sites: list[dict[str, Any]] | None = None) -> str:
        today = datetime.now().date().isoformat()
        websites = sites if sites is not None else self.load_websites_registry()
        metrics = [self.compute_site_metrics(w) for w in websites]

        lines: list[str] = []
        lines.append("# SEO Overview Report")
        lines.append("")
        lines.append(f"- Generated: {today}")
        lines.append(f"- Websites: {len(metrics)}")
        lines.append("")

        lines.append("## Sites")
        lines.append("")
        lines.append("| Site | Articles | Published | Drafts | Latest published | Issues |")
        lines.append("|---|---:|---:|---:|---|---:|")

        for m in metrics:
            issue_count = int(m.get("future_dates") or 0) + int(m.get("bad_dates") or 0) + int(m.get("missing_dates") or 0) + int(m.get("missing_slugs") or 0) + int(m.get("duplicate_slugs") or 0) + int(m.get("missing_files") or 0)
            site_name = m.get("name") or m.get("id")
            lines.append(
                f"| {site_name} ({m.get('id')}) | {m.get('total')} | {m.get('published')} | {m.get('drafts')} | {m.get('latest_published_date') or '—'} | {issue_count} |"
            )

        lines.append("")
        lines.append("## How to use")
        lines.append("")
        lines.append("- Get overview JSON: `seo_ops_overview`")
        lines.append("- Get site report markdown: `seo_ops_report_site_markdown`")
        lines.append("- Include drift (slower): `include_drift=true`")

        return "\n".join(lines) + "\n"

    def build_site_markdown_report(
        self,
        site: dict[str, Any],
        *,
        include_drift: bool = False,
        include_dates: bool = True,
        include_schedule_preview: bool = True,
        spacing_days: int = 2,
        max_items: int = 25,
    ) -> str:
        metrics = self.compute_site_metrics(site)
        articles = self.load_site_articles(site)

        today = datetime.now().date().isoformat()
        lines: list[str] = []
        lines.append(f"# SEO Report: {metrics.get('name') or metrics.get('id')}")
        lines.append("")
        lines.append(f"- Generated: {today}")
        lines.append(f"- Site ID: {metrics.get('id')}")
        lines.append(f"- Automation path: {_md_code(metrics.get('path'))}")
        lines.append(f"- Automation index: {_md_code(metrics.get('articles_path'))}")
        if metrics.get("source_repo_local_path"):
            lines.append(f"- Source repo (local): {_md_code(metrics.get('source_repo_local_path'))}")
        if metrics.get("source_content_dir"):
            lines.append(f"- Source content dir: {_md_code(metrics.get('source_content_dir'))}")

        lines.append("")
        lines.append("## Summary")
        lines.append("")
        lines.append(f"- Articles: {metrics.get('total')} (published: {metrics.get('published')}, draft/staged: {metrics.get('drafts')})")
        lines.append(f"- Latest published date (from index): {metrics.get('latest_published_date') or '—'}")
        lines.append(
            "- Issues: "
            f"future dates={metrics.get('future_dates')}, "
            f"missing dates={metrics.get('missing_dates')}, "
            f"bad dates={metrics.get('bad_dates')}, "
            f"missing slugs={metrics.get('missing_slugs')}, "
            f"dup slugs={metrics.get('duplicate_slugs')}, "
            f"missing files={metrics.get('missing_files')}"
        )

        if include_dates:
            analysis = self.analyze_site_dates(site)
            issues = analysis.get("issues", {})

            lines.append("")
            lines.append("## Date issues")
            lines.append("")

            future_ids = issues.get("future", []) or []
            missing_ids = issues.get("missing", []) or []
            bad_ids = issues.get("bad", []) or []
            overlaps = issues.get("overlaps", []) or []

            by_id = {str(a.get("id")): a for a in articles}

            lines.append(f"- Future dated articles: {len(future_ids)}")
            for aid in future_ids[:max_items]:
                a = by_id.get(str(aid))
                if not a:
                    continue
                lines.append(
                    f"  - {a.get('published_date') or '—'} · {a.get('title') or '—'} · {_md_code(a.get('file') or '—')}"
                )

            lines.append(f"- Missing dates: {len(missing_ids)}")
            for aid in missing_ids[:max_items]:
                a = by_id.get(str(aid))
                if not a:
                    continue
                lines.append(f"  - {a.get('title') or '—'} · {_md_code(a.get('file') or '—')}")

            lines.append(f"- Bad dates: {len(bad_ids)}")
            for aid in bad_ids[:max_items]:
                a = by_id.get(str(aid))
                if not a:
                    continue
                lines.append(
                    f"  - {a.get('published_date') or '—'} · {a.get('title') or '—'} · {_md_code(a.get('file') or '—')}"
                )

            lines.append(f"- Overlapping dates: {len(overlaps)}")
            for o in overlaps[:max_items]:
                lines.append(f"  - {o.get('date')}: {o.get('ids')}")

        if include_schedule_preview:
            preview = self.preview_date_schedule(site, spacing_days=spacing_days, statuses=["ready_to_publish"])
            lines.append("")
            lines.append("## Draft scheduling preview")
            lines.append("")
            lines.append(f"- Spacing days: {preview.get('spacing_days')}")
            lines.append(f"- Anchor: {preview.get('anchor')}")
            lines.append(f"- Mode: {preview.get('mode')}")
            lines.append(f"- Mutable count: {preview.get('context', {}).get('mutable_count')}")

            schedule = preview.get("schedule", []) or []
            if schedule:
                lines.append("")
                lines.append("### Proposed date updates")
                lines.append("")
                for item in schedule[:max_items]:
                    lines.append(
                        f"- {item.get('id')}: {item.get('from') or '—'} → {item.get('to')} · {item.get('title') or '—'} · {_md_code(item.get('file') or '—')}"
                    )
                if len(schedule) > max_items:
                    lines.append(f"- … ({len(schedule) - max_items} more)")
            else:
                lines.append("")
                lines.append("- No mutable articles to schedule.")

        if include_drift:
            drift = self.compute_repo_drift(site)
            lines.append("")
            lines.append("## Drift (automation vs repo)")
            lines.append("")
            if not drift.get("ok"):
                lines.append(f"- Error: {drift.get('error')}")
            else:
                lines.append(f"- Missing in repo: {len(drift.get('missing_in_repo') or [])}")
                lines.append(f"- Missing in automation: {len(drift.get('missing_in_automation') or [])}")
                lines.append(f"- Content mismatches: {len(drift.get('mismatches') or [])}")

                mismatches = drift.get("mismatches") or []
                if mismatches:
                    lines.append("")
                    lines.append("### Mismatched files")
                    lines.append("")
                    for m in mismatches[:max_items]:
                        lines.append(f"- {m.get('file')} · repo={_md_code(m.get('repo_path'))} · auto={_md_code(m.get('automation_path'))}")
                    if len(mismatches) > max_items:
                        lines.append(f"- … ({len(mismatches) - max_items} more)")

        lines.append("")
        lines.append("## Suggested actions")
        lines.append("")
        lines.append("- If drift is high: run import preview/apply (updates automation index only).")
        lines.append("- If dates are missing/future for drafts: run schedule preview/apply (updates automation index + automation content frontmatter).")
        lines.append("- If repo content is canonical: treat repo-present files as immutable.")

        return "\n".join(lines) + "\n"

    def sync_and_optimize(
        self,
        site: dict[str, Any],
        auto_fix: bool = False,
        spacing_days: int = 2,
        max_recent_days: int = 14,
        dry_run: bool = True,
        auto_deploy: bool = False,
        target_statuses: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Unified workflow: sync from production, analyze dates, fix issues, check drift, validate, deploy.
        
        This orchestrates the full content management workflow:
        1. Import from production repo (sync dates/metadata)
        2. Analyze dates for issues
        3. Fix dates if auto_fix enabled
        4. Check drift between automation and production
        5. Validate content
        6. Deploy to production if auto_deploy enabled
        
        Args:
            site: Website configuration from registry
            auto_fix: If True and dry_run=False, actually apply date fixes
            spacing_days: Days to space between redistributed articles
            max_recent_days: Only fix articles created in last N days
            dry_run: Safety check - if True, no changes are made even if auto_fix=True
            auto_deploy: If True and dry_run=False, copy files to production repo
            
        Returns:
            Structured result with all phase outputs and recommendations
        """
        website_id = site.get("id", "unknown")
        timestamp = datetime.now().isoformat() + "Z"
        mode = "preview" if (dry_run or not auto_fix) else "apply"
        
        phases = {}
        summary = {
            "articles_in_sync": False,
            "date_issues_found": 0,
            "files_ready_to_push": 0,
            "validation_errors": 0,
            "next_action": ""
        }
        recommended_actions = []

        status_filter = {str(s).strip().lower() for s in (target_statuses or []) if str(s).strip()}
        if not status_filter:
            status_filter = {"ready_to_publish"}
        
        # Phase 1: Import & Sync from Production
        try:
            if dry_run or not auto_fix:
                import_result = self.preview_import_from_repo(site)
                changes = import_result.get("changes", {})
                imported_articles = len(changes.get("updated", [])) + len(changes.get("new", []))
                new_articles = len(changes.get("new", []))
                updated_dates = sum(1 for u in changes.get("updated", []) 
                                  if "published_date" in u.get("updates", {}))
                
                phases["import_sync"] = {
                    "phase": "import_sync",
                    "status": "preview" if dry_run else "skipped",
                    "reason": "preview_mode" if dry_run else "auto_fix_disabled",
                    "would_import": imported_articles,
                    "new_articles": new_articles,
                    "updated_dates": updated_dates
                }
                summary["articles_in_sync"] = imported_articles == 0
            else:
                import_result = self.apply_import_from_repo(site)
                changes = import_result.get("changes", {})
                imported_articles = len(changes.get("updated", [])) + len(changes.get("new", []))
                
                phases["import_sync"] = {
                    "phase": "import_sync",
                    "status": "completed",
                    "imported_articles": imported_articles,
                    "new_articles": len(changes.get("new", [])),
                    "updated_dates": sum(1 for u in changes.get("updated", []) 
                                       if "published_date" in u.get("updates", {})),
                    "files_updated": [str(self.get_articles_path(site))]
                }
                summary["articles_in_sync"] = True
                
        except Exception as e:
            phases["import_sync"] = {
                "phase": "import_sync",
                "status": "error",
                "error": str(e)
            }
            return {
                "ok": False,
                "mode": mode,
                "website_id": website_id,
                "timestamp": timestamp,
                "error": {
                    "phase": "import_sync",
                    "type": "sync_failed",
                    "message": str(e),
                    "suggestions": [
                        "Check WEBSITES_REGISTRY.json has correct source_repo_local_path",
                        "Verify production repository exists on filesystem",
                        f"Ensure {site.get('source_repo_local_path')} is accessible"
                    ]
                }
            }
        
        # Phase 2: Date Analysis
        try:
            dates_analysis = self.analyze_site_dates(site)
            issues = dates_analysis.get("issues", {})
            future_count = len(issues.get("future", []))
            overlaps = issues.get("overlaps", [])
            missing_count = len(issues.get("missing", []))

            # Compute mutable count using the same status filter used for scheduling.
            mutable, _mutable_ctx = self.compute_mutable_articles(site, status_filter=status_filter)
            total_articles = int(dates_analysis.get("total") or len(self.load_site_articles(site)))
            by_id = {}
            for a in self.load_site_articles(site):
                try:
                    by_id[int(a.get("id") or 0)] = a
                except Exception:
                    continue
            
            phases["date_analysis"] = {
                "phase": "date_analysis",
                "status": "completed",
                "total_articles": total_articles,
                "mutable_articles": len(mutable),
                "immutable_articles": max(0, total_articles - len(mutable)),
                "target_statuses": sorted(status_filter),
                "issues": {
                    "future_dates": [
                        {"id": aid, "date": (by_id.get(int(aid)) or {}).get("published_date")}
                        for aid in (issues.get("future", []) or [])
                    ],
                    "overlapping_dates": [{"date": o.get("date"), "article_ids": o.get("ids")} 
                                         for o in overlaps],
                    "missing_dates": missing_count,
                    "poor_distribution": len(mutable) > 0
                }
            }
            
            summary["date_issues_found"] = future_count + len(overlaps) + missing_count
            
            if summary["date_issues_found"] > 0:
                recommended_actions.append(f"Found {summary['date_issues_found']} date issues - review before applying fixes")
                
        except Exception as e:
            phases["date_analysis"] = {
                "phase": "date_analysis",
                "status": "error",
                "error": str(e)
            }
        
        # Phase 3: Date Optimization (Conditional)
        try:
            mutable_count = phases.get("date_analysis", {}).get("mutable_articles", 0)
            
            if dry_run or not auto_fix:
                schedule_preview = self.preview_date_schedule(
                    site,
                    spacing_days=spacing_days,
                    statuses=sorted(status_filter),
                )
                phases["date_optimization"] = {
                    "phase": "date_optimization",
                    "status": "skipped",
                    "reason": "preview_mode" if dry_run else "auto_fix_disabled",
                    "would_fix": len(schedule_preview.get("schedule", []))
                }
                
                if mutable_count > 0:
                    recommended_actions.append("Run with auto_fix: true to apply date redistribution")
            else:
                if mutable_count > 0:
                    schedule_result = self.apply_date_schedule(
                        site,
                        spacing_days=spacing_days,
                        statuses=sorted(status_filter),
                    )
                    schedule = schedule_result.get("schedule", [])
                    
                    files_updated = [str(self.get_articles_path(site))]
                    # Add content files that were updated
                    automation_content = self.get_automation_content_dir(site)
                    if automation_content:
                        for item in schedule:
                            file_ref = item.get("file", "")
                            if file_ref:
                                file_path = automation_content / Path(file_ref).name
                                if file_path.exists():
                                    files_updated.append(str(file_path))
                    
                    phases["date_optimization"] = {
                        "phase": "date_optimization",
                        "status": "completed",
                        "articles_redistributed": len(schedule),
                        "date_range": {
                            "start": schedule[0].get("to") if schedule else None,
                            "end": schedule[-1].get("to") if schedule else None,
                            "span_days": spacing_days * len(schedule) if schedule else 0
                        },
                        "changes": [
                            {"id": item.get("id"), "old_date": item.get("from"), "new_date": item.get("to")}
                            for item in schedule
                        ],
                        "files_updated": files_updated
                    }
                else:
                    phases["date_optimization"] = {
                        "phase": "date_optimization",
                        "status": "skipped",
                        "reason": "no_mutable_articles"
                    }
                    
        except Exception as e:
            phases["date_optimization"] = {
                "phase": "date_optimization",
                "status": "error",
                "error": str(e)
            }
        
        # Phase 4: Drift Check
        try:
            drift = self.compute_repo_drift(site)
            
            if drift.get("ok"):
                missing_in_repo = drift.get("missing_in_repo", [])
                mismatched = drift.get("mismatches", [])
                mismatched_files = [m.get("file") for m in mismatched if m.get("file")]
                files_to_push = list(missing_in_repo)

                # Only deploy/surface files tied to target statuses.
                eligible_basenames: set[str] = set()
                for a in self.load_site_articles(site):
                    st = (a.get("status") or "").strip().lower()
                    if st not in status_filter:
                        continue
                    bn = Path(str(a.get("file") or "")).name
                    if bn:
                        eligible_basenames.add(bn)

                deploy_candidates = [f for f in files_to_push if f in eligible_basenames]

                # Also include mismatched files that belong to the target
                # statuses.  After date optimisation the automation copy has
                # updated frontmatter; those files need to be re-pushed.
                eligible_mismatched = [f for f in mismatched_files if f in eligible_basenames and f not in deploy_candidates]
                deploy_candidates.extend(eligible_mismatched)
                
                phases["drift_check"] = {
                    "phase": "drift_check",
                    "status": "completed",
                    "automation_files": drift.get("automation_files", 0),
                    "production_files": drift.get("repo_files", 0),
                    "missing_in_repo": missing_in_repo,
                    "files_to_push": deploy_candidates,
                    "files_to_push_filtered_by_status": True,
                    "target_statuses": sorted(status_filter),
                    "mismatched_files": mismatched_files,
                    "mismatched_eligible_for_deploy": eligible_mismatched,
                }
                
                summary["missing_in_repo_total"] = len(missing_in_repo)
                summary["files_ready_to_push"] = len(deploy_candidates)
                summary["files_mismatched"] = len(mismatched_files)
                
                if deploy_candidates:
                    recommended_actions.append(
                        f"Push {len(deploy_candidates)} ready files to production after review (missing in production)"
                    )
                elif missing_in_repo:
                    recommended_actions.append(
                        f"There are {len(missing_in_repo)} files missing in production, but none match target_statuses={sorted(status_filter)}"
                    )
                if mismatched_files:
                    recommended_actions.append(
                        f"Review {len(mismatched_files)} mismatched production files (NOT auto-deployed by default)"
                    )
            else:
                phases["drift_check"] = {
                    "phase": "drift_check",
                    "status": "error",
                    "error": drift.get("error", "Unknown drift error")
                }
                
        except Exception as e:
            phases["drift_check"] = {
                "phase": "drift_check",
                "status": "error",
                "error": str(e)
            }
        
        # Phase 5: Validation
        try:
            articles = self.load_site_articles(site)
            validation_errors = []
            validation_warnings = []
            
            for article in articles:
                # Check for required fields
                if not article.get("title"):
                    validation_errors.append({
                        "id": article.get("id"),
                        "error": "Missing title"
                    })
                if not article.get("target_keyword"):
                    validation_warnings.append({
                        "id": article.get("id"),
                        "warning": "Missing target_keyword"
                    })
                if not article.get("estimated_traffic_monthly"):
                    validation_warnings.append({
                        "id": article.get("id"),
                        "warning": "Missing estimated_traffic_monthly"
                    })
            
            phases["validation"] = {
                "phase": "validation",
                "status": "completed",
                "articles_validated": len(articles),
                "errors": validation_errors,
                "warnings": validation_warnings[:10]  # Limit warnings
            }
            
            summary["validation_errors"] = len(validation_errors)
            
            if validation_errors:
                recommended_actions.append(f"Fix {len(validation_errors)} validation errors before deployment")
                
        except Exception as e:
            phases["validation"] = {
                "phase": "validation",
                "status": "error",
                "error": str(e)
            }
        
        # Determine next action
        if dry_run:
            summary["next_action"] = "Run with dry_run: false to apply changes"
        elif not auto_fix:
            summary["next_action"] = "Run with auto_fix: true to fix date issues"
        elif auto_deploy and summary["files_ready_to_push"] > 0:
            summary["next_action"] = "Files will be deployed to production"
        elif summary["files_ready_to_push"] > 0:
            summary["next_action"] = "Run with auto_deploy: true to copy files to production"
        elif summary.get("files_mismatched", 0) > 0:
            summary["next_action"] = "Review mismatched production files before any overwrite"
        else:
            summary["next_action"] = "All in sync - no action needed"
        
        # Phase 6: Auto-Deploy (Conditional)
        if auto_deploy and not dry_run and summary["files_ready_to_push"] > 0:
            try:
                automation_content = self.get_automation_content_dir(site)
                repo_content = self.get_repo_content_dir(site)
                
                if not automation_content or not repo_content:
                    phases["deployment"] = {
                        "phase": "deployment",
                        "status": "error",
                        "error": "Cannot determine content directories for deployment"
                    }
                elif not automation_content.exists():
                    phases["deployment"] = {
                        "phase": "deployment",
                        "status": "error",
                        "error": f"Automation content directory does not exist: {automation_content}"
                    }
                elif not repo_content.exists():
                    phases["deployment"] = {
                        "phase": "deployment",
                        "status": "error",
                        "error": f"Production content directory does not exist: {repo_content}"
                    }
                else:
                    # Get files to deploy
                    files_to_push = phases.get("drift_check", {}).get("files_to_push", [])
                    all_files = list(files_to_push)
                    
                    copied_files = []
                    failed_files = []
                    
                    for filename in all_files:
                        source_file = automation_content / filename
                        target_file = repo_content / filename
                        
                        try:
                            if not source_file.exists():
                                failed_files.append({
                                    "file": filename,
                                    "error": "Source file not found"
                                })
                                continue
                            
                            # Copy the file
                            import shutil
                            shutil.copy2(source_file, target_file)
                            copied_files.append(filename)
                            
                        except Exception as e:
                            failed_files.append({
                                "file": filename,
                                "error": str(e)
                            })
                    
                    phases["deployment"] = {
                        "phase": "deployment",
                        "status": "completed",
                        "files_copied": len(copied_files),
                        "files_failed": len(failed_files),
                        "copied": copied_files,
                        "failed": failed_files,
                        "target_dir": str(repo_content)
                    }
                    
                    summary["files_deployed"] = len(copied_files)
                    summary["next_action"] = f"Deployed {len(copied_files)} files to production"
                    
                    if failed_files:
                        recommended_actions.append(f"Review {len(failed_files)} failed deployments")
                    else:
                        recommended_actions.append("All files successfully deployed to production")
                        
            except Exception as e:
                phases["deployment"] = {
                    "phase": "deployment",
                    "status": "error",
                    "error": str(e)
                }
        elif auto_deploy and not dry_run:
            phases["deployment"] = {
                "phase": "deployment",
                "status": "skipped",
                "reason": "no_files_to_deploy"
            }
        elif auto_deploy:
            phases["deployment"] = {
                "phase": "deployment",
                "status": "skipped",
                "reason": "dry_run_enabled"
            }
        
        # Build result
        result = {
            "ok": True,
            "mode": mode,
            "website_id": website_id,
            "timestamp": timestamp,
            "phases": phases,
            "summary": summary,
            "recommended_actions": recommended_actions
        }
        
        # Add deployment instructions if in apply mode and files to push (and not auto-deployed)
        if mode == "apply" and summary["files_ready_to_push"] > 0 and not auto_deploy:
            automation_content = self.get_automation_content_dir(site)
            repo_content = self.get_repo_content_dir(site)
            
            if automation_content and repo_content:
                files_to_push = phases.get("drift_check", {}).get("files_to_push", [])
                all_files = list(files_to_push)
                
                result["deployment_instructions"] = {
                    "source_dir": str(automation_content),
                    "target_dir": str(repo_content),
                    "files_to_copy": all_files,
                    "command": f"cp [source_dir]/[file] [target_dir]/[file]"
                }
        
        return result

    def sync_and_validate(
        self,
        site: dict[str, Any],
        *,
        apply_sync: bool = False,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        """Run a focused workflow: sync index metadata + validate index/file gaps.

        This intentionally excludes scheduling, optimization, and deployment.
        """
        website_id = site.get("id", "unknown")
        timestamp = datetime.now().isoformat() + "Z"
        mode = "apply" if (apply_sync and not dry_run) else "preview"

        phases: dict[str, Any] = {}
        summary: dict[str, Any] = {
            "articles_imported": 0,
            "new_articles": 0,
            "updated_articles": 0,
            "checked_entries": 0,
            "missing_everywhere": 0,
            "missing_in_repo": 0,
            "missing_in_automation": 0,
            "mismatched_files": 0,
            "next_action": "",
        }
        recommended_actions: list[str] = []

        # Phase 1: Sync automation articles index from production metadata.
        try:
            if mode == "apply":
                import_result = self.apply_import_from_repo(site)
            else:
                import_result = self.preview_import_from_repo(site)

            changes = import_result.get("changes", {})
            imported = len(changes.get("updated", [])) + len(changes.get("new", []))
            new_articles = len(changes.get("new", []))
            updated_articles = len(changes.get("updated", []))

            phases["import_sync"] = {
                "phase": "import_sync",
                "status": "completed",
                "mode": mode,
                "imported_articles": imported,
                "new_articles": new_articles,
                "updated_articles": updated_articles,
                "applied": mode == "apply",
            }
            summary["articles_imported"] = imported
            summary["new_articles"] = new_articles
            summary["updated_articles"] = updated_articles
        except Exception as e:
            phases["import_sync"] = {
                "phase": "import_sync",
                "status": "error",
                "mode": mode,
                "error": str(e),
            }
            return {
                "ok": False,
                "mode": mode,
                "website_id": website_id,
                "timestamp": timestamp,
                "phases": phases,
                "summary": summary,
                "error": {
                    "phase": "import_sync",
                    "type": "sync_failed",
                    "message": str(e),
                },
                "recommended_actions": [
                    "Check WEBSITES_REGISTRY.json source repo paths",
                    "Verify source_repo_local_path and source_content_dir are accessible",
                ],
            }

        # Phase 2: Validate index entries against both automation + production files.
        try:
            index_validation = self.validate_site_index(site)
            index_summary = index_validation.get("summary", {})
            checked = int(index_validation.get("checked") or 0)
            missing_everywhere = int(index_summary.get("missing_everywhere") or 0)

            phases["index_validation"] = {
                "phase": "index_validation",
                "status": "completed",
                "checked": checked,
                "summary": index_summary,
            }
            summary["checked_entries"] = checked
            summary["missing_everywhere"] = missing_everywhere

            if missing_everywhere > 0:
                recommended_actions.append(
                    f"Fix {missing_everywhere} articles.json entries that are missing in both automation and production"
                )
        except Exception as e:
            phases["index_validation"] = {
                "phase": "index_validation",
                "status": "error",
                "error": str(e),
            }

        # Phase 3: Drift between automation files and production files.
        try:
            drift = self.compute_repo_drift(site)
            if drift.get("ok"):
                missing_in_repo = len(drift.get("missing_in_repo", []))
                missing_in_automation = len(drift.get("missing_in_automation", []))
                mismatched_files = len(drift.get("mismatches", []))

                phases["drift_check"] = {
                    "phase": "drift_check",
                    "status": "completed",
                    "automation_files": drift.get("automation_files", 0),
                    "production_files": drift.get("repo_files", 0),
                    "missing_in_repo": drift.get("missing_in_repo", []),
                    "missing_in_automation": drift.get("missing_in_automation", []),
                    "mismatches": drift.get("mismatches", []),
                }
                summary["missing_in_repo"] = missing_in_repo
                summary["missing_in_automation"] = missing_in_automation
                summary["mismatched_files"] = mismatched_files

                if missing_in_repo > 0:
                    recommended_actions.append(
                        f"{missing_in_repo} files exist only in automation and may need deployment"
                    )
                if missing_in_automation > 0:
                    recommended_actions.append(
                        f"{missing_in_automation} files exist only in production and should be pulled into automation"
                    )
                if mismatched_files > 0:
                    recommended_actions.append(
                        f"Review {mismatched_files} file mismatches between automation and production"
                    )
            else:
                phases["drift_check"] = {
                    "phase": "drift_check",
                    "status": "error",
                    "error": drift.get("error", "Unknown drift error"),
                }
        except Exception as e:
            phases["drift_check"] = {
                "phase": "drift_check",
                "status": "error",
                "error": str(e),
            }

        if mode == "preview":
            summary["next_action"] = "Run with --apply-sync --dry-run false to write sync changes"
        elif summary["missing_everywhere"] > 0:
            summary["next_action"] = "Fix missing index entries before any publish/deploy workflow"
        elif summary["missing_in_automation"] > 0:
            summary["next_action"] = "Run pull-from-repo to align automation files"
        elif summary["missing_in_repo"] > 0 or summary["mismatched_files"] > 0:
            summary["next_action"] = "Review deployment candidates and mismatches"
        else:
            summary["next_action"] = "Index and content files are in sync"

        return {
            "ok": True,
            "mode": mode,
            "website_id": website_id,
            "timestamp": timestamp,
            "phases": phases,
            "summary": summary,
            "recommended_actions": recommended_actions,
        }
