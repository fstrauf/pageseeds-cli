"""Clustering & internal linking helpers for SEO Step 3.

Provides pure-function logic consumed by both the CLI and the MCP server.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class InternalLink:
    """A single internal link found in a content file."""
    source_id: int
    source_file: str
    target_file: str
    target_id: int | None  # None if target could not be resolved
    anchor_text: str
    line_number: int
    in_related_section: bool = False


@dataclass
class ArticleLinkProfile:
    """Link profile for a single article."""
    id: int
    title: str
    file: str
    outgoing_ids: list[int] = field(default_factory=list)
    incoming_ids: list[int] = field(default_factory=list)
    outgoing_links: list[dict[str, Any]] = field(default_factory=list)
    unresolved_links: list[str] = field(default_factory=list)


@dataclass
class LinkScanResult:
    """Result of scanning all content files for internal links."""
    website_path: str
    total_articles: int
    total_internal_links: int
    articles_with_outgoing: int
    articles_with_incoming: int
    orphan_articles: list[int]  # no incoming or outgoing
    profiles: list[ArticleLinkProfile] = field(default_factory=list)


@dataclass
class LinkingPlanItem:
    """A single planned link between two articles."""
    source_id: int
    source_title: str
    source_file: str
    target_id: int
    target_title: str
    target_file: str
    link_type: str  # hub-to-spoke, spoke-to-hub, cross-cluster
    already_exists: bool = False


@dataclass
class LinkingPlan:
    """Complete linking plan across all clusters."""
    website_path: str
    total_planned: int
    already_linked: int
    missing_links: int
    items: list[LinkingPlanItem] = field(default_factory=list)


@dataclass
class AddLinksResult:
    """Result of adding internal links to an article."""
    source_id: int
    source_file: str
    links_added: list[dict[str, Any]]
    links_skipped: list[dict[str, Any]]  # already existed
    mode: str  # related-section | inline


@dataclass
class BriefUpdateResult:
    """Result of updating the brief linking checklist."""
    brief_path: str
    items_checked: int  # ☐ → ✅
    items_already_done: int
    items_still_pending: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_file_to_id_map(articles: list[dict[str, Any]]) -> dict[str, int]:
    """Map content file basenames to article IDs."""
    m: dict[str, int] = {}
    for a in articles:
        f = str(a.get("file") or "").strip()
        if f:
            basename = Path(f).name
            m[basename] = int(a.get("id") or 0)
    return m


def _build_slug_to_id_map(articles: list[dict[str, Any]]) -> dict[str, int]:
    """Map url_slug values to article IDs."""
    m: dict[str, int] = {}
    for a in articles:
        slug = str(a.get("url_slug") or "").strip()
        if slug:
            m[slug] = int(a.get("id") or 0)
    return m


def _build_id_to_article_map(articles: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """Map article IDs to their full article dicts."""
    return {int(a["id"]): a for a in articles if a.get("id") is not None}


def _extract_internal_links(
    text: str,
    source_id: int,
    source_file: str,
    file_to_id: dict[str, int],
    slug_to_id: dict[str, int] | None = None,
) -> tuple[list[InternalLink], list[str]]:
    """Extract all internal links from MDX content text.

    Returns (resolved_links, unresolved_target_files).
    Recognizes both canonical URLs (/blog/slug/) and legacy relative paths (./filename.mdx).
    """
    links: list[InternalLink] = []
    unresolved: list[str] = []

    # Track whether we're in a "Related Articles" section
    in_related = False
    for lineno, line in enumerate(text.splitlines(), 1):
        # Detect "Related Articles" heading
        if re.match(r"^#{1,4}\s+Related\s+Articles", line, re.IGNORECASE):
            in_related = True
            continue
        # Reset if we hit another heading (except sub-items)
        if in_related and re.match(r"^#{1,3}\s+[^R]", line):
            in_related = False

        # Pattern 1: Canonical URLs /blog/slug/ (RECOMMENDED)
        for match in re.finditer(r"\[([^\]]+)\]\(/blog/([^/)]+)/?\)", line):
            anchor = match.group(1)
            target_slug = match.group(2)
            target_id = slug_to_id.get(target_slug) if slug_to_id else None
            # Fallback: try to find by filename pattern if slug mapping fails
            if target_id is None:
                # Try to match slug against url_slug field in articles
                for basename, aid in file_to_id.items():
                    # Derive slug from filename
                    derived_slug = basename.replace(".mdx", "").replace(".md", "")
                    derived_slug = re.sub(r"^\d+_", "", derived_slug)
                    if derived_slug == target_slug:
                        target_id = aid
                        break
            if target_id is not None:
                links.append(InternalLink(
                    source_id=source_id,
                    source_file=source_file,
                    target_file=f"/blog/{target_slug}/",
                    target_id=target_id,
                    anchor_text=anchor,
                    line_number=lineno,
                    in_related_section=in_related,
                ))
            else:
                unresolved.append(f"/blog/{target_slug}/")

        # Pattern 2: Legacy relative paths ./filename.mdx (DEPRECATED but supported)
        for match in re.finditer(r"\[([^\]]+)\]\(\.\/([^)]+\.mdx)\)", line):
            anchor = match.group(1)
            target_path = match.group(2)
            target_basename = Path(target_path).name
            target_id = file_to_id.get(target_basename)
            if target_id is not None:
                links.append(InternalLink(
                    source_id=source_id,
                    source_file=source_file,
                    target_file=target_path,
                    target_id=target_id,
                    anchor_text=anchor,
                    line_number=lineno,
                    in_related_section=in_related,
                ))
            else:
                unresolved.append(target_path)

    return links, unresolved


# ---------------------------------------------------------------------------
# scan_internal_links
# ---------------------------------------------------------------------------

def scan_internal_links(
    workspace_root: str,
    website_path: str,
) -> LinkScanResult:
    """Scan all content files and build the internal link graph."""
    base = Path(workspace_root) / website_path
    articles_path = base / "articles.json"
    if not articles_path.exists():
        raise FileNotFoundError(f"articles.json not found: {articles_path}")

    with articles_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    articles = [a for a in data.get("articles", []) if isinstance(a, dict)]
    file_to_id = _build_file_to_id_map(articles)
    slug_to_id = _build_slug_to_id_map(articles)
    id_to_article = _build_id_to_article_map(articles)

    profiles: dict[int, ArticleLinkProfile] = {}
    for a in articles:
        aid = int(a.get("id") or 0)
        profiles[aid] = ArticleLinkProfile(
            id=aid,
            title=str(a.get("title") or ""),
            file=str(a.get("file") or ""),
        )

    # Scan content files
    total_links = 0
    for a in articles:
        aid = int(a.get("id") or 0)
        file_ref = str(a.get("file") or "").strip()
        if not file_ref:
            continue
        content_path = base / file_ref.lstrip("./")
        if not content_path.exists():
            continue
        text = content_path.read_text(encoding="utf-8")
        links, unresolved = _extract_internal_links(text, aid, file_ref, file_to_id, slug_to_id)
        total_links += len(links)
        profile = profiles[aid]
        profile.unresolved_links = unresolved
        for link in links:
            if link.target_id is not None:
                if link.target_id not in profile.outgoing_ids:
                    profile.outgoing_ids.append(link.target_id)
                profile.outgoing_links.append({
                    "target_id": link.target_id,
                    "target_file": link.target_file,
                    "anchor_text": link.anchor_text,
                    "line": link.line_number,
                    "in_related_section": link.in_related_section,
                })
                # Update incoming on target
                if link.target_id in profiles:
                    if aid not in profiles[link.target_id].incoming_ids:
                        profiles[link.target_id].incoming_ids.append(aid)

    orphans = [
        p.id for p in profiles.values()
        if not p.outgoing_ids and not p.incoming_ids and p.file
    ]

    return LinkScanResult(
        website_path=website_path,
        total_articles=len(articles),
        total_internal_links=total_links,
        articles_with_outgoing=sum(1 for p in profiles.values() if p.outgoing_ids),
        articles_with_incoming=sum(1 for p in profiles.values() if p.incoming_ids),
        orphan_articles=sorted(orphans),
        profiles=sorted(profiles.values(), key=lambda p: p.id),
    )


# ---------------------------------------------------------------------------
# generate_linking_plan
# ---------------------------------------------------------------------------

def _parse_clusters_from_brief(brief_text: str, articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Parse cluster definitions from a content brief markdown.

    Expected format in the brief:
    ### Cluster N: Name ...
    **Pillar Article:**
    - **"Title"** (ID: N)
    **Support Articles:**
    | ... (ID: N) ...
    """
    id_to_article = _build_id_to_article_map(articles)
    clusters: list[dict[str, Any]] = []
    current_cluster: dict[str, Any] | None = None
    in_support_table = False

    for line in brief_text.splitlines():
        # Cluster heading
        m = re.match(r"^###\s+Cluster\s+(\d+):\s+(.+?)(?:\s*⭐.*)?$", line)
        if m:
            if current_cluster:
                clusters.append(current_cluster)
            current_cluster = {
                "cluster_id": int(m.group(1)),
                "name": m.group(2).strip(),
                "pillar_id": None,
                "support_ids": [],
            }
            in_support_table = False
            continue

        if current_cluster is None:
            continue

        # Pillar article line: - **"Title"** (ID: N)
        pm = re.search(r"\(ID:\s*(\d+)\)", line)
        if pm and "Pillar Article" not in line:
            aid = int(pm.group(1))
            if current_cluster["pillar_id"] is None and "Pillar" in brief_text.splitlines()[max(0, brief_text[:brief_text.find(line)].count("\n") - 3):brief_text.find(line)]:
                pass  # handled below

        # Detect pillar
        if "**Pillar Article:**" in line or "**Pillar:**" in line:
            in_support_table = False
            continue

        # Detect support section
        if "**Support Articles:**" in line:
            in_support_table = True
            continue

        # Extract ID from any line in context
        id_match = re.search(r"\(ID:\s*(\d+)\)", line)
        if id_match:
            aid = int(id_match.group(1))
            if current_cluster["pillar_id"] is None and not in_support_table:
                current_cluster["pillar_id"] = aid
            elif in_support_table or current_cluster["pillar_id"] is not None:
                if aid != current_cluster["pillar_id"]:
                    if aid not in current_cluster["support_ids"]:
                        current_cluster["support_ids"].append(aid)

        # Reset support table on blank line or section break
        if line.strip() == "" or line.startswith("**Secondary") or line.startswith("**Linking") or line.startswith("---"):
            in_support_table = False

    if current_cluster:
        clusters.append(current_cluster)

    return clusters


