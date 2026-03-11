---
name: seo6-indexing-diagnostics
description: SEO Step 6 indexing diagnostics (repo-local; inspect sitemap URLs via Search Console URL Inspection API).
argument-hint: "site=sc-domain:example.com sitemap_url=https://example.com/sitemap.xml limit=200 workers=2 (optional)"
agent: agent
---

Run SEO Step 6 in this repo.

- Skill (source of truth): `.github/skills/seo-indexing-diagnostics/SKILL.md`
- Step 6 uses centralized tool code from the automation repo (no scripts are copied into this repo).
- Follow the predefined CLI path only (`pageseeds automation seo ...`); do not use MCP server tools for Step 6 routing/discovery.

Quick command:

```bash
pageseeds automation seo gsc-indexing-report \
  --site sc-domain:example.com \
  --sitemap-url https://example.com/sitemap.xml \
  --limit 200 --workers 2
```

Credentials are auto-resolved from machine-local automation secrets/env sources; do not stop to ask for credential setup unless the command reports missing auth.

Then use the generated `automation/output/gsc_indexing/*_fix_plan.md`, `*_action_queue.md`, and `*_summary.md` (no ad-hoc parsing scripts).
