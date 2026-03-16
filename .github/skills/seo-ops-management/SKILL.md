---
name: seo-ops-management
description: Notes for multi-site SEO ops (registry-based). Repo-local installs do not use `seo-content-cli ops`.
---

# SEO Ops: Drift, Dates, and Dashboard

This skill captures the operational game plan for running multiple SEO sites with strict publishing pipelines.

Repo-local note: the distributed installer intentionally does NOT install a multi-site registry, so `seo-content-cli ops ...` commands are out of scope for repo-local workflows.

## Principles

- Production repo is source of truth for anything already published.
- Automation repo is staging for drafts + planning metadata.
- `articles.json` is the automation-side index, refreshed from production for published content.
- Never auto-modify old published content.
- Prefer read-only drift reports + explicit apply actions.

## Desired Workflows

### A) Import/refresh from production (read-only)

Goal: make automation’s `articles.json` reflect production content.

- Scan production content dir for MDX/MD
- Parse frontmatter
- Update automation `articles.json` entries as `published`
- Never write to production as part of import

### B) Drift report (automation vs production)

Goal: quickly answer “what changed where?”

Signals:
- Missing/extra files
- Content hash mismatch
- Frontmatter mismatch

Resolution is always explicit (no automatic overwrites).

### C) Date scheduling (draft-safe)

Rules:
- Only apply to `ready_to_publish` by default
- Never touch `published` entries
- Never create future dates

### D) Deploy (ready_to_publish only)

Rules:
- Only deploy files for `ready_to_publish`
- Only deploy files missing in production
- Treat mismatches as review items

## Implementation Notes (No MCP Server)

Multi-site ops are registry-based and not part of the repo-local package.

For repo-local publishing, use:
- `.github/skills/seo-content-cleanup/SKILL.md` (validation + date sanity)
- `.github/skills/seo-publishing-deployment/SKILL.md` (deploy via repo pipeline)
