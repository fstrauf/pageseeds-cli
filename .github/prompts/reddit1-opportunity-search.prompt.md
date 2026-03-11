---
name: reddit1-opportunity-search
description: Reddit Stage 1 opportunity search for a project (find + score posts; insert into DB).
argument-hint: "project=coffee"
agent: agent
---

Run Reddit Stage 1 for `project=<id>`.

- Skill (source of truth): `.github/skills/reddit-opportunity-search/SKILL.md`
- Input: `project=<id>` (required; must exist in `.github/prompts/projects.json`)
- References: `general/<project>/<project>.md`, `general/<project>/reddit_config.md`, `general/brandvoice.md`, `projects/reddit/_reply_guardrails.md`
- If `project` is missing, ask once and stop
