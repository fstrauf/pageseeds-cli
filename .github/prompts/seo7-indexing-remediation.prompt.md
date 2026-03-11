---
name: seo7-indexing-remediation
description: SEO Step 7 remediation (repo-local; apply scoped content fixes driven by Step 6 action queue).
argument-hint: "action_queue=automation/output/gsc_indexing/..._action_queue.json (optional)"
agent: agent
---

Run SEO Step 7 in this repo.

- Skill (source of truth): `.github/skills/seo-indexing-remediation/SKILL.md`
- Inputs: Step 6 outputs in `automation/output/gsc_indexing/` (especially `*_action_queue.json`)
- Follow the predefined CLI path only (`pageseeds automation seo ...`); do not use MCP server tools for Step 7 routing/discovery.
- Use one Step 6 action queue path for the whole Step 7 run; pass it explicitly with `--action-queue ...` where supported.
- Optional context refresh before edits: `pageseeds automation seo gsc-watch --site ... --action-queue ...` and `pageseeds automation seo gsc-site-scan --site ... --action-queue ...`.
- Start with `pageseeds automation seo gsc-remediation-targets` to get deterministic edit-ready mapped files.
- Use `pageseeds automation seo gsc-remediation-inputs` only if you need broader starter URLs.
- Use `pageseeds automation seo gsc-action-queue` for deterministic queue filtering/selection (no ad-hoc parsing).
- Follow the skill to select targets deterministically and apply content fixes directly in-repo.
