---
name: seo-content-review
description: Run SEO content review: sync GSC data into articles.json, run deterministic checks, generate LLM recommendations for the highest-priority article, and create actionable tasks.
---

# SEO Content Review

⚠️ **EXECUTION MANDATE**: Do NOT ask questions, summarise, or provide options. Execute this workflow immediately and completely.

## When to Use

- Periodic review cycle (monthly or quarterly)
- After a batch of new articles has published and GSC data has had time to accumulate
- When a site shows stagnant or declining traffic despite reasonable content volume
- When the user says "review my content" or "what should I update"

## Prerequisites

- `articles.json` exists at `automation/articles.json` in the target repo
- Articles have `url_slug` or `file` populated so the GSC sync can match them
- GSC service account is configured (`GSC_SERVICE_ACCOUNT_PATH` in `~/.config/pageseeds/secrets.env`)

## Recommended Path — Dashboard

Run the `content_review` task type from the PageSeeds dashboard. It handles steps 1 and 2 automatically (GSC sync + deterministic audit), then invokes the agent for recommendations.

---

## Manual Path (CLI)

Use this if running outside the dashboard.

### Step 1 — Sync GSC data into articles.json

```bash
pageseeds automation seo gsc-sync-articles \
  --workspace-dir automation \
  --days 90
```

This fetches page-level metrics (impressions, clicks, CTR, avg position) and writes a `gsc` block onto each matched article. Articles with no GSC match get `gsc: null`. Check the `matched` vs `unmatched` counts — a high unmatched count means the site URL or `url_slug` values need attention.

### Step 2 — Run deterministic content audit

```bash
pageseeds automation seo content-audit \
  --workspace-dir automation
```

This checks every published article against objective rules (title length and keyword, H1, meta description, word count, internal links, frontmatter completeness) and writes ranked results to `automation/content_audit.json`.

### Step 3 — Pick the highest-priority article

Read `automation/articles.json` and `automation/content_audit.json`.

**Skip:** `status: draft`, `review_status: in_review`, `file` field missing or `"unknown"`

**Priority order:**

| Priority | Criteria |
|---|---|
| **Best** | GSC position 5–20 AND impressions > 200 AND CTR < 3% — ranking but underperforming CTR |
| **High** | `last_reviewed_at` is null or > 12 months ago |
| **High** | `health: poor` in the audit results |
| **Medium** | GSC position 20–50 with ≥ 100 impressions |
| **Low** | Position 1–4 and CTR ≥ 5% (already performing — skip unless nothing else) |
| **No GSC** | Pick by most audit failures |

Select the **single** highest-priority article. Set its `review_status` to `in_review` in `articles.json`.

### Step 4 — Read the source file

Locate the article using the `file` field (relative to repo root). Read the full content, noting: title, H1, meta description, intro paragraph, heading structure, internal links, word count, any FAQ block.

### Step 5 — Write recommendations

Create `.github/automation/task_results/<article_id>/recommendations.json`:

```json
{
  "article_id": 7,
  "article_title": "Article title",
  "article_file": "path/to/article.mdx",
  "url_slug": "article-slug",
  "target_keyword": "the target keyword",
  "generated_at": "2026-03-19",
  "gsc_snapshot": {
    "impressions": 1240,
    "clicks": 34,
    "ctr": 0.027,
    "avg_position": 11.4,
    "period_days": 90
  },
  "failed_checks": ["h1_keyword", "internal_links", "meta_description_keyword"],
  "suggestions": [
    {
      "category": "title",
      "current": "Current title text",
      "proposed": "Improved title text with keyword",
      "reason": "Including the exact keyword improves CTR from position 11"
    },
    {
      "category": "meta_description",
      "current": "...",
      "proposed": "..."
    },
    {
      "category": "intro",
      "current": "First paragraph text",
      "proposed": "Rewritten intro that leads with the key answer",
      "reason": "Answer-first intros reduce bounce rate and improve dwell time"
    },
    {
      "category": "internal_links",
      "proposed": "Add links to /related-slug-a and /related-slug-b in the body",
      "reason": "Passes authority to related pages and improves crawlability"
    },
    {
      "category": "faq",
      "proposed": "Add FAQ block answering: question 1, question 2, question 3",
      "reason": "Captures featured snippet opportunities for long-tail variants"
    }
  ]
}
```

`category` values: `title` | `meta_description` | `intro` | `h1` | `internal_links` | `faq` | `eeat` | `cta`

For landing pages also evaluate: value proposition clarity, CTA placement and repetition, objection handling, FAQ relevance to real search queries.

### Step 6 — Create a task

Add to `.github/automation/task_list.json`:

```json
{
  "id": "<article_id>",
  "type": "content_review",
  "status": "needs_action",
  "title": "Review: <article title>",
  "created_at": "<ISO datetime>",
  "artifact_path": ".github/automation/task_results/<article_id>/recommendations.json",
  "summary": "One sentence describing the top improvement opportunity"
}
```

---

## Completing a Review Task

When the user marks the task done or skipped, update `articles.json`:
- `review_status` → `reviewed`
- `last_reviewed_at` → today's ISO date

Update `task_list.json`:
- `status` → `done` or `skipped`
- `completed_at` → today's ISO datetime

---

## articles.json Schema Reference

All review fields are optional — existing records without them remain valid.

```json
{
  "id": 7,
  "type": "blog",
  "title": "My Article Title",
  "url_slug": "my-article-title",
  "file": "content/blog/001_my-article-title.mdx",
  "target_keyword": "my target keyword",
  "status": "published",
  "published_date": "2024-06-01",
  "gsc": {
    "impressions": 1240,
    "clicks": 34,
    "ctr": 0.0274,
    "avg_position": 11.4,
    "last_synced": "2026-03-19T12:00:00Z",
    "period_days": 90
  },
  "last_reviewed_at": "2026-01-10",
  "review_status": "needs_review"
}
```

**`type`**: `blog` (default) | `landing_page`  
**`gsc`**: Written exclusively by `gsc-sync-articles`. Never hand-edit.  
**`last_reviewed_at`**: Set only when a review task is marked done.  
**`review_status`**: `needs_review` | `in_review` | `reviewed`

## Landing Page Registration

When a landing page spec is created, register it in `articles.json`:

```json
{
  "id": 42,
  "type": "landing_page",
  "title": "Landing Page Title",
  "url_slug": "landing-page-slug",
  "file": "src/app/(marketing)/landing-page-slug/page.mdx",
  "target_keyword": "target keyword phrase",
  "status": "draft",
  "gsc": null,
  "last_reviewed_at": null,
  "review_status": "needs_review"
}
```

Set `file` to `"unknown"` if the file does not yet exist. Update it once created.

