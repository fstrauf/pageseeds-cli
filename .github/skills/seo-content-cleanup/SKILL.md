---
name: seo-content-cleanup
description: Run SEO Step 5 (content cleanup & QA) using `seo-content-cli` (uv run) to validate/clean content and fix date distribution issues safely.
---

# SEO Content Cleanup & Quality Assurance

This step ensures all content is properly formatted, dated, and ready for publication.

## Prerequisites

- Articles created (Step 2)
- Clustering & linking complete (Step 3)
- `articles.json` exists
- Content files exist in `automation/content/`

## Tools Used (No MCP Server)

Use the `seo-content-cli` entrypoint:

- `seo-content-cli --workspace-root automation validate-content --website-path .`
- `seo-content-cli --workspace-root automation clean-content --website-path .`
- `seo-content-cli --workspace-root automation analyze-dates --website-path .`
- `seo-content-cli --workspace-root automation fix-dates --website-path .`
- `seo-content-cli --workspace-root automation test-distribution --project-name '<Project Name>' --article-count <count> --earliest-date 'YYYY-MM-DD'`

## Workflow

### 1) Content Validation (read-only)

- `seo-content-cli --workspace-root automation validate-content --website-path .`

Review:
- duplicate title headings
- frontmatter/date mismatches
- missing fields

### 2) Content Cleaning (writes)

- `seo-content-cli --workspace-root automation clean-content --website-path .`

Then re-run:
- `seo-content-cli --workspace-root automation validate-content --website-path .` (should be clean)

### 3) Date Analysis (read-only)

- `seo-content-cli --workspace-root automation analyze-dates --website-path .`

### 4) Date Fixing (writes)

- `seo-content-cli --workspace-root automation fix-dates --website-path .`

This only redistributes *recent* articles (last 7 days); historical dates remain untouched.

Re-run:
- `seo-content-cli --workspace-root automation analyze-dates --website-path .` (should report no issues)

### 5) Distribution Preview (optional)

- `seo-content-cli --workspace-root automation test-distribution --project-name '<Project Name>' --article-count <count> --earliest-date 'YYYY-MM-DD'`

### 6) Final Validation

- `seo-content-cli --workspace-root automation validate-content --website-path .`
- `seo-content-cli --workspace-root automation analyze-dates --website-path .`

Spot-check a few `.mdx` files for frontmatter correctness.
