---
name: posthog0-single-site
description: Single-site PostHog analytics pull (repo-local, no registry required).
argument-hint: "project_id=12345 api_key_env=POSTHOG_API_KEY (optional if config exists)"
agent: agent
---

Run PostHog analytics for this single-site repo.

- Skill (source of truth): `.github/skills/posthog-single-site/SKILL.md`
- Workspace root: `automation`
- Website path: `.`
- Config file (optional): `automation/posthog_config.json`
- Output: `automation/output/posthog/`

## Quick Start

If `automation/posthog_config.json` exists:
```bash
automation-cli posthog report --repo-root . --refresh
```

Otherwise, use command-line flags with project_id and api_key_env.

## View Results (No Custom Code)

After running the report, use the `view` command to extract data:

```bash
# View detected situations
automation-cli posthog view --field situations

# View action candidates
automation-cli posthog view --field action_candidates

# View insights with values
automation-cli posthog view --field insights

# View breakdown values (referring domains, browsers, etc.)
automation-cli posthog view --field breakdowns

# JSON format for programmatic use
automation-cli posthog view --field situations --format json
```

**DO NOT** write Python/jq to parse JSON files. Use `automation-cli posthog view`.
