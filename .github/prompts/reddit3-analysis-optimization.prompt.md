---
name: reddit3-analysis-optimization
description: Reddit Stage 3 analysis and optimization for a project (update engagement metrics; review stats; refine queries).
argument-hint: "project=coffee"
agent: agent
---

Run Reddit Stage 3 for `project=<id>`.

- Skill (source of truth): `.github/skills/reddit-analysis-optimization/SKILL.md`
- Input: `project=<id>` (required; must exist in `.github/prompts/projects.json`)
- If `project` is missing, ask once and stop
