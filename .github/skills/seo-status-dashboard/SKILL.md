```skill
---
name: seo-status-dashboard
description: Repo-local SEO dashboard: show latest published dates, article counts, draft backlogs, and recommend the next SEO step to run.
---

# SEO Status Dashboard (Repo-Local)

⚠️ **EXECUTION MANDATE**: Do NOT ask questions, summarize, or provide options. Execute this workflow immediately and completely.

## Purpose

Provide a quick, repo-local view so you can decide what to do next:

- When was the last article published?
- How many are draft vs ready_to_publish vs published?
- Should we do keyword research, write content, link content, or clean up?

## Repo-Local Workspace Assumptions

- Workspace root: `automation/`
- Website path: `.`
- Registry: `automation/articles.json`
- Content dir: `automation/content/` (often a symlink to the canonical content folder in this repo)

## Tooling (No MCP Server)

Use `pageseeds content` only:

```bash
pageseeds content --workspace-root automation articles-summary --website-path .
pageseeds content --workspace-root automation articles-index --website-path . --status published
pageseeds content --workspace-root automation articles-index --website-path . --status draft
pageseeds content --workspace-root automation articles-index --website-path . --status ready_to_publish
```

Disallowed:
- Ad-hoc terminal/Python/jq to inspect `articles.json` directly.

## Workflow

1) Run `articles-summary` and record totals + status breakdown.

2) Run `articles-index --status published` and identify the most recent `published_date` (if any).

3) Run `articles-index --status draft` and `--status ready_to_publish` and count backlog sizes.

4) Output a Markdown table:

| Metric | Value |
|---|---|
| Total articles | N |
| Published | N |
| Latest published | YYYY-MM-DD (Title) OR "none" |
| Drafts | N |
| Ready to publish | N |
| Next action | one of: Step 1 / Step 2 / Step 3 / Step 5 / Step 6 |

5) Next-action rules:

- If there are `ready_to_publish` articles: recommend **Step 4** (publish/deploy via repo pipeline) and **Step 5** (cleanup) if validation fails.
- Else if there are `draft` articles: recommend **Step 2** (content creation).
- Else recommend **Step 1** (keyword research).

If Search Console credentials/config are available and publishing cadence looks stalled, also recommend **Step 6** (indexing diagnostics).

6) Finish with a short, prioritized list of concrete next commands to run (copy/paste friendly).

```

