---
name: seo-content-creation
description: Run SEO Step 2 (content creation) repo-locally: pick next high-priority task, plan metadata with `pageseeds content`, write MDX, update automation/articles.json, and mark brief tasks complete.
---

# SEO Content Creation

⚠️ **EXECUTION MANDATE**: Do NOT ask questions, summarize, or provide options. Execute this workflow immediately and completely.

## No Early Exit (MANDATORY)

This step is NOT “create one article”. This step is “work the backlog”.

You MUST repeat the workflow until there are **no remaining HIGH PRIORITY tasks** in the content brief.

If the brief has no structured tasks and `pageseeds content get-next-content-task` falls back to registry drafts, you MUST repeat until there are **zero** `draft` articles remaining.

You are an SEO content writer. This workflow creates high-priority articles from the content brief using the brand voice and tracking system.

## Project Structure

Repo-local SEO workspace:

- Workspace root: `automation/`
- Content brief: `automation/*_seo_content_brief.md` (auto-detected by CLI)
- Articles JSON: `automation/articles.json`
- Content folder: `automation/content/` (usually a symlink to the canonical repo content folder)
- Brand voice (optional): `automation/brandvoice.md` or your repo’s existing brand voice doc

## Terminal Execution Rules (MANDATORY)

1. **ALWAYS foreground** — run every CLI command synchronously. NEVER background with `&`.
2. **NEVER poll** — no `sleep`, `ps`, `tail -f`, `wait`, or `jobs` loops.
3. **NEVER redirect to temp files** — no `> /tmp/…`, `cat > /tmp/…`, or heredoc writes.
4. **NEVER manually construct JSON** — every JSON blob the workflow needs is produced by a CLI command; do NOT hand-craft JSON objects in the terminal.
5. **Use `--from-plan`** — when calling `publish-article-and-complete-task`, always use `--from-plan`. This auto-populates article metadata (id, url_slug, file, published_date, target_keyword, keyword_difficulty, target_volume, word_count) from the plan and the MDX file. No need to pass `--article-json`.

## Tooling Requirements (No MCP Server)

**FILE FORMAT:** All article content files MUST be saved with `.mdx` extension (not `.md`).

Use `pageseeds content` (no MCP server):

- State: `pageseeds content --workspace-root automation articles-summary --website-path .`
- Draft listing: `pageseeds content --workspace-root automation articles-index --website-path . --status draft`
- Next task: `pageseeds content --workspace-root automation get-next-content-task --website-path . --priority 'HIGH PRIORITY'`
- Plan metadata: `pageseeds content --workspace-root automation plan-content-article --website-path . --task-id '<Task ID>' --extension mdx`
- Upsert article + complete brief task: `pageseeds content --workspace-root automation publish-article-and-complete-task --website-path . --task-id '<Task ID>' --from-plan`

Optional workflow tools:

Repo-local note: `pageseeds content ops ...` commands require a multi-site registry and are intentionally not part of the repo-local setup. Deploy via your repo’s normal pipeline.

Disallowed:

- Ad-hoc terminal/Python/jq to inspect or bulk-edit `articles.json` (use `pageseeds content` instead)
- Writing `cat > /tmp/*.json`, heredocs, or any temp file construction
- Manually constructing JSON blobs for `--article-json`
- Backgrounding commands with `&`
- Polling loops (`sleep`, `ps`, `tail -f`)

## Workflow

### 1) Read Context

- Call `pageseeds content --workspace-root automation articles-summary --website-path .`.
- Read your brand voice doc if present (optional).

Optional (recommended for visibility):

- `pageseeds content --workspace-root automation articles-index --website-path . --status draft`
- `pageseeds content --workspace-root automation articles-index --website-path . --status ready_to_publish`

### 2) Select Article to Create

- Call `pageseeds content --workspace-root automation get-next-content-task --website-path . --priority 'HIGH PRIORITY'`.
- Plan it with `pageseeds content --workspace-root automation plan-content-article --website-path . --task-id '<Task ID>' --extension mdx`.

If the brief is not structured, `pageseeds content get-next-content-task` will fall back to the next draft article in `articles.json`.

If `pageseeds content get-next-content-task` fails with “No draft articles found in articles.json”, treat it as **STOP** (no structured tasks + no draft backlog). Do not invent tasks.

### 3) Write Article (MDX)

Frontmatter template:

```markdown
---
title: "[Article Title - Under 60 Characters]"
date: "YYYY-MM-DD"
summary: "[1-2 sentence value proposition]"
keyword: "[primary-keyword-target]"
difficulty: [keyword_difficulty_from_task]
---

[Article content following brand voice]
```

Requirements:

- Follow brand voice (pragmatic, conversational, data-driven)
- Address the content gap from the task
- Add internal links listed in the task (when present)
- Keep it scannable (short paragraphs, subheadings)

### 4) Save File

- Folder: `automation/content/`
- Name: `{id}_{url_slug}.mdx` (from `pageseeds content plan-content-article`)

### 5) Update Registry + Brief

Use `pageseeds content publish-article-and-complete-task --from-plan` to:

- Upsert the article into `articles.json`
- Mark the corresponding content brief task as completed
- Auto-populate all metadata (id, url_slug, file, published_date, keyword, difficulty, volume, word count)

Command:

```
pageseeds content --workspace-root automation publish-article-and-complete-task \
  --website-path . --task-id '<Task ID>' --from-plan
```

Optional overrides: `--title 'Custom Title'`, `--word-count 1500`.

Default target status is `ready_to_publish` (not `published`).

### 6) Schedule Dates (Ready-to-Publish only)

Repo-local note: scheduling via `pageseeds content ops schedule-apply` requires a multi-site registry. For repo-local workflows, use Step 5’s `fix-dates` after publishing to keep recent dates sane.

### 7) Deploy (Optional)

When ready to deploy, use the publishing/deployment skill (`seo-publishing-deployment`).

### 8) Repeat Until Backlog Is Done (REQUIRED)

After completing ONE article (file saved + `publish-article-and-complete-task` succeeded), you MUST loop:

1) Call `pageseeds content get-next-content-task --priority 'HIGH PRIORITY'` again.
2) If a next task is returned, plan → write → publish → complete task.
3) Stop only when there are no remaining HIGH PRIORITY tasks, or when the CLI indicates there is no fallback draft backlog.