def generate_linking_plan(
    workspace_root: str,
    website_path: str,
    brief_path: str | None = None,
    clusters_json: list[dict[str, Any]] | None = None,
) -> LinkingPlan:
    """Generate a complete hub-spoke linking plan.

    If clusters_json is provided, use it directly. Otherwise parse clusters from the brief.
    Each cluster dict: {cluster_id, name, pillar_id, support_ids: [int]}
    """
    base = Path(workspace_root) / website_path
    articles_path = base / "articles.json"
    if not articles_path.exists():
        raise FileNotFoundError(f"articles.json not found: {articles_path}")

    with articles_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    articles = [a for a in data.get("articles", []) if isinstance(a, dict)]
    id_to_article = _build_id_to_article_map(articles)

    # Get clusters
    if clusters_json:
        clusters = clusters_json
    else:
        # Parse from brief
        if brief_path:
            bp = Path(brief_path)
            if not bp.is_absolute():
                bp = Path(workspace_root) / brief_path
        else:
            # Auto-detect brief
            folder = Path(workspace_root) / website_path
            patterns = ["*_seo_content_brief.md", "*_sorted_content_brief.md", "*_content_brief.md"]
            candidates: list[Path] = []
            for pattern in patterns:
                candidates.extend(folder.glob(pattern))
            candidates = sorted(set(candidates))
            if not candidates:
                raise FileNotFoundError(f"No content brief found under {website_path}")
            bp = candidates[0]

        brief_text = bp.read_text(encoding="utf-8")
        clusters = _parse_clusters_from_brief(brief_text, articles)

    # Scan existing links
    scan = scan_internal_links(workspace_root, website_path)
    existing_links: set[tuple[int, int]] = set()
    for profile in scan.profiles:
        for tid in profile.outgoing_ids:
            existing_links.add((profile.id, tid))

    # Build plan
    items: list[LinkingPlanItem] = []
    cluster_map: dict[int, int] = {}  # article_id -> cluster_id
    for cl in clusters:
        pid = cl.get("pillar_id")
        sids = cl.get("support_ids", [])
        cid = cl.get("cluster_id", 0)
        if pid:
            cluster_map[pid] = cid
        for sid in sids:
            cluster_map[sid] = cid

    for cl in clusters:
        pid = cl.get("pillar_id")
        sids = cl.get("support_ids", [])
        if not pid:
            continue
        pillar = id_to_article.get(pid)
        if not pillar:
            continue

        for sid in sids:
            support = id_to_article.get(sid)
            if not support:
                continue

            # Hub → Spoke
            items.append(LinkingPlanItem(
                source_id=pid,
                source_title=str(pillar.get("title", "")),
                source_file=str(pillar.get("file", "")),
                target_id=sid,
                target_title=str(support.get("title", "")),
                target_file=str(support.get("file", "")),
                link_type="hub-to-spoke",
                already_exists=(pid, sid) in existing_links,
            ))

            # Spoke → Hub
            items.append(LinkingPlanItem(
                source_id=sid,
                source_title=str(support.get("title", "")),
                source_file=str(support.get("file", "")),
                target_id=pid,
                target_title=str(pillar.get("title", "")),
                target_file=str(pillar.get("file", "")),
                link_type="spoke-to-hub",
                already_exists=(sid, pid) in existing_links,
            ))

    # Cross-cluster links between pillars
    pillar_ids = [cl["pillar_id"] for cl in clusters if cl.get("pillar_id")]
    for i, p1 in enumerate(pillar_ids):
        for p2 in pillar_ids[i + 1:]:
            a1 = id_to_article.get(p1)
            a2 = id_to_article.get(p2)
            if not a1 or not a2:
                continue
            items.append(LinkingPlanItem(
                source_id=p1,
                source_title=str(a1.get("title", "")),
                source_file=str(a1.get("file", "")),
                target_id=p2,
                target_title=str(a2.get("title", "")),
                target_file=str(a2.get("file", "")),
                link_type="cross-cluster",
                already_exists=(p1, p2) in existing_links,
            ))
            items.append(LinkingPlanItem(
                source_id=p2,
                source_title=str(a2.get("title", "")),
                source_file=str(a2.get("file", "")),
                target_id=p1,
                target_title=str(a1.get("title", "")),
                target_file=str(a1.get("file", "")),
                link_type="cross-cluster",
                already_exists=(p2, p1) in existing_links,
            ))

    already = sum(1 for it in items if it.already_exists)
    return LinkingPlan(
        website_path=website_path,
        total_planned=len(items),
        already_linked=already,
        missing_links=len(items) - already,
        items=items,
    )


