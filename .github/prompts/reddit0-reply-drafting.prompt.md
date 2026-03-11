---
name: reddit0-reply-drafting
description: Draft Reddit replies for a project (generic drafting guidance; not tied to a specific stage).
argument-hint: "project=coffee"
agent: agent
---

Draft Reddit replies for `project=<id>`.

- Skill (source of truth): `.github/skills/reddit-reply-drafting/SKILL.md`
- Input: `project=<id>` (required; must exist in `.github/prompts/projects.json`)
- References: `general/<project>/<project>.md`, `general/<project>/reddit_config.md`, `general/brandvoice.md`, `projects/reddit/_reply_guardrails.md`
- If `project` is missing, ask once and stop
