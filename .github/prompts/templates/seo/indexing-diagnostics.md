---
agent: agent
---

# {{PROJECT_DISPLAY_NAME}} - SEO Step 6: Indexing Diagnostics (Why Not Indexed)

Run the workflow defined in:

- `.github/skills/seo-indexing-diagnostics/SKILL.md`

References:
- `general/brandvoice.md`
- `{{PROJECT_DESCRIPTION_FILE}}`
- `general/{{PROJECT_NAME}}/manifest.json`
- `{{PROJECT_ARTICLES_FILE}}`

Inputs:
- Project name: `{{PROJECT_NAME}}`
- Website path: `general/{{PROJECT_NAME}}`

Commands:

```bash
automation-cli seo gsc-indexing-report --manifest general/{{PROJECT_NAME}}/manifest.json
```

Credentials are auto-resolved from machine-local automation secrets/env sources; only ask for credential setup if the command fails with missing auth.