# ---------------------------------------------------------------------------
# add_article_links
# ---------------------------------------------------------------------------

def add_article_links(
    workspace_root: str,
    website_path: str,
    source_id: int,
    target_ids: list[int],
    mode: str = "related-section",
    dry_run: bool = False,
) -> AddLinksResult:
    """Add internal links from source article to target articles.

    mode='related-section': Append/update a Related Articles section.
    mode='inline': Find natural anchor points in text body (best-effort).

    Returns what was added and what was skipped.
    """
    base = Path(workspace_root) / website_path
    articles_path = base / "articles.json"
    with articles_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    articles = [a for a in data.get("articles", []) if isinstance(a, dict)]
    id_to_article = _build_id_to_article_map(articles)
    file_to_id = _build_file_to_id_map(articles)
    slug_to_id = _build_slug_to_id_map(articles)

    source = id_to_article.get(source_id)
    if not source:
        raise ValueError(f"Source article ID {source_id} not found in articles.json")

    source_file = str(source.get("file", "")).strip()
    if not source_file:
        raise ValueError(f"Article {source_id} has no file path")

    content_path = base / source_file.lstrip("./")
    if not content_path.exists():
        raise FileNotFoundError(f"Content file not found: {content_path}")

    text = content_path.read_text(encoding="utf-8")

    # Find existing outgoing links (recognizes both canonical URLs and legacy paths)
    existing_links, _ = _extract_internal_links(text, source_id, source_file, file_to_id, slug_to_id)
    existing_target_ids = {lnk.target_id for lnk in existing_links}

    added: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for tid in target_ids:
        target = id_to_article.get(tid)
        if not target:
            skipped.append({"target_id": tid, "reason": "not found in articles.json"})
            continue
        if tid in existing_target_ids:
            skipped.append({"target_id": tid, "reason": "link already exists", "title": target.get("title", "")})
            continue

        target_file = str(target.get("file", "")).strip()
        target_title = str(target.get("title", "")).strip()
        if not target_file:
            skipped.append({"target_id": tid, "reason": "target has no file path"})
            continue

        # Compute canonical URL path using url_slug (not relative file path)
        # This ensures links work correctly in the website routing (e.g., /blog/slug/)
        target_slug = str(target.get("url_slug") or "").strip()
        if not target_slug:
            # Fallback: derive slug from filename if url_slug not set
            target_basename = Path(target_file).name
            target_slug = target_basename.replace(".mdx", "").replace(".md", "")
            # Remove numeric prefix like "001_" if present
            target_slug = re.sub(r"^\d+_", "", target_slug)
        link_ref = f"/blog/{target_slug}/"

        if mode == "related-section":
            added.append({
                "target_id": tid,
                "title": target_title,
                "link_ref": link_ref,
            })
        elif mode == "inline":
            added.append({
                "target_id": tid,
                "title": target_title,
                "link_ref": link_ref,
            })

    if not added:
        return AddLinksResult(
            source_id=source_id,
            source_file=source_file,
            links_added=added,
            links_skipped=skipped,
            mode=mode,
        )

    if dry_run:
        return AddLinksResult(
            source_id=source_id,
            source_file=source_file,
            links_added=added,
            links_skipped=skipped,
            mode=mode,
        )

    # Actually write links
    if mode == "related-section":
        text = _add_related_section(text, added)
    elif mode == "inline":
        text = _add_inline_links(text, added)

    content_path.write_text(text, encoding="utf-8")

    return AddLinksResult(
        source_id=source_id,
        source_file=source_file,
        links_added=added,
        links_skipped=skipped,
        mode=mode,
    )


