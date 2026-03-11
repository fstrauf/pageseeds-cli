---
name: reddit2-reply-engagement
description: Reddit Stage 2 reply and engagement for a project (review pending; post manually; mark posted/skipped in DB).
argument-hint: "project=coffee"
agent: agent
---

Run Reddit Stage 2 for `project=<id>`.

- Skill (source of truth): `.github/skills/reddit-reply-engagement/SKILL.md`
- Input: `project=<id>` (required; must exist in `.github/prompts/projects.json`)
- If `project` is missing, ask once and stop
