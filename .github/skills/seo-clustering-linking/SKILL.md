---
name: seo-clustering-linking
description: Run SEO Step 3 (clustering & linking): cluster by intent, pick pillars/supports, update brief with gaps and linking checklist, and add internal links in MDX.
---

# SEO Clustering & Linking

⚠️ **EXECUTION MANDATE**: Do NOT ask questions, summarize, or provide options. Execute this workflow immediately and completely.

You are an SEO strategist. This workflow organizes content into topical clusters and adds internal links to establish topical authority.

## Project Structure

Repo-local SEO workspace:

- Workspace root: `automation/`
- Content brief: `automation/*_seo_content_brief.md` (auto-detected by CLI)
- Articles JSON: `automation/articles.json`
- Content folder: `automation/content/` (usually a symlink to the canonical repo content folder)

## Tooling Requirements

Use `pageseeds content` for ALL structured operations. Never use ad-hoc jq/Python/terminal scripts.

### Available CLI Commands (Step 3)

```bash
# Load articles (Part 1 prerequisites)
pageseeds content --workspace-root automation articles-summary --website-path .
pageseeds content --workspace-root automation articles-index --website-path .

# Cannibalization spot-check
pageseeds content --workspace-root automation get-articles-by-keyword --website-path . --keyword '<keyword>'

# Get article content by ID (no manual file lookup needed)
pageseeds content --workspace-root automation get-article-content --website-path . --article-id <ID>
pageseeds content --workspace-root automation get-article-content --website-path . --article-id <ID> --metadata-only

# Scan existing internal links (read-only)
pageseeds content --workspace-root automation scan-internal-links --website-path .
pageseeds content --workspace-root automation scan-internal-links --website-path . --verbose

# Generate linking plan from clusters in the brief (read-only)
pageseeds content --workspace-root automation generate-linking-plan --website-path .
pageseeds content --workspace-root automation generate-linking-plan --website-path . --missing-only

# Add links to a specific article
pageseeds content --workspace-root automation add-article-links --website-path . --source-id <ID> --target-ids <ID1> <ID2> <ID3>
pageseeds content --workspace-root automation add-article-links --website-path . --source-id <ID> --target-ids <ID1> --mode inline --dry-run

# Batch add ALL missing links from the plan at once
pageseeds content --workspace-root automation batch-add-links --website-path . --dry-run
pageseeds content --workspace-root automation batch-add-links --website-path .

# Auto-update brief checklist based on actual links
pageseeds content --workspace-root automation update-brief-linking-status --website-path . --dry-run
pageseeds content --workspace-root automation update-brief-linking-status --website-path .
```

Disallowed as substitutes:

- Ad-hoc terminal/Python/jq to load/summarize `articles.json`
- Manual `grep` to find internal links in files
- Manual file reads to map article IDs to file paths

## PART 1: Create Clusters

### 1) Load articles

```bash
pageseeds content --workspace-root automation articles-summary --website-path .
pageseeds content --workspace-root automation articles-index --website-path .
```

### 2) Group by intent

- Informational (guides)
- Navigational (comparisons/lists)
- Transactional (how-to)
- Commercial (buy/get)

### 3) Pick a pillar per cluster

- Broadest scope
- Links out to all supports

### 4) Identify supports

- Narrow scope (single subtopic)
- Links back to pillar

### 5) Map coverage + gaps

In the brief, document:

- Covered (check) 
- Missing (warning) content gaps with HIGH/MEDIUM/LOW priority

### 6) Cannibalization check

For suspected duplicates:

```bash
pageseeds content --workspace-root automation get-articles-by-keyword --website-path . --keyword '<keyword>'
```

If 2+ matches, resolve by merging or differentiating.

### 7) Update content brief

Add a "Topical Clusters & Intent Mapping" section (with pillar, supports, gaps, linking strategy).

Cluster format for the brief (must follow this structure for automated parsing):

```markdown
### Cluster N: Name PILLAR CLUSTER
**Primary Intent:** "..."

**Pillar Article:**
- **"Title"** (ID: N)

**Support Articles:**
| Article | Target Keyword | Intent Type | Focus |
| ... (ID: N) ... | ... | ... | ... |

**Linking Strategy:**
- Pillar (ID: N) <-> All supports (IDs: ...)
```

## PART 2: Add Internal Links

### 1) Scan existing links

```bash
pageseeds content --workspace-root automation scan-internal-links --website-path .
```

Review orphan articles and current link coverage.

### 2) Generate the linking plan

```bash
pageseeds content --workspace-root automation generate-linking-plan --website-path . --missing-only
```

This reads clusters from the brief and shows all missing hub-spoke + cross-cluster links.

### 3) Add missing links

**Option A: Batch (recommended for initial linking)**

```bash
# Preview first
pageseeds content --workspace-root automation batch-add-links --website-path . --dry-run
# Apply
pageseeds content --workspace-root automation batch-add-links --website-path .
```

**Option B: Per-article (for targeted edits)**

```bash
pageseeds content --workspace-root automation add-article-links --website-path . --source-id <ID> --target-ids <ID1> <ID2>
```

Modes:
- `--mode related-section` (default): Appends/updates a "Related Articles" section
- `--mode inline`: Tries to add natural anchor links in body text, falls back to Related section

**Link Format (IMPORTANT):**
The CLI now creates canonical URL links by default:
- ✅ Correct: `[Article Title](/blog/article-slug/)`
- ❌ Legacy: `[Article Title](./001_article_slug.mdx)`

All internal links should use the canonical URL format `/blog/{url_slug}/`. This ensures:
1. Links work correctly in the deployed website
2. No broken links when files are reorganized
3. Better SEO with consistent URL structure

**Migration:** To fix existing relative links in a project:
```bash
uv run tools/seo_help/fix_relative_links_to_canonical.py general/coffee --write
```

### 4) Update brief checklist

```bash
# Preview
pageseeds content --workspace-root automation update-brief-linking-status --website-path . --dry-run
# Apply
pageseeds content --workspace-root automation update-brief-linking-status --website-path .
```

This automatically scans actual MDX files and flips unchecked to checked for links that exist.

### 5) Verify bidirectional coverage

```bash
pageseeds content --workspace-root automation generate-linking-plan --website-path . --missing-only
```

If missing_links > 0, repeat step 3 for remaining articles.