def _add_related_section(text: str, links: list[dict[str, Any]]) -> str:
    """Add or update a Related Articles section at the end of MDX content."""
    new_links_md = "\n".join(
        f"- [{link['title']}]({link['link_ref']})" for link in links
    )

    # Check if Related Articles section already exists
    related_pattern = re.compile(
        r"(^#{1,4}\s+Related\s+Articles.*$)", re.MULTILINE | re.IGNORECASE
    )
    match = related_pattern.search(text)

    if match:
        # Find the end of the Related Articles section
        # Look for next heading or end of file
        rest = text[match.end():]
        next_heading = re.search(r"^#{1,3}\s+", rest, re.MULTILINE)
        if next_heading:
            insert_pos = match.end() + next_heading.start()
            # Insert before the next heading
            text = text[:insert_pos].rstrip() + "\n" + new_links_md + "\n\n" + text[insert_pos:]
        else:
            # Append at end
            text = text.rstrip() + "\n" + new_links_md + "\n"
    else:
        # Add new section at end
        text = text.rstrip() + "\n\n## Related Articles\n\n" + new_links_md + "\n"

    return text


def _add_inline_links(text: str, links: list[dict[str, Any]]) -> str:
    """Best-effort: add inline markdown links where keywords naturally appear.

    Falls back to a Related Articles section if no inline spots are found.
    """
    remaining: list[dict[str, Any]] = []

    for link in links:
        title = link["title"]
        ref = link["link_ref"]

        # Try to find a good anchor - look for the target keyword or title words
        # in the body text (skip frontmatter)
        fm_match = re.match(r"^---\s*\n.*?\n---\s*\n", text, re.DOTALL)
        body_start = fm_match.end() if fm_match else 0

        # Generate search terms from the title
        # Remove common words and look for 2-3 word phrases
        words = re.findall(r"[A-Za-z]+", title)
        stop_words = {"the", "a", "an", "in", "of", "for", "to", "and", "or", "is", "are", "how",
                       "what", "why", "with", "your", "from", "that", "this", "on", "at", "by",
                       "complete", "guide", "best", "ultimate", "simple"}
        keywords = [w for w in words if w.lower() not in stop_words and len(w) > 3]

        linked = False
        # Try to find a sentence containing 2+ keywords
        for i in range(len(keywords) - 1):
            phrase_pattern = re.compile(
                rf"(?<!\[)({re.escape(keywords[i])}\s+\w+\s+{re.escape(keywords[i+1])}|"
                rf"{re.escape(keywords[i+1])}\s+\w+\s+{re.escape(keywords[i])})",
                re.IGNORECASE,
            )
            body = text[body_start:]
            m = phrase_pattern.search(body)
            if m:
                anchor = m.group(0)
                # Make sure this text is not already a link
                before = body[:m.start()]
                if not before.endswith("[") and "](" not in body[m.start():m.end() + 5]:
                    replacement = f"[{anchor}]({ref})"
                    text = text[:body_start + m.start()] + replacement + text[body_start + m.end():]
                    linked = True
                    break

        if not linked:
            remaining.append(link)

    # Anything we couldn't inline → add to Related Articles
    if remaining:
        text = _add_related_section(text, remaining)

    return text


