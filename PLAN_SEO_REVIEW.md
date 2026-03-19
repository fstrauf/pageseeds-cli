# SEO Review Mode — Design Specification

**Status:** Planning  
**Date:** 2026-03-18

---

## Goal

Add a content review mode to PageSeeds that systematically revisits published articles and landing pages, enriches them with live GSC performance data, and produces prioritised, actionable improvement recommendations — persisted as tasks just like content specs.

Keep it simple. No new databases. No parallel tracking systems. Everything lives in `articles.json` and the existing task/artifact machinery.

---

## Decisions Made

| Topic | Decision |
|---|---|
| Landing page tracking | Optimistic: registered manually when a landing page spec is created; same `articles.json` array, `type: landing_page` |
| Article + landing page registry | Single `articles.json` file with a `type` field (`blog \| landing_page`) |
| Landing page file discovery | Caller registers `file_path` at creation time; no auto-crawl in v1 |
| GSC data | Sync step hydrates a `gsc` block per article; reusable across workflows |
| Review output | Recommendation artifact stored under `task_results/<task_id>/`; task created in `task_list.json` |
| Review tasks | Persist until user marks done/skipped — same pattern as content specs |
| Articles with no GSC data | Skip in opportunity scoring; included in content-health-only scoring |
| Priority | Opportunity score (derived fresh from GSC block each run) + content age + time since last review |

---

## Phase 0: Schema Extension

Extend the per-article object in `articles.json`. All new fields are optional so existing records remain valid with no migration.

### New fields

```json
{
  "type": "blog",
  "file_path": "src/app/blog/my-article.mdx",
  "gsc": {
    "impressions": 1240,
    "clicks": 34,
    "ctr": 0.027,
    "avg_position": 11.4,
    "last_synced": "2026-03-18"
  },
  "last_reviewed_at": "2026-01-10",
  "review_status": "needs_review"
}
```

**`type`**: `blog` (default, backward-compatible) | `landing_page`

**`file_path`**: Repo-relative path to the source file. Required for review to work. Articles created before this field existed will have it populated on first review or via a backfill command.

**`gsc`**: Written by the GSC sync step. `null` or absent = no data yet. Never hand-modified.

**`last_reviewed_at`**: ISO date. Set when a review task is marked done.

**`review_status`**: `needs_review` | `in_review` | `reviewed`. Defaults to `needs_review` for anything not yet reviewed.

### Landing page entries

When a landing page spec is created, an entry is registered in `articles.json`:

```json
{
  "id": 42,
  "type": "landing_page",
  "title": "Freight Forwarding Software for SMBs",
  "url_slug": "freight-forwarding-software",
  "file_path": "src/app/(marketing)/freight-forwarding-software/page.mdx",
  "target_keyword": "freight forwarding software small business",
  "status": "published",
  "gsc": null,
  "last_reviewed_at": null,
  "review_status": "needs_review"
}
```

No auto-discovery. The user provides `file_path` when creating the spec. This is intentional — landing pages live in varied directory structures across different projects.

---

## Phase 1: GSC Sync Step

A deterministic, reusable utility that hydrates the `gsc` block for every article in `articles.json`.

### What it does

1. Reads `articles.json` for the project
2. Pulls GSC performance data for the site (using existing GSC API integration)
3. Matches each article by URL slug / full URL
4. Writes the `gsc` block into the matching record, setting `last_synced` to today
5. Articles with no GSC match get `gsc: null` (not an error)

### Key properties

- **Idempotent**: Safe to run any time. Overwrites existing `gsc` blocks with fresh data.
- **Non-destructive**: Only touches the `gsc` field. All other fields left as-is.
- **Reusable**: Not part of the review workflow specifically. Content creation prioritisation and clustering can read from the same enriched `articles.json`.

### Invocation

```bash
pageseeds automation seo gsc-sync-articles --project <project-id>
```

Or as an orchestrated step before any workflow that needs performance-aware prioritisation.

### Priority: build this first

Everything else (review scoring, opportunity ranking) reads from the `gsc` block. This unblocks all downstream workflows and is independently useful.

---

## Phase 2: Review Workflow

### Priority scoring (computed fresh each run, not stored)

| Tier | Criteria |
|---|---|
| **High** | GSC position 5–20, impressions above site threshold, CTR below band average — these are the best short-term wins |
| **High** | Not reviewed in > 12 months (blog) or > 6 months (landing page) |
| **Medium** | Position > 20 or impressions too low to be meaningful |
| **Low** | Position 1–4 (already performing), or reviewed recently |
| **Skip** | No `file_path` known, or `review_status: in_review` (already being worked) |

