---
name: reddit-reply-engagement
description: Run Reddit Stage 2: review pending opportunities, post replies manually, and mark posted/skipped in the DB via the CLI.
---

# Reddit Reply & Engagement (Stage 2)

## Overview

You are posting thoughtful replies to opportunities found in Stage 1.

Input: pending opportunities from the database.

Output: posted replies tracked in the database.

## Setup / References

- `projects/reddit/_reply_guardrails.md`
- `general/<project>/<project>.md` (optional)
- `general/<project>/reddit_config.md` (optional)

## Workflow

### 1) Load Pending Opportunities

Use the CLI (no MCP server):

- `pageseeds reddit pending --project <project> --severity CRITICAL`

### 2) Review Each Opportunity

- Read context fields (`why_relevant`, `key_pain_points`, `website_fit`)
- Review drafted reply against guardrails
- Decide: post, edit, or skip

### 3) Post Reply (manual)

- Open the Reddit post URL
- Post the reply in browser
- Copy your Reddit comment URL

### 4) Mark Posted / Skipped in DB

- Posted (no MCP server):
	- `pageseeds reddit mark-posted --post-id <id> --reply-url '<comment_url>' --reply-text-file <path>`
	- Tip: use `--reply-text-file -` to paste via stdin.
- Skipped (no MCP server):
	- `pageseeds reddit mark-skipped --post-id <id> --reason '...'`

Optional:
- View stats: `pageseeds reddit stats --project <project>`
