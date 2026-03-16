---
name: seo-sync-validation
description: Run SEO sync + index/file gap validation using the focused ops workflow.
---

# SEO Sync Validation

Run this before publishing when you want a clean sync/gap check without date optimization or deployment.

## Execution Mandate

- CLI-only workflow.
- Never call MCP tools for this step.
- If CLI execution fails, stop and report the CLI error; do not switch to MCP fallback.
- Prefer repo-local command (`sync-and-validate` with `--website-path`).

## Goal

- Validate `articles.json` entries against local content files
- Optionally sync frontmatter dates from `articles.json` into content files
- Surface gaps:
  - missing files referenced by index (`missing_files`)
  - orphan files not in index (`orphan_files`)
  - date mismatches (`date_mismatches`)

## Commands

Preview (safe default):

```bash
seo-content-cli --workspace-root automation sync-and-validate --website-path . --compact
```

Apply date sync + validate:

```bash
seo-content-cli --workspace-root automation sync-and-validate --website-path . --apply-sync --compact
```

If `pageseeds` is not available in PATH, install it via pip:

```bash
pip install pageseeds
```

## Decision Rules

- If `missing_files > 0`: fix index entries/files first.
- If `date_mismatches > 0`: run apply sync to align frontmatter dates.
- If `orphan_files > 0`: either add them to `articles.json` or remove/archive them.