Articles without GSC data are included in review using content-health scoring only (no opportunity component).

### Workflow steps

1. **Pick target**: Select highest-priority article/landing page from `articles.json`
2. **Mark in-flight**: Set `review_status: in_review` on the record
3. **Deterministic checks** (via `seo-content-cli`):
   - Title/meta length and keyword presence
   - H1 count and heading structure
   - Word count vs. target range for type
   - Internal link count
   - Frontmatter completeness (`last_modified`, `description`)
4. **LLM analysis**: Pass article text + target keyword + GSC snapshot + check results to the LLM with a structured prompt encoding:
   - Intent satisfaction: does the article answer the query clearly?
   - Intro quality: answer-first or buried?
   - EEAT signals: examples, data, original insight present?
   - For landing pages: CTA clarity, objection handling, FAQ block
   - Specific rewrites: proposed title, H1, intro, FAQ questions, internal link targets
5. **Persist artifact**: Write structured recommendation JSON to `task_results/<task_id>/recommendations.json`
6. **Create task**: Add task to `task_list.json` with type `content_review`, status `needs_action`, linked to artifact

### Recommendation artifact structure

```json
{
  "article_id": 7,
  "article_type": "blog",
  "generated_at": "2026-03-18",
  "gsc_snapshot": { "impressions": 1240, "clicks": 34, "avg_position": 11.4 },
  "deterministic_checks": [
    { "check": "title_length", "passed": true },
    { "check": "h1_count", "passed": false, "detail": "Found 0 H1 tags" },
    { "check": "internal_links", "passed": false, "detail": "2 internal links found, minimum is 3" }
  ],
  "llm_recommendations": {
    "priority": "high",
    "summary": "Ranking 11th for target keyword with decent impressions but low CTR — suggests title/meta are not compelling enough.",
    "suggestions": [
      { "category": "title", "current": "...", "proposed": "..." },
      { "category": "meta_description", "current": "...", "proposed": "..." },
      { "category": "intro", "current": "...", "proposed": "..." },
      { "category": "internal_links", "detail": "Add links from /related-post-a and /landing-page-b" },
      { "category": "faq", "detail": "Add FAQ block answering: [question 1], [question 2], [question 3]" }
    ]
  }
}
```

### Task lifecycle

```
needs_review → in_review (workflow picks it) → needs_action (task created, awaiting user)
                                              → reviewed (user marks task done or skipped)
```

When user marks a review task as done or skipped:
- `review_status` → `reviewed`
- `last_reviewed_at` → today's date

Recommendations are not re-generated automatically. A manual re-trigger or a review cycle after `last_reviewed_at` > threshold will queue it again.

---

## Phase 3: Landing Page Spec Creation Integration

When `pageseeds` creates a landing page spec (e.g., via the landing-page-keyword-research workflow), the spec creation step also:

1. Prompts the user for `file_path` (or allows `unknown` as a placeholder)
2. Appends an entry to `articles.json` with `type: landing_page`, `status: draft` (until published), `review_status: needs_review`

No separate landing page registry. No second JSON to maintain.

---

## What We Are Not Building (v1)

- Auto-discovery of landing pages by crawling the repo
- Direct content edits by the agent (recommendations only; human edits)
- Backlink data integration (would need Ahrefs; add later if needed)
- PageSpeed / Core Web Vitals integration
- Multi-site batch review (single project at a time in v1)

---

## Build Order

1. **Schema extension** — add optional fields to articles.json schema docs and CLI validation. Backward compatible, zero migration.
2. **GSC sync step** — `gsc-sync-articles` command. Independently useful immediately.
3. **Review workflow** — pick → check → LLM → artifact → task.
4. **Landing page spec integration** — wire `articles.json` append into landing page spec creation.

---

## Files Affected

| File | Change |
|---|---|
| `packages/seo-content-cli/` | New `gsc-sync-articles` command; extend schema validation to accept new fields |
| `dashboard_ptk/dashboard/tasks/` | New `content_review` task type and runner |
| `.github/skills/seo-content-review/SKILL.md` | New skill documenting the review workflow |
| `.github/skills/landing-page-keyword-research/SKILL.md` | Update to include `articles.json` registration step |
| `examples/articles.json` (if it exists) | Update example schema to show new fields |
