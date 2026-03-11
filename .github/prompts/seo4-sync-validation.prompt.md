---
name: seo4-sync-validation
description: SEO Step 4 sync validation (repo-local; sync + gap checks only, no deploy).
argument-hint: "website_path=. apply_sync=false (optional)"
agent: agent
---

Run SEO sync validation in this repo (repo-local workspace).

- Skill (source of truth): `.github/skills/seo-sync-validation/SKILL.md`
- Workspace root: `automation`
- Command family: `pageseeds content sync-and-validate`
- Use CLI commands only (no MCP tool fallback for this step)