# ---------------------------------------------------------------------------
# get_article_content
# ---------------------------------------------------------------------------

def get_article_content(
    workspace_root: str,
    website_path: str,
    article_id: int,
) -> dict[str, Any]:
    """Get article metadata + MDX content by ID."""
    base = Path(workspace_root) / website_path
    articles_path = base / "articles.json"
    with articles_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    articles = [a for a in data.get("articles", []) if isinstance(a, dict)]
    id_to_article = _build_id_to_article_map(articles)

    article = id_to_article.get(article_id)
    if not article:
        raise ValueError(f"Article ID {article_id} not found in articles.json")

    file_ref = str(article.get("file", "")).strip()
    content = ""
    word_count = 0
    if file_ref:
        content_path = base / file_ref.lstrip("./")
        if content_path.exists():
            content = content_path.read_text(encoding="utf-8")
            # Strip frontmatter for word count
            fm_match = re.match(r"^---\s*\n.*?\n---\s*\n", content, re.DOTALL)
            body = content[fm_match.end():] if fm_match else content
            word_count = len(body.split())

    return {
        "id": article_id,
        "title": article.get("title", ""),
        "file": file_ref,
        "target_keyword": article.get("target_keyword", ""),
        "status": article.get("status", ""),
        "url_slug": article.get("url_slug", ""),
        "published_date": article.get("published_date", ""),
        "keyword_difficulty": article.get("keyword_difficulty", ""),
        "target_volume": article.get("target_volume", 0),
        "word_count": word_count,
        "content": content,
    }


