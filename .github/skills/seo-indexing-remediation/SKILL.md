---
name: seo-indexing-remediation
description: SEO Step 7. Apply fixes for non-indexed pages using Step 6 artifacts and make scoped changes directly in this repo.
---

# SEO Indexing Remediation (Phase 2)

Goal: take the deterministic outputs from Step 6 and turn them into a scoped set of content fixes you can land directly in this repo (PR/commit).

## Inputs (From Step 6)

From `automation/output/gsc_indexing/`:

- `..._fix_plan.md` (primary triage)
- `..._action_queue.json` (deterministic per-URL queue; this drives remediation)

## Key Rule

Only make changes that are:

- scoped to a known list of target URLs/files (from the action queue)
- deployable as a small set of content files

Anything that requires app templates (canonicals, headers, robots rules, sitemap generation) should be surfaced as a ticket list, not hacked into content.

Step 7 execution path is CLI-first and deterministic:

- Use only `automation-cli seo ...` commands for queue selection and scan context.
- Do not call `seo-content-mcp` or other MCP servers for Step 7 discovery/routing.
- If Step 6 artifacts are missing, stop and request/re-run Step 6 (`gsc-indexing-report`) instead of using alternate discovery paths.

## Workflow

### 0) Lock to Step 6 output first

Resolve and use a single Step 6 action queue for the whole run:

- Prefer explicit `--action-queue automation/output/gsc_indexing/..._action_queue.json`
- If omitted, commands may auto-select latest queue, but explicit is preferred for deterministic handoff from Step 6.

Use the same `--action-queue` value across all Step 7 commands in this run.

### 1) Select the Fix Set Deterministically

Do not use `jq`, shell pipes, or ad-hoc parsing scripts.

Fast path (default): get edit-ready mapped files immediately:

```bash
automation-cli seo gsc-remediation-targets \
  --action-queue automation/output/gsc_indexing/..._action_queue.json \
  --format lines \
  --field basename \
  --unique \
  --limit 12
```

If you need URL-to-file mapping in one command:

```bash
automation-cli seo gsc-remediation-targets \
  --action-queue automation/output/gsc_indexing/..._action_queue.json \
  --format lines \
  --field url_to_file \
  --limit 12
```

Only if the fast path returns too few targets, use the broader starter input command:

```bash
automation-cli seo gsc-remediation-inputs --format lines --field url --limit 20
```

Primary target extraction (mapped content files only):

```bash
automation-cli seo gsc-action-queue \
  --action-queue automation/output/gsc_indexing/..._action_queue.json \
  --reason-code fetch_error \
  --reason-code noindex \
  --reason-code robots_blocked \
  --reason-code canonical_mismatch \
  --reason-code not_indexed_other \
  --coverage-contains crawled \
  --mapped-only \
  --format lines \
  --field basename \
  --unique \
  --limit 20
```

Fallback for discovered-not-indexed set:

```bash
automation-cli seo gsc-action-queue \
  --action-queue automation/output/gsc_indexing/..._action_queue.json \
  --reason-code not_indexed_other \
  --coverage-contains discovered \
  --mapped-only \
  --format lines \
  --field basename \
  --unique \
  --limit 20
```

Treat the returned basename/file list as the only approved file scope for this run.

Execution discipline for Step 7:

- Run at most 3 discovery commands before making edits.
- Do not inspect unrelated files once target files are identified.
- Start edits immediately on the selected files.

Optional context pull before edits (still scoped to Step 6 queue):

```bash
automation-cli seo gsc-watch \
  --site sc-domain:example.com \
  --action-queue automation/output/gsc_indexing/..._action_queue.json
```

```bash
automation-cli seo gsc-site-scan \
  --site sc-domain:example.com \
  --action-queue automation/output/gsc_indexing/..._action_queue.json \
  --top-pages 5 --decliners 5 --max-pages 12
```

### 2) Apply Fixes (Content-Managed)

For each mapped file:

- Add 3-5 contextual internal links from relevant hubs/spokes (reuse your existing clustering/linking plan; avoid inventing new formats).
- Expand thin pages: add concrete examples, comparisons, FAQs, and uniquely useful sections.
- Remove or update obviously outdated “month/year” pages: either make evergreen (preferred) or plan redirects (ticket).
- Ensure the page strongly links to the canonical URL you want indexed (internal links should point to the canonical).

Do not write one-off parsing scripts. Use `automation-cli seo gsc-action-queue`, existing CLI tools, and direct file edits.

### 3) Verify

Re-run Step 6 with a smaller scope (limit 50-100) after a few days or after you request reindexing in Search Console.

## Output Expectations

- A short “Fixes Applied” list: URL -> file -> what changed (internal links, expansions, consolidations).
- A separate “Needs Template/App Work” list for non-content fixes (canonical tag injection, robots, sitemap issues).
