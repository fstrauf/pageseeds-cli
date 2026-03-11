# Automation (CLI-first)

Unified automation package for this workspace.

- `automation-cli`: plain Python CLI entrypoint (no MCP server)

## ⚠️ MCP server is deprecated in this repo

This workspace runs workflows by calling Python CLIs directly via `uv run`.

```bash
uv run --directory packages/automation-cli automation-cli --help
```

---

## Legacy MCP server entrypoint

`automation-mcp` (the MCP server) remains in the package for historical reasons, but the repo workflows should not require it.

Example:

```bash
uv run --directory packages/automation-cli automation-cli --help
```

---

## Skills: Sync into another repo

Copy `.github/skills` (and optionally `.github/prompts`) from this automation repo into a target repo.

### Recommended: Repo Bootstrap (core payload)

Install the core bootstrap payload (distributed workflow skill + install/update/status prompts) into a repo:

```bash
uv run --directory packages/automation-cli automation-cli repo init --to /path/to/target/repo
```

Check if it's out of sync:

```bash
uv run --directory packages/automation-cli automation-cli repo status --to /path/to/target/repo
```

Update (overwrites managed files):

```bash
uv run --directory packages/automation-cli automation-cli repo update --to /path/to/target/repo
```

### Repo-Local SEO Workspace

Create a minimal `automation/` workspace in a repo so `seo-content-cli` can run without copying content into the automation repo:

```bash
uv run --directory packages/automation-cli automation-cli seo init \
  --repo-root /path/to/any/repo \
  --website-id my_site \
  --source-repo /path/to/content/repo \
  --source-content-dir content/blog \
  --articles-json /path/to/articles.json \
  --force
```

Check configuration:

```bash
uv run --directory packages/automation-cli automation-cli seo status \
  --repo-root /path/to/any/repo \
  --website-id my_site
```

### Advanced: Raw Skills/Prompts Sync

Dry-run:

```bash
uv run --directory packages/automation-cli automation-cli skills sync --to /path/to/target/repo --dry-run
```

Overwrite existing files:

```bash
uv run --directory packages/automation-cli automation-cli skills sync --to /path/to/target/repo --force
```

Also include prompts:

```bash
uv run --directory packages/automation-cli automation-cli skills sync --to /path/to/target/repo --include-prompts --force
```

## Geo: Google Maps enrichment (Playwright)

This repo includes a lightweight, UI-driven enrichment flow to look up cafe addresses and Google Maps links.

### One-time setup

```bash
uv run --directory packages/automation-cli python -m playwright install chromium
```

### CLI usage (recommended)

Look up a single place:

```bash
uv run --directory packages/automation-cli automation-cli geo maps-lookup \
	--query "Atomic Coffee, Auckland, New Zealand"
```

Enrich a CSV (adds address + maps URL columns):

```bash
uv run --directory packages/automation-cli automation-cli geo maps-enrich-csv \
	--input output/nz_pourover_cafes_2026-02-10.csv \
	--output output/nz_pourover_cafes_2026-02-10.maps.csv \
	--sleep-seconds 1.0 \
	--timeout-ms 45000
```

Notes:
- This automates the Google Maps web UI, so it can be fragile and may trigger consent/captcha.
- For production-grade enrichment, prefer an official API (e.g., Google Places API).
