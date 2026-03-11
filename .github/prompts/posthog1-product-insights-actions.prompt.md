---
name: posthog1-product-insights-actions
description: Build and refine cross-site PostHog action queue.
argument-hint: ""
agent: agent
---

Turn PostHog insight packets into a prioritized action queue.

- Skill (source of truth): `.github/skills/posthog-product-insights/SKILL.md`
- Build deterministic queue: `automation-cli posthog action-queue --repo-root . --write-md`
- Inputs:
  - `output/posthog/<YYYY-MM-DD>_summary.md`
  - `output/posthog/<YYYY-MM-DD>_action_queue.json`
  - `output/posthog/<site_id>_<YYYY-MM-DD>_insights.json`
- Refine into final recommendations:
  - Remove weak/duplicate actions
  - Prioritize P0/P1/P2 by evidence strength
  - Convert each action into concrete next steps in repo/workflow terms
- Refer to the skill for thresholds, guardrails, and output contract.

