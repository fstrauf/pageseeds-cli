---
name: seo0-local-setup
description: Create/update a minimal repo-local SEO workspace under `automation/` (articles.json + content pointer + config).
argument-hint: "website_id=days_to_expiry content_dir=webapp/content/blog"
agent: agent
---

Set up the repo-local SEO workspace.

- Skill (source of truth): `.github/skills/seo-local-setup/SKILL.md`

Run:

```bash
automation-cli seo init \
  --site-id "<website_id>" \
  --content-dir "<source_content_dir>" \
  --link-mode symlink \
  --force
```
