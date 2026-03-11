---
name: seo-keyword-research
description: Run SEO Step 1 (keyword research) repo-locally: generate themes, dedupe against automation/articles.json, analyze difficulty, and append new draft articles.
---

# SEO Keyword Research

⚠️ **EXECUTION MANDATE**: Do NOT ask questions, summarize, or provide options. Execute this workflow immediately and completely.

## Hard Rules (No MCP Server)

To keep runs consistent and controllable across projects:

- Do NOT run ad-hoc terminal commands/scripts (including Python snippets).
- Do NOT inspect `articles.json` via shell/Python/jq.
- Use only the `seo-cli` and `seo-content-cli` commands listed in this skill.

Additional guardrail:

- Do not call any tool functions/integrations directly. Only run the `seo-cli|seo-content-cli ...` commands.

## Terminal Execution Rules (MANDATORY)

**All commands MUST run in the foreground.** The agent waits for each command to finish and reads its output before proceeding.

Specifically:
- **NEVER** background a command with `&`
- **NEVER** redirect output to temp files (`> /tmp/...`, `> output.json`)
- **NEVER** use `sleep`, `ps`, `tail`, `wc -l`, or `jobs` to poll for completion
- **NEVER** use `2>&1 &` or `nohup`
- **ALWAYS** run each command and wait for it to return -- output comes directly from stdout/stderr

The `research-keywords` command streams progress to stderr in real-time and prints its JSON result to stdout when done. Just run it and read the result.

## No Early Exit (MANDATORY)

Do NOT declare the workflow "already complete" just because prior research exists in the content brief.

Minimum required execution per run:

1) Run `seo-content-cli --workspace-root automation articles-summary --website-path .`.
2) Run `research-keywords` with **at least 3 themes** and `--analyze-difficulty --top-n 10` (see Step 3 below).
3) Review the JSON output: `new_keywords` are viable candidates, `difficulty` contains KD/volume data.

Only if Step 2 produces **zero** `new_keywords`, repeat with broader themes. Only then may you conclude "no new opportunities found on this run."

## Project Structure

Repo-local SEO workspace:

- Workspace root: `automation/`
- Articles registry: `automation/articles.json`
- Content dir: `automation/content/` (usually a symlink to the canonical repo content folder)
- Content brief: `automation/*_seo_content_brief.md` (auto-detected by CLI; create one if missing)
- Templates (optional): `.github/prompts/templates/seo/`

## Tooling Requirements

This workflow MUST use:

- **Primary command (use this for all keyword research):**
  ```bash
  seo-content-cli --workspace-root automation research-keywords \
    --website-path . \
    --themes 'theme1' 'theme2' 'theme3' \
    --country us \
    --analyze-difficulty --top-n 10 \
    --auto-append --min-volume 500 --max-kd 30
  ```
  This single command generates keywords, dedupes against articles.json, analyzes difficulty for top 10 keywords, and auto-appends viable drafts. No temp files, no JSON construction, no intermediate steps.

  **`--top-n 10` is REQUIRED with `--analyze-difficulty`** -- it caps runtime to ~2-3 minutes. Without it, 30+ keywords would take 5-10 minutes.

  **`--auto-append` is REQUIRED** -- it automatically filters keywords by `--min-volume` / `--max-kd` and appends them as draft articles. The output JSON includes an `appended` section showing what was added.

- Project state: `seo-content-cli --workspace-root automation articles-summary --website-path .`

### Authentication Prereq

External keyword research uses Ahrefs behind Cloudflare and requires `CAPSOLVER_API_KEY`.

`seo-cli` will auto-load it from:
- `~/.config/automation/secrets.env` (preferred), or
- `/path/to/automation/.env` (automation repo), or
- a repo-local `.env` (walking up from the current working directory)

Optional (for individual keyword investigation):

- Single keyword difficulty: `seo-cli keyword-difficulty --keyword '<keyword>' --country us`
- Single keyword difficulty: `seo-cli keyword-difficulty --keyword '<keyword>' --country us`
- Cannibalization spot-check: `seo-content-cli --workspace-root automation get-articles-by-keyword --website-path . --keyword '<candidate>'`

Disallowed:

- Writing to temp files (`/tmp/*.txt`, `/tmp/*.json`)
- Backgrounding commands with `&`, `nohup`, or `disown`
- Running `sleep`, `ps`, `tail`, `wc`, `jobs` to poll for command completion
- Redirecting command output to files (`> output.json`, `2>&1`)
- Running `grep`, `sort`, `wc`, `head`, `cat` to process keyword output
- Terminal/Python scripts to "research" or invent keyword metrics
- Any non-CLI approach to inspect/dedupe `articles.json`
- Creating temp Python scripts, JSON files, or intermediate processing scripts
- Piping between `seo-cli` and `seo-content-cli` manually (use `research-keywords` instead)
- **Manually constructing JSON for `append-draft-articles`** -- use `--auto-append` instead
- Writing `cat > /tmp/*.json <<'EOF'` blocks to create draft payloads
- Inventing titles, KD scores, or volume numbers that weren't returned by the CLI

