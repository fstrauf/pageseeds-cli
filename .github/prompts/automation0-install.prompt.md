---
name: automation0-install
description: Install the core automation payload (skills + slash prompts) into the current repo.
argument-hint: ""
agent: agent
---

Install the automation payload into this repo.

- Skill (source of truth): `.github/skills/distributed-workflows/SKILL.md`
- Run (writes into `.github/skills` and `.github/prompts`):

```bash
automation-cli repo init
```

Then confirm:

```bash
automation-cli repo status
```

