---
name: seo-local-setup
description: Create a minimal repo-local SEO workspace under `automation/` so `seo-content-cli` can run anywhere without copying articles/content into the automation repo.
---

# SEO Local Setup (Repo-Local Workspace)

## Goal

Enable running `seo-content-cli` in any repo with minimal context by creating a small workspace folder:

- `automation/articles.json` (article registry used by the SEO CLIs)
- `automation/content` (points at the canonical content folder)
- `automation/seo_workspace.json` (lightweight config + status output; no website registry)

This avoids syncing content into external repositories.

## One-Time Setup

Run this from the repo where you want slash commands to live (it can be the content repo or a "control" repo):

```bash
pageseeds automation seo init \
  --site-id '<id>' \
  --content-dir 'webapp/content/blog'
```

Notes:
- Default `--link-mode symlink` keeps a single source of truth (no drift) and is the right choice when the content lives in the same repo.
- If you prefer a fully local copy, use `--link-mode copy` (but you must refresh/update explicitly later).
- `--force` replaces the workspace `content` link/dir if it already exists. It does not wipe `articles.json` unless you pass `--reset-articles`.

## Verify

Run:

```bash
pageseeds automation seo status --website-id '<id>'
```

Then validate the registry is reachable:

```bash
seo-content-cli --workspace-root automation articles-summary --website-path .
```

If `content` is configured, you can also run:

```bash
seo-content-cli --workspace-root automation validate-content --website-path .
```
