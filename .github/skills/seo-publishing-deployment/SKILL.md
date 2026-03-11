---
name: seo-publishing-deployment
description: Run SEO Step 4 (publishing & deployment) repo-locally: validate/clean content, sanity-check dates, and deploy via the repo’s normal pipeline.
---

# SEO Publishing & Deployment

⚠️ **EXECUTION MANDATE**: Do NOT ask questions, summarize, or provide options. Execute this workflow immediately and completely.

This is the final step before content goes live. In the repo-local setup, deployment is handled by the repo’s normal build/deploy pipeline (not `pageseeds content ops`).

## Overview

**Purpose**: Safely ship `ready_to_publish` articles after content QA.

**Prerequisites**:
- Articles marked as `status="ready_to_publish"` in `articles.json`
- Content files exist in the automation workspace
- No duplicate filenames or slug collisions

**Outcome**:
- Content is validated/clean
- Recent date issues are fixed (if any)
- Repo deploy is run (CI/CD or manual)

## Project Structure (Repo-Local)

- Workspace root: `automation/`
- Articles index: `automation/articles.json`
- Content folder: `automation/content/` (usually a symlink to the canonical repo content folder)

## Terminal Execution Rules (MANDATORY)

1. **ALWAYS foreground** — run every CLI command synchronously. NEVER background with `&`.
2. **NEVER poll** — no `sleep`, `ps`, `tail -f`, `wait`, or `jobs` loops.
3. **NEVER redirect to temp files** — no `> /tmp/…`, `cat > /tmp/…`, or heredoc writes.
4. **NEVER manually construct JSON** — every JSON blob the workflow needs is produced by a CLI command.
5. **NEVER pipe through jq** — prefer the CLI output directly.

## Workflow Steps (Repo-Local)

### 1) Validate and Clean

```bash
pageseeds content --workspace-root automation validate --website-path .
pageseeds content --workspace-root automation clean --website-path .
pageseeds content --workspace-root automation validate --website-path .
```

### 2) Sanity-Check Dates (Optional but Recommended)

```bash
pageseeds content --workspace-root automation analyze-dates --website-path .
pageseeds content --workspace-root automation fix-dates --website-path .
pageseeds content --workspace-root automation analyze-dates --website-path .
```

### 3) Confirm What’s Ready

```bash
pageseeds content --workspace-root automation articles-index --website-path . --status ready_to_publish
```

### 4) Deploy

Deploy is repo-specific (CI/CD, `pnpm build`, a deploy script, etc.). Run the repo’s normal deployment process.

### 5) Verify

After deploy:
- spot-check a few pages/URLs
- optionally re-run Step 6 indexing diagnostics after a few days

## Common Issues

- **Duplicate title headings / frontmatter mismatches**: fix via Step 5 (cleanup) and re-run `validate-content`.
- **Date issues**: use `analyze-dates` + `fix-dates` (Step 5).
