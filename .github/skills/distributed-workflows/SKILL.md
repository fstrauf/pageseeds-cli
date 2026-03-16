---
name: distributed-workflows
description: Run automation workflows from the repo that owns the content by installing CLIs locally (uv tools) and syncing skills/prompts as needed.
---

# Distributed Workflows (Local Tool Install)

## Intent

Eliminate the "sync articles into automation repo, edit, sync back" loop by:

- keeping content edits inside the target repo
- keeping tooling iteration centralized in the pageseeds CLI

## Prompts vs Skills (Non-Negotiable)

- Workflow knowledge lives in `.github/skills/*/SKILL.md` (source of truth)
- `.github/prompts/*.prompt.md` are thin launchers only (5-10 lines)
- Update the skill, not the prompt (unless CLI commands change)
- Never duplicate data structures/output formats/decision matrices into prompts

## Install CLIs (One-Time Per Machine)

Install tools in editable mode so changes in the automation repo apply immediately everywhere.

```bash
pip install pageseeds
```

After install, any repo can run:

- `pageseeds ...`

## Secrets (One-Time Per Machine)

Some workflows call external services (e.g. Ahrefs via CapSolver) and require API keys.

Preferred: set real environment variables in your shell startup.

Fallbacks supported by `pageseeds` (no per-repo copying required):

1) `~/.config/pageseeds/secrets.env` (format: `CAPSOLVER_API_KEY=...`)

## Deploy Skills/Prompts Into Another Repo (Optional)

If you want to author skills in the automation repo and then copy them into a target repo, prefer the payload installer:

```bash
pageseeds repo init --to /path/to/target/repo --bundle seo
```

For PostHog workflows:

```bash
pageseeds repo init --to /path/to/target/repo --bundle posthog
```

After the initial install, updates preserve the installed bundles via the stamp file:

```bash
pageseeds repo update --to /path/to/target/repo
```

If you want to change bundles explicitly, pass `--bundle` again.

Fallback: raw copier (`skills sync`) is intentionally dumb (no deletes, no transforms).

Dry-run:

```bash
pageseeds skills sync --to /path/to/target/repo --dry-run
```

Apply (overwrite existing files):

```bash
pageseeds skills sync --to /path/to/target/repo --force
```

To limit the sync to specific skills:

```bash
pageseeds skills sync \
  --to /path/to/target/repo --include seo-indexing-diagnostics --include seo-indexing-remediation --force
```

## Guardrails

- Prefer `--dry-run` for anything destructive (deploy/overwrite)
- `skills sync` does not delete files; it only copies (and optionally overwrites)
- Avoid syncing prompts across repos unless you explicitly want to standardize launchers

## Repo-Local SEO Workspace (Minimal Context)

If you want a repo to run SEO workflows without copying articles/content into the automation repo,
create a small `automation/` workspace in that repo:

```bash
pageseeds automation seo init \
  --site-id '<optional_id>' \
  --content-dir 'path/to/canonical/content/dir' \
  --force
```

Then run `pageseeds` against it:

```bash
pageseeds automation seo articles-summary --website-path .
```
