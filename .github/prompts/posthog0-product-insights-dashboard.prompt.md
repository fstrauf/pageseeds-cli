---
name: posthog0-product-insights-dashboard
description: Cross-site PostHog pull + prioritized action queue (repo-grounded).
argument-hint: ""
agent: agent
---

Run the cross-site PostHog product insights workflow.

- Skill (source of truth): `.github/skills/posthog-product-insights/SKILL.md`
- Run deterministic pull via `automation-cli posthog report --repo-root . --refresh`
- Use existing repo/env configuration; do not create new `.env` or manifest files during normal execution.
- Script auto-discovers sites from `general/*/manifest.json` files with PostHog config.
- Script output:
  - `output/posthog/<YYYY-MM-DD>_summary.md`
  - `output/posthog/<site_id>_<YYYY-MM-DD>_insights.json` (insights + dashboards + page traffic + situations + action candidates)
- Next step: run `posthog1-product-insights-actions` to build + refine action queue.
- For workflow details, rule thresholds, and guardrails, refer to the skill only.