Allowed: if you need a plain list of existing keywords (no `jq`, no pipes), use:

```bash
seo-content-cli --workspace-root automation articles-index --website-path . \
  --format lines --field target_keyword --unique --sort --limit 50
```

## Workflow

### 1) Extract Current Content

Read the content brief (or create one based on `projects/seo/content_brief_template.md`) and extract:

- Topical clusters (name, pillar keywords, supporting content)
- Missing secondary intents (gaps per cluster)
- Priority levels (HIGH/MEDIUM/LOW)

### 2) Generate Keyword Themes

**Tier 1 - Fill Gaps (PRIORITY):**
- Each HIGH priority gap -> keyword theme
- Each cluster primary topic -> keyword theme

**Tier 2 - Explore New Topics:**
- Adjacent topics (one level broader/related)
- Emerging trends in the niche
- Low-competition opportunities

### 3) Research Keywords

Run `research-keywords` for all themes at once. Always include `--analyze-difficulty --top-n 10 --auto-append`:

```bash
seo-content-cli --workspace-root automation research-keywords \
  --website-path . \
  --themes 'gap theme 1' 'gap theme 2' 'adjacent topic 1' 'trending topic' \
  --country us \
  --analyze-difficulty --top-n 10 \
  --auto-append --min-volume 500 --max-kd 30
```

This single command will:
1. Generate keyword ideas for each theme (via Ahrefs, ~15s per theme)
2. Deduplicate across themes
3. Filter out keywords already in `articles.json`
4. Analyze difficulty/volume for top 10 new keywords (~15s each, ~2-3 min total)
5. Auto-append viable keywords (vol >= 500, KD <= 30) as draft articles to `articles.json`

The output JSON contains:
- `new_keywords`: list of keywords NOT in articles.json
- `filtered_out`: count of keywords already covered
- `difficulty`: batch difficulty/volume data for analyzed keywords
- `difficulty_skipped_keywords`: keywords beyond top-10 that were NOT analyzed (if any)
- `appended`: draft articles that were added to `articles.json` (IDs and details)

If the command returns zero `new_keywords`:
- Re-run with broader/adjacent themes
- Try shorter seed phrases or close synonyms

If you need to research additional themes, run `research-keywords` again with new themes -- deduplication is automatic.

If `difficulty_skipped_keywords` contains interesting keywords, run individual checks:
```bash
seo-cli keyword-difficulty --keyword '<candidate>' --country us
```

### 4) Review Results

`--auto-append` already filtered and added viable keywords. Review the `appended` section of the output to see what was added.

**If difficulty analysis succeeded:** only keywords meeting vol >= 500, KD <= 30 were appended.
**If difficulty analysis failed (API issues):** all new keywords (up to `--top-n`) were appended as drafts with unknown KD/volume. This is intentional -- do NOT manually re-create drafts.

For keywords in `difficulty_skipped_keywords` that look promising based on theme relevance, run individual `keyword-difficulty` checks.

### 5) Analyze Competition

The `--analyze-difficulty` flag already provides difficulty scores and SERP data. For deeper investigation of specific high-potential keywords:

- Run `seo-cli keyword-difficulty --keyword '<candidate>' --country us` to inspect:
  - Top ranking pages and content types
  - Angles not yet covered

Cannibalization guard:

- Call `seo-content-cli --workspace-root automation get-articles-by-keyword --website-path . --keyword '<candidate>'`.
- If it returns matches, treat as covered / at risk of cannibalization; skip or re-scope.

### 6) Update Content Brief

Add findings to the brief under a "Keyword Research Findings" section. Keep it concise (tables are fine).

### 7) Verify Appended Drafts

The `--auto-append` flag already added viable keywords as draft articles in Step 3. Check the `appended` section of the output JSON for the list of added article IDs.

If you want to add more candidates, re-run `research-keywords` with additional themes; deduplication is automatic. Avoid manual JSON entry.

---

## Re-run Logic

Skip any keyword rejected by `seo-content-cli filter-new-keywords`.

```
IF keyword is rejected by seo-content-cli filter-new-keywords (match found):
  SKIP (already acted on)
ELSE IF keyword meets criteria (vol 500+, KD <30):
  ANALYZE and ADD via seo-content-cli append-draft-articles
```

Re-run:
- Monthly (seasonal/trending)
- Quarterly (refresh KD/volume)
- As-needed (new content gaps)
