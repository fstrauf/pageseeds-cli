---
name: automation0-update
description: Update the installed automation payload (skills + slash prompts) in the current repo.
argument-hint: ""
agent: agent
---

Update the automation payload in this repo.

- Skill (source of truth): `.github/skills/distributed-workflows/SKILL.md`
- Run:

```bash
pageseeds automation repo update
```

This preserves previously-installed bundles (for example `seo`) via `.github/automation/automation_payload.json`.

Then confirm:

```bash
pageseeds automation repo status
```