# ---------------------------------------------------------------------------
# update_brief_linking_status
# ---------------------------------------------------------------------------

def update_brief_linking_status(
    workspace_root: str,
    website_path: str,
    brief_path: str | None = None,
    dry_run: bool = False,
) -> BriefUpdateResult:
    """Scan actual MDX files and update ☐ → ✅ in the brief linking checklist.

    Parses ID references from checklist items like:
      - ☐ Article Title (ID: 5)
    Under a source article heading like:
      **"Article Title" (ID: 10) - Link to:**

    If the actual content file for the source contains a link to the target file,
    flips ☐ → ✅.
    """
    base = Path(workspace_root) / website_path

    # Resolve brief
    if brief_path:
        bp = Path(brief_path)
        if not bp.is_absolute():
            bp = Path(workspace_root) / brief_path
    else:
        folder = Path(workspace_root) / website_path
        patterns = ["*_seo_content_brief.md", "*_sorted_content_brief.md", "*_content_brief.md"]
        candidates: list[Path] = []
        for pattern in patterns:
            candidates.extend(folder.glob(pattern))
        candidates = sorted(set(candidates))
        if not candidates:
            raise FileNotFoundError(f"No content brief found under {website_path}")
        bp = candidates[0]

    # Load articles for file lookups
    articles_path = base / "articles.json"
    with articles_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    articles = [a for a in data.get("articles", []) if isinstance(a, dict)]
    id_to_article = _build_id_to_article_map(articles)
    file_to_id = _build_file_to_id_map(articles)

    # Scan actual links
    scan = scan_internal_links(workspace_root, website_path)
    actual_links: set[tuple[int, int]] = set()
    for profile in scan.profiles:
        for tid in profile.outgoing_ids:
            actual_links.add((profile.id, tid))

    # Parse and update brief
    brief_text = bp.read_text(encoding="utf-8")
    lines = brief_text.splitlines()

    current_source_id: int | None = None
    items_checked = 0
    items_already_done = 0
    items_pending = 0

    new_lines: list[str] = []
    # Pattern for source article heading: **"Title" (ID: N) - Link to:**
    # or **Hub: "Title" (ID: N) - Link to all:**
    source_pattern = re.compile(r"\*\*.*?\(ID:\s*(\d+)\).*?(?:Link to|link to)")
    # Pattern for checklist item: - ☐ ... (ID: N) or - ✅ ... (ID: N)
    item_pattern = re.compile(r"^(\s*-\s+)(☐|✅)(\s+.*?\(ID:\s*(\d+)\).*)$")

    in_linking_section = False
    for line in lines:
        # Detect linking section
        if re.match(r"^##\s+Internal\s+Linking\s+Strategy", line, re.IGNORECASE):
            in_linking_section = True
        elif re.match(r"^##\s+", line) and in_linking_section and "Internal" not in line:
            in_linking_section = False

        if in_linking_section:
            # Check for source heading
            sm = source_pattern.search(line)
            if sm:
                current_source_id = int(sm.group(1))

            # Check for checklist item
            im = item_pattern.match(line)
            if im and current_source_id is not None:
                prefix = im.group(1)
                status_char = im.group(2)
                rest = im.group(3)
                target_id = int(im.group(4))

                if status_char == "✅":
                    items_already_done += 1
                    new_lines.append(line)
                    continue

                # Check if source actually links to target
                if (current_source_id, target_id) in actual_links:
                    new_lines.append(f"{prefix}✅{rest}")
                    items_checked += 1
                    continue
                else:
                    items_pending += 1
                    new_lines.append(line)
                    continue

        new_lines.append(line)

    if not dry_run and items_checked > 0:
        bp.write_text("\n".join(new_lines), encoding="utf-8")

    return BriefUpdateResult(
        brief_path=str(bp),
        items_checked=items_checked,
        items_already_done=items_already_done,
        items_still_pending=items_pending,
    )
